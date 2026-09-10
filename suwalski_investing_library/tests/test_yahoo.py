import pandas as pd
import pytest
from suwalski_investing_library.marketdata.errors import MarketDataError
from suwalski_investing_library.marketdata.yahoo import build_snapshot

# Real NVDA quarterly figures as Yahoo returns them: newest column first.
QUARTERS = [pd.Timestamp(date) for date in ("2026-07-31", "2026-04-30", "2026-01-31", "2025-10-31")]


def _frame(rows: dict[str, list[float]], columns: list | None = None) -> pd.DataFrame:
    return pd.DataFrame(rows, index=columns or QUARTERS).transpose()


INCOME = _frame({"Total Revenue": [96_221e6, 81_615e6, 68_127e6, 57_006e6]})
CASHFLOW = _frame(
    {
        "Free Cash Flow": [21_400e6, 48_587e6, 34_904e6, 22_115e6],
        "Operating Cash Flow": [24_077e6, 50_344e6, 36_188e6, 23_751e6],
        "Capital Expenditure": [-2_677e6, -1_757e6, -1_284e6, -1_636e6],
    }
)
BALANCE = _frame({"Total Debt": [10_000e6] * 4, "Cash Cash Equivalents And Short Term Investments": [56_000e6] * 4})


def _snapshot(**overrides):
    kwargs = {
        "price": 224.03,
        "shares": 24.40e9,
        "currency": "USD",
        "income": INCOME,
        "cashflow": CASHFLOW,
        "balance": BALANCE,
    }
    return build_snapshot("NVDA", **{**kwargs, **overrides})


def test_ttm_figures_sum_the_last_four_quarters():
    snapshot = _snapshot()

    assert snapshot.revenue_ttm == pytest.approx(302.969e9)
    assert snapshot.fcf_ttm == pytest.approx(127.006e9)
    assert snapshot.fcf_margin == pytest.approx(0.4192, abs=1e-4)


def test_net_debt_is_debt_minus_cash_and_goes_negative_on_net_cash():
    assert _snapshot().net_debt == pytest.approx(10_000e6 - 56_000e6)


def test_missing_free_cash_flow_row_falls_back_to_operating_minus_capex():
    cashflow = CASHFLOW.drop(index=["Free Cash Flow"])

    snapshot = _snapshot(cashflow=cashflow)

    assert snapshot.fcf_ttm == pytest.approx(134.36e9 - 7.354e9, rel=1e-6)


def test_older_quarters_are_ignored_however_yahoo_orders_the_columns():
    scrambled = INCOME[sorted(INCOME.columns)]  # oldest first
    scrambled.insert(0, pd.Timestamp("2025-07-31"), 40_000e6)

    assert _snapshot(income=scrambled).revenue_ttm == pytest.approx(302.969e9)


def test_a_stub_with_fewer_than_four_quarters_is_refused():
    with pytest.raises(MarketDataError, match="only 2 quarters of revenue"):
        _snapshot(income=_frame({"Total Revenue": [10e6, 9e6]}, columns=QUARTERS[:2]))


def test_a_missing_share_count_is_refused():
    with pytest.raises(MarketDataError, match="no share count"):
        _snapshot(shares=None)


def test_a_debt_free_balance_sheet_means_zero_net_debt():
    assert _snapshot(balance=pd.DataFrame()).net_debt == 0.0
