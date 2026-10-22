"""Cover the yfinance handling without a network call: `fetch_snapshot` imports the module
lazily, so a stub in sys.modules is enough to drive every branch."""

import sys
from collections.abc import Callable
from typing import Any

import pandas as pd  # pyright: ignore[reportMissingTypeStubs] — pandas ships no type information here
import pytest

from suwinvtools_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwinvtools_library.marketdata.yahoo import fetch_snapshot

QUARTERS = [pd.Timestamp(date) for date in ("2026-07-31", "2026-04-30", "2026-01-31", "2025-10-31")]


def _statement(rows: dict[str, list[float]]) -> pd.DataFrame:
    """Statement-shaped frame (pandas is untyped here, hence the Any on the way through)."""
    index: Any = QUARTERS
    frame: Any = pd.DataFrame(rows, index=index)
    return frame.transpose()


INCOME = _statement({"Total Revenue": [96_221e6, 81_615e6, 68_127e6, 57_006e6]})
CASHFLOW = _statement({"Free Cash Flow": [21_400e6, 48_587e6, 34_904e6, 22_115e6]})


class _FastInfo:
    def __init__(self, raises: Exception | None = None, **values: object) -> None:
        self._values = values
        self._raises = raises

    def get(self, key: str) -> object:
        if self._raises is not None:
            raise self._raises
        return self._values.get(key)


class _Handle:
    def __init__(self, income: pd.DataFrame, fast_info: _FastInfo) -> None:
        self.quarterly_income_stmt = income
        self.quarterly_cashflow = CASHFLOW
        self.quarterly_balance_sheet = pd.DataFrame()
        self.income_stmt = pd.DataFrame()
        self.cashflow = pd.DataFrame()
        self.fast_info = fast_info


@pytest.fixture
def stub_yfinance(monkeypatch: pytest.MonkeyPatch) -> Callable[[_Handle], None]:
    def install(handle: _Handle) -> None:
        module = type(sys)("yfinance")

        def ticker(symbol: str) -> _Handle:
            return handle

        module.Ticker = ticker
        monkeypatch.setitem(sys.modules, "yfinance", module)

    return install


def test_a_healthy_symbol_becomes_a_snapshot(stub_yfinance: Callable[[_Handle], None]) -> None:
    stub_yfinance(_Handle(INCOME, _FastInfo(lastPrice=224.03, shares=24.4e9, currency="USD")))

    snapshot = fetch_snapshot(" nvda ")

    assert snapshot.ticker == "NVDA"  # trimmed and upper-cased
    assert snapshot.price == 224.03
    assert snapshot.revenue_ttm == pytest.approx(302.969e9)
    assert snapshot.source == "yfinance"


def test_empty_statements_mean_the_symbol_is_unknown(stub_yfinance: Callable[[_Handle], None]) -> None:
    # Yahoo answers for anything; a symbol that does not exist just has no statements.
    stub_yfinance(_Handle(pd.DataFrame(), _FastInfo(KeyError("currentTradingPeriod"))))

    with pytest.raises(UnknownTickerError, match="no financial statements for ZZZZ"):
        fetch_snapshot("ZZZZ")


def test_a_broken_quote_on_a_real_company_is_an_upstream_failure(stub_yfinance: Callable[[_Handle], None]) -> None:
    stub_yfinance(_Handle(INCOME, _FastInfo(KeyError("currentTradingPeriod"))))

    with pytest.raises(MarketDataError, match="no quote for NVDA"):
        fetch_snapshot("NVDA")


def test_a_missing_price_is_an_upstream_failure(stub_yfinance: Callable[[_Handle], None]) -> None:
    stub_yfinance(_Handle(INCOME, _FastInfo(lastPrice=None, shares=24.4e9)))

    with pytest.raises(MarketDataError, match="no price for NVDA"):
        fetch_snapshot("NVDA")
