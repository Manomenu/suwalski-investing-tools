"""One real call per outside service the signals read — left out of the gate (`-m "not live"`),
run by `just signals live-check` (scripts/.internal/live-check.sh). They catch a service that
changed its answer without a commit here; the monthly job reports the same as INVALID.

SEC wants a named User-Agent with a contact: export SEC_USER_AGENT="<tool> <you@example.com>"."""

from datetime import UTC, datetime, timedelta

import pytest

from suwinvtools_library.marketdata.edgar import CAPEX_TAGS, RPO_TAGS, Edgar, instants, quarterly_flows
from suwinvtools_server.signals.sources.http import http_get
from suwinvtools_server.signals.sources.news import headlines, search_url
from suwinvtools_server.signals.sources.openrouter import MODELS_URL, RANKINGS_URL, prices_from_models, token_market, usage_from_rankings
from suwinvtools_server.signals.sources.prices import closing_price
from suwinvtools_server.signals.sources.vast import family_price

pytestmark = pytest.mark.live

TODAY = datetime.now(UTC).date()


def test_edgar_answers_with_filings_facts_and_search() -> None:
    edgar = Edgar(cache_dir=None)
    cik = edgar.cik("MSFT")
    assert cik == "0000789019"
    assert any(filing.form in {"10-Q", "10-K"} for filing in edgar.filings(cik))
    facts = edgar.facts(cik)
    capex = quarterly_flows(facts, CAPEX_TAGS)
    assert capex
    assert max(capex) > TODAY - timedelta(days=200)  # a fresh quarter exists
    assert instants(facts, RPO_TAGS)
    hits = edgar.search('"impairment"', forms=("10-Q", "10-K", "8-K"), start=TODAY - timedelta(days=90), end=TODAY)
    assert hits


def test_vast_ai_has_offers_for_the_gpu_families() -> None:
    price = family_price("H200", http_get)
    assert price is not None
    assert price.offers > 0
    assert 0.3 < price.median < 30  # USD per GPU-hour: a sanity range, not a market view


def test_openrouter_models_and_rankings_still_have_the_shape_the_parsers_read() -> None:
    prices = prices_from_models(http_get(MODELS_URL))
    assert len(prices) > 50
    usage = usage_from_rankings(http_get(RANKINGS_URL))
    market = token_market(usage, prices)
    assert market.tokens > 0
    assert market.priced_share > 0.5  # most of the traffic has a list price; a drop means slugs no longer match


def test_google_news_rss_returns_headlines_with_outlets() -> None:
    found = headlines(http_get(search_url('"OpenAI" funding')))
    assert found
    assert all(item.title and item.domain for item in found)


def test_yahoo_has_a_recent_closing_price() -> None:
    price = closing_price("MSFT", TODAY)
    assert price is not None
    assert price > 0
