"""The parsers of every outside service, against recorded answers (tests/signals/fixtures/)."""

import json
from datetime import date

import pytest

from suwinvtools_library.marketdata.edgar import (
    CAPEX_TAGS,
    RPO_TAGS,
    calendar_quarter,
    filings_from_submissions,
    hits_from_search,
    html_to_text,
    instants,
    paragraphs_with,
    quarter_before,
    quarterly_flows,
    trailing_sum,
)
from suwinvtools_server.signals.sources.http import SourceChangedError
from suwinvtools_server.signals.sources.news import headlines, search_url
from suwinvtools_server.signals.sources.openrouter import (
    ModelUsage,
    Price,
    prices_from_models,
    token_market,
    usage_from_rankings,
)
from suwinvtools_server.signals.sources.vast import FAMILIES, family_price, offers_url, per_gpu_prices
from tests.signals.fakes import Pages, fixture

# vast.ai --------------------------------------------------------------------------------------


def test_vast_prices_are_per_gpu_hour() -> None:
    prices = per_gpu_prices(fixture("vast_h100.json"))
    assert len(prices) == 12
    assert prices[0] == pytest.approx(3.575555555555556 / 2)  # a 2-GPU offer is split between its GPUs


@pytest.mark.parametrize(
    "body",
    [b"<html>", b'{"rows": []}', b'{"offers": [{"num_gpus": 1}]}', b'{"offers": [{"dph_total": 2.0, "num_gpus": 0}]}'],
)
def test_vast_answers_of_an_unknown_shape_are_a_changed_source(body: bytes) -> None:
    with pytest.raises(SourceChangedError):
        per_gpu_prices(body)


def test_vast_family_pools_its_variants_and_none_means_no_offers() -> None:
    fetch = Pages(default=fixture("vast_h100.json"))
    price = family_price("H100", fetch)
    assert price is not None
    assert (price.family, price.offers) == ("H100", 12 * len(FAMILIES["H100"]))
    assert price.p25 <= price.median
    assert fetch.requested == [offers_url(name) for name in FAMILIES["H100"]]
    assert family_price("B200", Pages(default=b'{"offers": []}')) is None
    single = family_price("B200", Pages(default=json.dumps({"offers": [{"dph_total": 6.0, "num_gpus": 2}]}).encode()))
    assert single is not None
    assert (single.median, single.p25, single.offers) == (3.0, 3.0, 1)


# OpenRouter -----------------------------------------------------------------------------------


def test_rankings_page_gives_the_latest_day_of_per_model_tokens() -> None:
    usage = usage_from_rankings(fixture("openrouter_rankings.html"))
    assert {row.day for row in usage} == {"2026-10-21"}
    assert len(usage) == 4
    assert usage[0] == ModelUsage("2026-10-21", "deepseek/deepseek-v4.1-flash-20261017", 16237260463007, 236336043470)


def test_rankings_keep_only_the_newest_day() -> None:
    row = (
        '{\\"date\\":\\"%s 00:00:00\\",\\"model_permaslug\\":\\"a/b\\",\\"variant\\":\\"standard\\",'
        '\\"total_completion_tokens\\":1,\\"total_prompt_tokens\\":2}'
    )
    page = (row % "2026-10-20" + row % "2026-10-21").encode()
    assert [r.day for r in usage_from_rankings(page)] == ["2026-10-21"]


def test_rankings_page_without_token_counts_is_a_changed_source() -> None:
    with pytest.raises(SourceChangedError):
        usage_from_rankings(b"<html>nothing to see</html>")


