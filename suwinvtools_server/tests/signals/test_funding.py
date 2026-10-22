from collections.abc import Sequence
from datetime import timedelta

from pydantic import BaseModel

from suwinvtools_server.signals.checks.funding import ComputeCuts, LabFunding, LabIpo
from suwinvtools_server.signals.llm import Document
from suwinvtools_server.signals.model import (
    CapacityEvent,
    CapacityEvents,
    CapacityKind,
    FundingEvent,
    FundingEvents,
    FundingKind,
    IpoEvent,
    IpoEvents,
    IpoKind,
    PriceVsRange,
    Quote,
    Reading,
    Verdict,
)
from tests.signals.fakes import TODAY, Pages, Sec, Stub, context, reading, rss

REUTERS = ("OpenAI raises $40 billion at $300 billion valuation led by SoftBank", "Reuters", "https://www.reuters.com")
BLOOMBERG = ("OpenAI valued at $300 billion in a new funding round, sources say", "Bloomberg", "https://www.bloomberg.com")

# D1 -------------------------------------------------------------------------------------------


def round_event(
    quote: str, *, source: str = "n1", post_money: float = 300e9, kind: FundingKind = "priced_round", terms: bool = False
) -> FundingEvent:
    return FundingEvent(
        company="OpenAI",
        kind=kind,
        post_money_usd=post_money,
        month="2026-10",
        protective_terms=terms,
        quote=Quote(source_id=source, text=quote),
    )


def test_funding_events_become_readings_with_the_outlets_that_reported_them() -> None:
    fetch = Pages(default=rss(REUTERS, BLOOMBERG))
    events = FundingEvents(
        events=[
            round_event("OpenAI raises $40 billion at $300 billion valuation"),
            round_event("OpenAI valued at $300 billion", source="n2"),
        ]
    )
    result = LabFunding().read(context(fetch=fetch, extract=Stub({FundingEvents: events})))
    [row] = result.readings
    assert (row.subject, row.period, row.value) == ("OpenAI", "2026-10 priced_round", 300e9)
    assert row.data["domains"] == ["bloomberg.com", "reuters.com"]
    assert len(row.evidence) == 2
    # The other five labs found nothing about themselves.
    assert {o.verdict for o in result.skipped} == {Verdict.NOT_READY}


def test_funding_drops_invented_quotes_wrong_numbers_and_other_companies() -> None:
    fetch = Pages(default=rss(REUTERS))
    for event in (
        round_event("OpenAI is now worth a trillion dollars after a secret deal"),
        round_event("OpenAI raises $40 billion at $300 billion valuation", post_money=500e9),
    ):
        assert not LabFunding().read(context(fetch=fetch, extract=Stub({FundingEvents: FundingEvents(events=[event])}))).readings
    no_model = LabFunding().read(context(fetch=fetch, extract=None))
    assert {o.verdict for o in no_model.skipped} == {Verdict.INVALID}
    assert not LabFunding().read(context(fetch=Pages(), extract=Stub({FundingEvents: FundingEvents(events=[])}))).readings


def funding(period: str, value: float, *domains: str, terms: bool = False) -> Reading:
    return reading("D1", "OpenAI", period, value, protective_terms=terms, domains=list(domains))


def judge(*rows: Reading) -> Verdict:
    return LabFunding().evaluate(rows, TODAY)[-1].verdict


def test_funding_evaluation() -> None:
    first = funding("2025-03 priced_round", 300e9, "reuters.com")
    assert judge(first) is Verdict.BASELINE
    assert judge(first, funding("2026-10 priced_round", 600e9, "reuters.com", "bloomberg.com")) is Verdict.GREEN
    assert judge(first, funding("2026-10 priced_round", 600e9, "reuters.com")) is Verdict.UNCONFIRMED
    assert judge(first, funding("2025-10 priced_round", 250e9, "reuters.com", "ft.com")) is Verdict.RED  # down round
    assert judge(first, funding("2026-01 priced_round", 310e9, "reuters.com", "ft.com")) is Verdict.RED  # flat for 10 months
    assert judge(first, funding("2025-06 priced_round", 310e9, "reuters.com", "ft.com")) is Verdict.NEUTRAL  # flat but young
    assert judge(first, funding("2025-06 priced_round", 330e9, "reuters.com", "ft.com")) is Verdict.NEUTRAL
    assert judge(first, funding("2025-09 round_cut", 0, "reuters.com", "ft.com")) is Verdict.RED
    assert judge(first, funding("2025-09 priced_round", 400e9, "reuters.com", "ft.com", terms=True)) is Verdict.RED
    assert judge(funding("2025-09 round_cut", 0, "reuters.com", "ft.com")) is Verdict.RED


