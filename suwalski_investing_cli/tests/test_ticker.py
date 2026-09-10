from datetime import UTC, datetime

import pytest
from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.marketdata.errors import UnknownTickerError

from suwalski_investing_cli import main as cli

ASSUMPTIONS = ["--optimized-margin", "35%", "--growth", "1-3:55%", "--discount", "10%", "--terminal", "3%"]

SNAPSHOT = TickerSnapshot(
    ticker="NVDA",
    price=224.03,
    shares_outstanding=24.40e9,
    revenue_ttm=302.969e9,
    fcf_ttm=127.006e9,
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

        monkeypatch.setattr(cli, "get_snapshot", get_snapshot)

    return install


def test_ticker_fills_in_the_facts_and_echoes_them(stub_provider, capsys):
    stub_provider(SNAPSHOT)

    assert cli.main(["--ticker", "NVDA", *ASSUMPTIONS]) == 0

    output = capsys.readouterr().out
    assert "NVDA  price 224.03 USD  shares 24.40B" in output
    assert "revenue TTM 302.97B   FCF TTM 127.01B (41.9%)   net debt -46.00B" in output
    assert "GROWTH THE PRICE REQUIRES" in output


def test_explicit_flags_override_the_fetched_facts(stub_provider, capsys):
    stub_provider(SNAPSHOT)

    assert cli.main(["--ticker", "NVDA", "--price", "300", "--net-debt", "0", *ASSUMPTIONS, "--json"]) == 0

    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["current_price"] == 300.0
    # A pricier share needs more growth than the 4.76% the real price implies.
    assert payload["implied_growth"] > 0.0476


def test_an_unknown_ticker_exits_3(stub_provider, capsys):
    stub_provider(UnknownTickerError("Yahoo Finance has no financial statements for ZZZZ"))

    assert cli.main(["--ticker", "ZZZZ", *ASSUMPTIONS]) == 3
    assert "market data:" in capsys.readouterr().err