def test_model_prices_are_indexed_by_slug_and_id_and_placeholders_are_skipped() -> None:
    prices = prices_from_models(fixture("openrouter_models.json"))
    assert prices["minimax/minimax-m3.1-flash-20261019"] == prices["minimax/minimax-m3.1-flash"] == Price(prompt=1.5e-7, completion=6e-7)
    router = json.dumps(
        {
            "data": [
                {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
                {"id": "x/free", "pricing": {"prompt": "0", "completion": "0"}},
            ]
        }
    )
    assert "x/free" in prices_from_models(router.encode())
    for body in (b"nope", b'{"models": []}'):
        with pytest.raises(SourceChangedError):
            prices_from_models(body)


def test_token_market_prices_tokens_and_reports_how_much_was_priced() -> None:
    usage = [
        ModelUsage("2026-10-21", "a/paid", 1_000_000, 500_000),
        ModelUsage("2026-10-21", "a/free", 1_000_000, 0),
        ModelUsage("2026-10-21", "a/unknown", 500_000, 0),
    ]
    prices = {"a/paid": Price(prompt=2e-6, completion=8e-6), "a/free": Price(prompt=0.0, completion=0.0)}
    market = token_market(usage, prices)
    assert market.tokens == 3_000_000
    assert market.spend == pytest.approx(2.0 + 4.0)
    assert market.priced_share == pytest.approx(2_500_000 / 3_000_000)
    assert (market.day, market.models) == ("2026-10-21", 3)


# Google News ----------------------------------------------------------------------------------


def test_headlines_split_title_outlet_and_domain() -> None:
    found = headlines(fixture("news_openai.xml"))
    assert [item.id for item in found] == ["n1", "n2", "n3", "n4"]
    first = found[0]
    assert first.title.startswith("OpenAI targets $30 billion funding")
    assert not first.title.endswith("Reuters")  # Google's " - Outlet" suffix is dropped
    assert (first.outlet, first.domain) == ("Reuters", "reuters.com")
    assert found[2].domain == "bloomberg.com"  # "www." is dropped
    assert first.text.startswith(first.title)


def test_a_feed_that_is_not_rss_is_a_changed_source() -> None:
    for body in (b"<html><body>captcha</body></html>", b"not xml at all", b"<rss></rss>"):
        with pytest.raises(SourceChangedError):
            headlines(body)


def test_search_url_limits_the_age_and_escapes_the_query() -> None:
    url = search_url('"OpenAI" IPO', days=14)
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "when%3A14d" in url
    assert " " not in url


# EDGAR: pure functions ------------------------------------------------------------------------


def test_filings_come_newest_first_with_their_8k_items() -> None:
    filings = filings_from_submissions("0000789019", json.loads(fixture("submissions_msft.json")))
    assert len(filings) == 40
    assert [f.filed for f in filings] == sorted((f.filed for f in filings), reverse=True)
    first = filings[0]
    assert (first.cik, first.form, first.filed) == ("0000789019", "ARS", date(2026, 10, 21))
    assert first.url == f"https://www.sec.gov/Archives/edgar/data/789019/{first.accession.replace('-', '')}/{first.primary_document}"
    submissions: dict[str, object] = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q"],
                "filingDate": ["2026-07-30", "2026-07-29"],
                "reportDate": ["", "2026-06-30"],
                "accessionNumber": ["0000000000-26-000001", "0000000000-26-000002"],
                "primaryDocument": ["a.htm", "b.htm"],
                "items": ["2.02, 9.01", ""],
            }
        }
    }
    eight_k, ten_q = filings_from_submissions("0000000001", submissions)
    assert (eight_k.items, eight_k.report_date) == (("2.02", "9.01"), None)
    assert (ten_q.items, ten_q.report_date) == ((), date(2026, 6, 30))


def test_search_hits_carry_company_form_date_and_document_url() -> None:
    hits = hits_from_search(json.loads(fixture("search_impairment.json")))
    assert len(hits) == 3
    first = hits[0]
    assert (first.cik, first.form, first.filed) == ("0001571996", "8-K", date(2026, 5, 28))
    assert first.url == "https://www.sec.gov/Archives/edgar/data/1571996/000157199626000021/exhibit991earnings8kq1fy27.htm"
    assert hits_from_search({}) == []


def quarter_facts(entries: list[tuple[str, str, float]]) -> dict[str, object]:
    """companyfacts of one tag from (start, end, value) rows, the way 10-Qs and 10-Ks report them."""
    rows = [{"start": start, "end": end, "val": value, "filed": end} for start, end, value in entries]
    return {"facts": {"us-gaap": {"PaymentsToAcquireProductiveAssets": {"units": {"USD": rows}}}}}


def test_quarterly_flows_difference_the_year_to_date_figures() -> None:
    facts = quarter_facts(
        [
            ("2025-01-01", "2025-03-31", 10.0),
            ("2025-01-01", "2025-06-30", 25.0),  # 10-Q for Q2: six months
            ("2025-01-01", "2025-09-30", 45.0),
            ("2025-01-01", "2025-12-31", 70.0),  # the 10-K: the whole year
        ]
    )
    flows = quarterly_flows(facts, CAPEX_TAGS)
    assert flows == {date(2025, 3, 31): 10.0, date(2025, 6, 30): 15.0, date(2025, 9, 30): 20.0, date(2025, 12, 31): 25.0}


def test_quarterly_flows_ignore_odd_periods_and_take_the_tag_with_the_newest_quarter() -> None:
    odd = quarter_facts([("2025-01-01", "2025-02-15", 5.0)])
    assert quarterly_flows(odd, CAPEX_TAGS) == {}
    old = {
        "PaymentsToAcquirePropertyPlantAndEquipment": {
            "units": {"USD": [{"start": "2020-01-01", "end": "2020-03-31", "val": 1.0, "filed": "2020-04-30"}]}
        }
    }
    new = {
        "PaymentsToAcquireProductiveAssets": {
            "units": {"USD": [{"start": "2025-01-01", "end": "2025-03-31", "val": 9.0, "filed": "2025-04-30"}]}
        }
    }
    assert quarterly_flows({"facts": {"us-gaap": {**old, **new}}}, CAPEX_TAGS) == {date(2025, 3, 31): 9.0}


