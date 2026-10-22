import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from suwinvtools_library.contracts.market import HistoryPoint, TickerSnapshot
from suwinvtools_library.marketdata.errors import UnknownTickerError
from suwinvtools_server.app import app
from suwinvtools_server.mcp import server as mcp_server

# Streamable HTTP clients announce both; the server answers with plain JSON.
HEADERS = {"accept": "application/json, text/event-stream"}

StubProvider = Callable[[TickerSnapshot | Exception], None]

SNAPSHOT = TickerSnapshot(
    ticker="NVDA",
    price=224.03,
    shares_outstanding=24.4,
    revenue_ttm=302.9,
    fcf_ttm=127.0,
    net_debt=-46.0,
    currency="USD",
    as_of=datetime.now(UTC),
    source="test",
    history=[
        HistoryPoint(year=2024, revenue=60.9, fcf=27.0, fcf_margin=0.443),
        HistoryPoint(year=2025, revenue=130.5, fcf=60.9, fcf_margin=0.467, revenue_growth=1.142),
    ],
)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    # The context manager runs the lifespan, which starts the MCP session manager — once
    # per process, the SDK refuses a second start, hence one client for the module.
    with TestClient(app) as client:
        yield client


@pytest.fixture
def stub_provider(monkeypatch: pytest.MonkeyPatch) -> StubProvider:
    def install(result: TickerSnapshot | Exception) -> None:
        def get_snapshot(ticker: str, **kwargs: object) -> TickerSnapshot:
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(mcp_server, "get_snapshot", get_snapshot)

    return install


def call(client: TestClient, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    result: dict[str, Any] = client.post("/mcp", headers=HEADERS, json=body).json()["result"]
    return result


def test_lists_the_three_tools(client: TestClient) -> None:
    body = client.post("/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()

    assert {tool["name"] for tool in body["result"]["tools"]} == {"fcf_margin_history", "revenue_history", "reverse_dcf"}


def test_fcf_margin_history_comes_from_the_snapshot(client: TestClient, stub_provider: StubProvider) -> None:
    stub_provider(SNAPSHOT)

    result = call(client, "fcf_margin_history", {"ticker": "NVDA"})

    assert [year["fcf_margin"] for year in result["structuredContent"]["years"]] == [0.443, 0.467]


def test_revenue_history_keeps_the_open_first_year(client: TestClient, stub_provider: StubProvider) -> None:
    stub_provider(SNAPSHOT)

    result = call(client, "revenue_history", {"ticker": "NVDA"})

    assert [year["revenue_growth"] for year in result["structuredContent"]["years"]] == [None, 1.142]


def test_reverse_dcf_fills_facts_from_the_ticker_and_explicit_values_win(client: TestClient, stub_provider: StubProvider) -> None:
    stub_provider(SNAPSHOT)

    result = call(
        client,
        "reverse_dcf",
        {
            "ticker": "NVDA",
            "price": 250.0,
            "optimized_fcf_margin": 0.35,
            "growth_segments": [{"start_year": 1, "end_year": 3, "growth": 0.55}],
        },
    )

    answer = result["structuredContent"]
    assert answer["request"]["current_price"] == 250.0
    assert answer["request"]["revenue"] == 302.9
    assert answer["result"]["solved_years"] == [4, 5, 6, 7, 8, 9, 10]
    assert answer["result"]["projection"]["intrinsic_value_per_share"] == pytest.approx(250.0, abs=1e-6)


def test_reverse_dcf_runs_offline_on_typed_facts(client: TestClient) -> None:
    result = call(client, "reverse_dcf", {"optimized_fcf_margin": 0.10, "price": 400.0, "shares_outstanding": 1.0, "revenue": 100.0})

    assert result["structuredContent"]["market"] is None
    assert result["structuredContent"]["result"]["solved_years"] == list(range(1, 11))


def test_bad_inputs_reach_the_model_with_their_reason(client: TestClient) -> None:
    result = call(
        client,
        "reverse_dcf",
        {"optimized_fcf_margin": 0.10, "price": 400.0, "shares_outstanding": 1.0, "revenue": 100.0, "terminal_growth": 0.2},
    )

    assert result["isError"] is True
    assert "terminal_growth" in json.dumps(result["content"])


def test_an_unknown_ticker_reaches_the_model_with_its_reason(client: TestClient, stub_provider: StubProvider) -> None:
    stub_provider(UnknownTickerError("Yahoo Finance has no financial statements for ZZZZ"))

    result = call(client, "revenue_history", {"ticker": "ZZZZ"})

    assert result["isError"] is True
    assert "ZZZZ" in json.dumps(result["content"])
