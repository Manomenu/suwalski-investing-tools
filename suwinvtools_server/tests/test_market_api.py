from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from suwinvtools_library.contracts.market import TickerSnapshot
from suwinvtools_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwinvtools_server.app import app
from suwinvtools_server.market import api as market_api

client = TestClient(app, raise_server_exceptions=False)

StubProvider = Callable[[TickerSnapshot | Exception], None]

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
def stub_provider(monkeypatch: pytest.MonkeyPatch) -> StubProvider:
    def install(result: TickerSnapshot | Exception) -> None:
        def get_snapshot(ticker: str, **kwargs: object) -> TickerSnapshot:
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(market_api, "get_snapshot", get_snapshot)

    return install


def test_snapshot_returns_the_observable_facts(stub_provider: StubProvider) -> None:
    stub_provider(SNAPSHOT)

    body = client.get("/market/NVDA").json()

    assert body["price"] == 224.03
    assert body["revenue_ttm"] == 302.9e9
    assert body["source"] == "test"


def test_an_unknown_symbol_is_a_404(stub_provider: StubProvider) -> None:
    stub_provider(UnknownTickerError("Yahoo Finance has no financial statements for ZZZZ"))

    response = client.get("/market/ZZZZ")

    assert response.status_code == 404
    assert "ZZZZ" in response.json()["detail"]


def test_a_provider_failure_is_a_502(stub_provider: StubProvider) -> None:
    stub_provider(MarketDataError("Yahoo Finance lookup for NVDA failed: timeout"))

    assert client.get("/market/NVDA").status_code == 502
