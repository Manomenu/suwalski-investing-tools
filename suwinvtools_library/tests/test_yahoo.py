from collections.abc import Sequence
from typing import Any

import pandas as pd  # pyright: ignore[reportMissingTypeStubs] — pandas ships no type information here
import pytest

from suwinvtools_library.contracts.market import TickerSnapshot
from suwinvtools_library.marketdata.errors import MarketDataError
from suwinvtools_library.marketdata.yahoo import build_history, build_snapshot

# Real NVDA quarterly figures as Yahoo returns them: newest column first.
QUARTERS = [pd.Timestamp(date) for date in ("2026-07-31", "2026-04-30", "2026-01-31", "2025-10-31")]


# pandas is untyped here, so each frame operation the tests need is wrapped once, typed as Any
# on the way through.
def _statement(rows: dict[str, list[float]], columns: Sequence[object]) -> pd.DataFrame:
    """Statement-shaped frame: one row per line item, one column per report date."""
    index: Any = columns
    frame: Any = pd.DataFrame(rows, index=index)
    return frame.transpose()


def _frame(rows: dict[str, list[float]], columns: Sequence[object] | None = None) -> pd.DataFrame:
    return _statement(rows, columns or QUARTERS)


def _without_rows(frame: pd.DataFrame, rows: list[str]) -> pd.DataFrame:
    untyped: Any = frame
    return untyped.drop(index=rows)


def _without_columns(frame: pd.DataFrame, columns: Sequence[object]) -> pd.DataFrame:
    untyped: Any = frame
    return untyped.drop(columns=columns)


def _oldest_first_with_an_older_quarter(frame: pd.DataFrame) -> pd.DataFrame:
    """Columns reordered oldest first, plus one quarter older than any of them."""
    untyped: Any = frame
    scrambled: Any = untyped[sorted(untyped.columns)]
    scrambled.insert(0, pd.Timestamp("2025-07-31"), 40_000e6)
    return scrambled


INCOME = _frame({"Total Revenue": [96_221e6, 81_615e6, 68_127e6, 57_006e6]})
CASHFLOW = _frame(
    {
        "Free Cash Flow": [21_400e6, 48_587e6, 34_904e6, 22_115e6],
        "Operating Cash Flow": [24_077e6, 50_344e6, 36_188e6, 23_751e6],
        "Capital Expenditure": [-2_677e6, -1_757e6, -1_284e6, -1_636e6],
    }
)
BALANCE = _frame({"Total Debt": [10_000e6] * 4, "Cash Cash Equivalents And Short Term Investments": [56_000e6] * 4})


def _snapshot(
    *,
    price: float | None = 224.03,
    shares: float | None = 24.40e9,
    income: pd.DataFrame = INCOME,
    cashflow: pd.DataFrame = CASHFLOW,
    balance: pd.DataFrame = BALANCE,
) -> TickerSnapshot:
    return build_snapshot("NVDA", price=price, shares=shares, currency="USD", income=income, cashflow=cashflow, balance=balance)


def test_ttm_figures_sum_the_last_four_quarters() -> None:
    snapshot = _snapshot()

    assert snapshot.revenue_ttm == pytest.approx(302.969e9)
    assert snapshot.fcf_ttm == pytest.approx(127.006e9)
    assert snapshot.fcf_margin == pytest.approx(0.4192, abs=1e-4)


def test_net_debt_is_debt_minus_cash_and_goes_negative_on_net_cash() -> None:
    assert _snapshot().net_debt == pytest.approx(10_000e6 - 56_000e6)


def test_missing_free_cash_flow_row_falls_back_to_operating_minus_capex() -> None:
    cashflow = _without_rows(CASHFLOW, ["Free Cash Flow"])

    snapshot = _snapshot(cashflow=cashflow)

    assert snapshot.fcf_ttm == pytest.approx(134.36e9 - 7.354e9, rel=1e-6)


def test_older_quarters_are_ignored_however_yahoo_orders_the_columns() -> None:
    scrambled = _oldest_first_with_an_older_quarter(INCOME)

    assert _snapshot(income=scrambled).revenue_ttm == pytest.approx(302.969e9)


def test_a_stub_with_fewer_than_four_quarters_is_refused() -> None:
    with pytest.raises(MarketDataError, match="only 2 quarters of revenue"):
        _snapshot(income=_frame({"Total Revenue": [10e6, 9e6]}, columns=QUARTERS[:2]))


def test_a_missing_share_count_is_refused() -> None:
    with pytest.raises(MarketDataError, match="no share count"):
        _snapshot(shares=None)


def test_a_debt_free_balance_sheet_means_zero_net_debt() -> None:
    assert _snapshot(balance=pd.DataFrame()).net_debt == 0.0


ANNUAL_YEARS = [pd.Timestamp(date) for date in ("2026-01-31", "2025-01-31", "2024-01-31", "2023-01-31")]
ANNUAL_INCOME = _statement({"Total Revenue": [215.9e9, 130.5e9, 60.9e9, 27.0e9]}, ANNUAL_YEARS)
ANNUAL_CASHFLOW = _statement({"Free Cash Flow": [96.7e9, 60.7e9, 27.0e9, 3.8e9]}, ANNUAL_YEARS)


def test_history_runs_oldest_first_with_margin_and_growth() -> None:
    history = build_history(ANNUAL_INCOME, ANNUAL_CASHFLOW)

    assert [point.year for point in history] == [2023, 2024, 2025, 2026]
    assert history[0].revenue_growth is None  # nothing on record before it
    assert history[1].revenue_growth == pytest.approx(60.9 / 27.0 - 1)
    assert history[-1].fcf_margin == pytest.approx(96.7 / 215.9)


def test_a_year_whose_cash_flow_is_missing_still_anchors_the_next_year_growth() -> None:
    # Yahoo frequently reports one more year of revenue than of cash flow.
    cashflow = _without_columns(ANNUAL_CASHFLOW, [ANNUAL_YEARS[3]])

    history = build_history(ANNUAL_INCOME, cashflow)

    assert [point.year for point in history] == [2024, 2025, 2026]
    assert history[0].revenue_growth == pytest.approx(60.9 / 27.0 - 1)


def test_history_falls_back_to_operating_minus_capex() -> None:
    cashflow = _statement(
        {"Operating Cash Flow": [100e9, 70e9, 30e9, 5e9], "Capital Expenditure": [-3e9, -2e9, -1e9, -0.5e9]},
        ANNUAL_YEARS,
    )

    history = build_history(ANNUAL_INCOME, cashflow)

    assert history[-1].fcf == pytest.approx(97e9)


def test_no_statements_means_no_history_rather_than_an_error() -> None:
    assert build_history(pd.DataFrame(), pd.DataFrame()) == []