def test_funding_compares_with_the_latest_earlier_priced_valuation_only() -> None:
    rows = [
        funding("2025-03 priced_round", 300e9, "a.com"),
        funding("2025-06 tender", 0, "a.com"),
        funding("2025-12 priced_round", 450e9, "a.com", "b.com"),
    ]
    summary = LabFunding().evaluate(rows, TODAY)[-1]
    assert summary.verdict is Verdict.GREEN
    assert "+50.0%" in summary.summary


# D2 -------------------------------------------------------------------------------------------


def ipo_event(kind: IpoKind, *, vs_range: PriceVsRange = "unknown", below: bool = False) -> IpoEvent:
    return IpoEvent(
        company="OpenAI",
        kind=kind,
        price_vs_range=vs_range,
        first_day_below_offer=below,
        month="2026-10",
        quote=Quote(source_id="n1", text="OpenAI raises $40 billion at $300 billion valuation"),
    )


def test_ipo_news_and_registration_withdrawals_are_readings() -> None:
    sec = Sec()
    sec.pages.default = b'{"hits": {"hits": []}}'
    window = (TODAY - timedelta(days=35), TODAY)
    sec.search('"OpenAI"', "RW", window, [("0001234567-26-000001", 1234567, "OpenAI Inc", "rw.htm", "2026-10-15")])
    stub = Stub({IpoEvents: IpoEvents(events=[ipo_event("postponed")])})
    result = LabIpo().read(context(sec=sec, fetch=Pages(default=rss(REUTERS)), extract=stub))
    rows = {r.period: r for r in result.readings}
    assert set(rows) == {"2026-10 postponed", "2026-10 withdrawn"}
    assert rows["2026-10 withdrawn"].data["primary"] is True
    assert rows["2026-10 postponed"].data["domains"] == ["reuters.com"]


def test_ipo_not_ready_without_news_and_invalid_without_a_model() -> None:
    sec = Sec()
    sec.pages.default = b'{"hits": {"hits": []}}'
    quiet = LabIpo().read(context(sec=sec, fetch=Pages(), extract=Stub({IpoEvents: IpoEvents(events=[])})))
    assert not quiet.readings
    assert all(o.verdict in {Verdict.NOT_READY, Verdict.INVALID} for o in quiet.skipped)
    no_model = LabIpo().read(context(sec=sec, fetch=Pages(default=rss(REUTERS)), extract=None))
    assert {o.verdict for o in no_model.skipped} == {Verdict.INVALID}


def ipo(
    kind: str, *, vs_range: str = "unknown", below: bool = False, domains: tuple[str, ...] = ("a.com", "b.com"), primary: bool = False
) -> Reading:
    return reading(
        "D2",
        "OpenAI",
        f"2026-10 {kind}",
        None,
        price_vs_range=vs_range,
        first_day_below_offer=below,
        domains=list(domains),
        primary=primary,
    )


def test_ipo_evaluation() -> None:
    check = LabIpo()

    def verdict(row: Reading) -> Verdict:
        return check.evaluate([row], TODAY)[0].verdict

    assert verdict(ipo("postponed")) is Verdict.RED
    assert verdict(ipo("postponed", domains=("a.com",))) is Verdict.UNCONFIRMED
    assert verdict(ipo("withdrawn", domains=(), primary=True)) is Verdict.RED  # a filing needs no second outlet
    assert verdict(ipo("priced", vs_range="below")) is Verdict.RED
    assert verdict(ipo("priced", vs_range="within", below=True)) is Verdict.RED
    assert verdict(ipo("priced", vs_range="above")) is Verdict.GREEN
    assert verdict(ipo("priced", vs_range="above", domains=("a.com",))) is Verdict.UNCONFIRMED
    assert verdict(ipo("priced", vs_range="within")) is Verdict.NEUTRAL
    assert verdict(ipo("filed")) is Verdict.NEUTRAL


