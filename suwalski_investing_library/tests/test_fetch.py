"""Cover the yfinance handling without a network call: `fetch_snapshot` imports the module
lazily, so a stub in sys.modules is enough to drive every branch."""

import sys

import pandas as pd
import pytest
from suwalski_investing_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwalski_investing_library.marketdata.yahoo import fetch_snapshot

QUARTERS = [pd.Timestamp(date) for date in ("2026-07-31", "2026-04-30", "2026-01-31", "2025-10-31")]
INCOME = pd.DataFrame({"Total Revenue": [96_221e6, 81_615e6, 68_127e6, 57_006e6]}, index=QUARTERS).transpose()
CASHFLOW = pd.DataFrame({"Free Cash Flow": [21_400e6, 48_587e6, 34_904e6, 22_115e6]}, index=QUARTERS).transpose()


class _FastInfo(dict):
    def __init__(self, raises: Exception | None = None, **values):
        super().__init__(**values)
        self._raises = raises

    def get(self, key, default=None):
        if self._raises is not None:
            raise self._raises
        return super().get(key, default)


class _Handle:
    def __init__(self, income, fast_info):
        self.quarterly_income_stmt = income
        self.quarterly_cashflow = CASHFLOW
        self.quarterly_balance_sheet = pd.DataFrame()
        self.income_stmt = pd.DataFrame()
        self.cashflow = pd.DataFrame()
        self.fast_info = fast_info


@pytest.fixture
def stub_yfinance(monkeypatch):
    def install(handle):
        module = type(sys)("yfinance")
        module.Ticker = lambda symbol: handle
        monkeypatch.setitem(sys.modules, "yfinance", module)

    return install


def test_a_healthy_symbol_becomes_a_snapshot(stub_yfinance):
    stub_yfinance(_Handle(INCOME, _FastInfo(lastPrice=224.03, shares=24.4e9, currency="USD")))

    snapshot = fetch_snapshot(" nvda ")

    assert snapshot.ticker == "NVDA"  # trimmed and upper-cased
    assert snapshot.price == 224.03
    assert snapshot.revenue_ttm == pytest.approx(302.969e9)
    assert snapshot.source == "yfinance"


def test_empty_statements_mean_the_symbol_is_unknown(stub_yfinance):
    # Yahoo answers for anything; a symbol that does not exist just has no statements.
    stub_yfinance(_Handle(pd.DataFrame(), _FastInfo(KeyError("currentTradingPeriod"))))

    with pytest.raises(UnknownTickerError, match="no financial statements for ZZZZ"):
        fetch_snapshot("ZZZZ")


def test_a_broken_quote_on_a_real_company_is_an_upstream_failure(stub_yfinance):
    stub_yfinance(_Handle(INCOME, _FastInfo(KeyError("currentTradingPeriod"))))

    with pytest.raises(MarketDataError, match="no quote for NVDA"):
        fetch_snapshot("NVDA")


def test_a_missing_price_is_an_upstream_failure(stub_yfinance):
    stub_yfinance(_Handle(INCOME, _FastInfo(lastPrice=None, shares=24.4e9)))

    with pytest.raises(MarketDataError, match="no price for NVDA"):
        fetch_snapshot("NVDA")
