from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwalski_investing_server.app import app
from suwalski_investing_server.market import router as market_router

client = TestClient(app, raise_server_exceptions=False)

SNAPSHOT = TickerSnapshot(
    ticker="NVDA",
    price=224.03,
    shares_outstanding=24.4e9,
    revenue_ttm=302.9e9,
    fcf_ttm=127.0e9,
    net_debt=-46.0e9,
    currency="USD",
    as_of=datetime.now(UTC),
    source="test",
)


@pytest.fixture
def stub_provider(monkeypatch):
    def install(result):
        def get_snapshot(ticker, **kwargs):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(market_router, "get_snapshot", get_snapshot)

    return install


def test_snapshot_returns_the_observable_facts(stub_provider):
    stub_provider(SNAPSHOT)

    body = client.get("/market/NVDA").json()

    assert body["price"] == 224.03
    assert body["revenue_ttm"] == 302.9e9
    assert body["source"] == "test"


def test_an_unknown_symbol_is_a_404(stub_provider):
    stub_provider(UnknownTickerError("Yahoo Finance has no financial statements for ZZZZ"))

    response = client.get("/market/ZZZZ")

    assert response.status_code == 404
    assert "ZZZZ" in response.json()["detail"]


def test_a_provider_failure_is_a_502(stub_provider):
    stub_provider(MarketDataError("Yahoo Finance lookup for NVDA failed: timeout"))

    assert client.get("/market/NVDA").status_code == 502