def test_a_restated_figure_replaces_the_earlier_one() -> None:
    rows = [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 10.0, "filed": "2025-04-30"},
        {"start": "2025-01-01", "end": "2025-03-31", "val": 11.0, "filed": "2026-04-30"},
    ]
    facts: dict[str, object] = {"facts": {"us-gaap": {"PaymentsToAcquireProductiveAssets": {"units": {"USD": rows}}}}}
    assert quarterly_flows(facts, CAPEX_TAGS) == {date(2025, 3, 31): 11.0}


def test_recorded_companyfacts_give_quarters_and_backlog() -> None:
    facts = json.loads(fixture("facts_msft.json"))
    capex = quarterly_flows(facts, CAPEX_TAGS)
    assert capex[date(2026, 6, 30)] == 35_802_000_000.0
    assert trailing_sum(capex, date(2026, 6, 30)) == sum(capex[day] for day in sorted(capex)[-4:])
    backlog = instants(facts, RPO_TAGS)
    assert backlog[date(2026, 6, 30)] == 684_000_000_000.0


def test_instants_take_the_latest_filing_and_skip_durations() -> None:
    rows = [
        {"end": "2025-12-31", "val": 1.0, "filed": "2026-01-30"},
        {"end": "2025-12-31", "val": 2.0, "filed": "2026-02-27"},
        {"start": "2025-10-01", "end": "2025-12-31", "val": 99.0, "filed": "2026-02-27"},
    ]
    facts: dict[str, object] = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": rows}}}}}
    assert instants(facts, ("EntityCommonStockSharesOutstanding",), namespace="dei") == {date(2025, 12, 31): 2.0}


def test_trailing_sum_needs_consecutive_quarters_ending_on_the_day_asked() -> None:
    quarters = {date(2025, 3, 31): 1.0, date(2025, 6, 30): 2.0, date(2025, 9, 30): 3.0, date(2025, 12, 31): 4.0, date(2026, 3, 31): 5.0}
    assert trailing_sum(quarters, date(2025, 12, 31)) == 10.0
    assert trailing_sum(quarters, date(2026, 3, 31)) == 14.0
    assert trailing_sum(quarters, date(2026, 3, 31), 2) == 9.0
    assert trailing_sum(quarters, date(2025, 9, 30)) is None  # only three quarters so far
    assert trailing_sum(quarters, date(2025, 11, 30)) is None  # not a quarter end
    gap = {date(2025, 3, 31): 1.0, date(2025, 12, 31): 4.0, date(2026, 3, 31): 5.0, date(2026, 6, 30): 6.0}
    assert trailing_sum(gap, date(2026, 6, 30)) is None  # a missing quarter would make a short "year"


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 6, 30), "2026Q2"),
        (date(2026, 3, 31), "2026Q1"),
        (date(2025, 9, 27), "2025Q3"),
        (date(2025, 12, 28), "2025Q4"),
        (date(2026, 1, 3), "2025Q4"),
    ],
)
def test_calendar_quarter_places_fiscal_periods_by_their_middle(day: date, expected: str) -> None:
    assert calendar_quarter(day) == expected


@pytest.mark.parametrize(
    ("filed", "expected"),
    [
        (date(2026, 7, 30), "2026Q2"),
        (date(2026, 1, 28), "2025Q4"),
        (date(2026, 4, 1), "2026Q1"),
        (date(2026, 3, 31), "2025Q4"),
        (date(2026, 10, 22), "2026Q3"),
    ],
)
def test_quarter_before_is_the_quarter_an_earnings_release_reports_on(filed: date, expected: str) -> None:
    assert quarter_before(filed) == expected


def test_html_becomes_text_without_tags_scripts_or_the_xbrl_header() -> None:
    html = (
        "<html><head><title>x</title></head><body><ix:header>hidden facts</ix:header>"
        "<script>var a=1;</script><p>First &amp; second</p><div>Third</div><table><tr><td>A</td><td>1</td></tr></table></body></html>"
    )
    text = html_to_text(html)
    assert "hidden facts" not in text
    assert "var a" not in text
    assert text.splitlines() == ["First & second", "Third", "A 1"]


def test_paragraphs_with_returns_merged_windows_around_each_word() -> None:
    text = "intro " * 50 + "the useful life of servers is 6 years. " + "filler " * 200 + "Another useful lives note. " + "end " * 50
    found = paragraphs_with(text, "useful life", "useful lives", window=100)
    assert len(found) == 2
    assert "servers is 6 years" in found[0]
    assert "Another useful lives" in found[1]
    assert all(len(passage) <= 160 for passage in found)
    close = paragraphs_with("a useful life here and useful lives there", "useful life", "useful lives", window=100)
    assert len(close) == 1  # overlapping windows are one passage
    assert paragraphs_with(text, "goodwill") == []
    assert len(paragraphs_with(("useful life " + "z" * 100) * 30, "useful life", window=10, limit=3)) == 3