# D3 -------------------------------------------------------------------------------------------

CANCEL_HEADLINE = ("OpenAI walks away from a data center lease with Oracle", "Reuters", "https://www.reuters.com")
TERMINATION = "Oracle terminated the data center capacity agreement with its counterparty effective immediately."


def capacity_event(
    quote: str, source: str, *, who: str = "OpenAI", counterparty: str = "Oracle", kind: CapacityKind = "cancel"
) -> CapacityEvent:
    return CapacityEvent(
        who=who, counterparty=counterparty, kind=kind, size_usd=0, size_mw=300, month="2026-10", quote=Quote(source_id=source, text=quote)
    )


def capacity_answers(documents: Sequence[Document]) -> BaseModel:
    if documents[0].id == "d1":  # the 8-K
        return CapacityEvents(events=[capacity_event(TERMINATION, "d1", who="Oracle", counterparty="a customer")])
    return CapacityEvents(events=[capacity_event("OpenAI walks away from a data center lease with Oracle", "n1")])


def test_compute_cuts_from_news_and_from_8k_item_1_02() -> None:
    sec = Sec()
    sec.filings("ORCL", 1341439, [("8-K", "2026-10-10", "2026-10-09", "0001341439-26-000009", "o8k.htm", "1.02")])
    sec.document(1341439, "0001341439-26-000009", "o8k.htm", f"<p>Item 1.02. {TERMINATION}</p>")
    result = ComputeCuts().read(
        context(sec=sec, fetch=Pages(default=rss(CANCEL_HEADLINE)), extract=Stub({CapacityEvents: capacity_answers}))
    )
    rows = {r.subject: r for r in result.readings}
    assert set(rows) == {"OpenAI", "ORCL"}
    assert rows["OpenAI"].data["domains"] == ["reuters.com"]
    assert rows["ORCL"].data["primary"] is True
    assert not result.skipped


def test_compute_cuts_drop_events_about_other_companies_and_invented_quotes() -> None:
    other = CapacityEvents(
        events=[capacity_event("OpenAI walks away from a data center lease with Oracle", "n1", who="Intel", counterparty="Dell")]
    )
    assert not ComputeCuts().read(context(fetch=Pages(default=rss(CANCEL_HEADLINE)), extract=Stub({CapacityEvents: other}))).readings
    made_up = CapacityEvents(events=[capacity_event("OpenAI has burned down its own data center in Texas", "n1")])
    assert not ComputeCuts().read(context(fetch=Pages(default=rss(CANCEL_HEADLINE)), extract=Stub({CapacityEvents: made_up}))).readings
    no_model = ComputeCuts().read(context(fetch=Pages(default=rss(CANCEL_HEADLINE)), extract=None))
    assert {o.verdict for o in no_model.skipped} == {Verdict.INVALID}


def cut(kind: str, *, usd: float = 0, mw: float = 0, domains: tuple[str, ...] = ("a.com", "b.com"), primary: bool = False) -> Reading:
    return reading("D3", "OpenAI", f"2026-10 {kind}", usd or None, size_usd=usd, size_mw=mw, domains=list(domains), primary=primary)


def test_compute_cuts_evaluation() -> None:
    check = ComputeCuts()

    def verdict(row: Reading) -> Verdict:
        return check.evaluate([row], TODAY)[0].verdict

    for kind in ("cancel", "reduce", "delay", "resell_capacity", "sell_gpus_discount"):
        assert verdict(cut(kind)) is Verdict.RED
    assert verdict(cut("cancel", domains=("a.com",))) is Verdict.UNCONFIRMED
    assert verdict(cut("cancel", domains=(), primary=True)) is Verdict.RED
    assert verdict(cut("expand", usd=2e9)) is Verdict.GREEN
    assert verdict(cut("expand", mw=600)) is Verdict.GREEN
    assert verdict(cut("expand", usd=5e8, mw=100)) is Verdict.NEUTRAL
