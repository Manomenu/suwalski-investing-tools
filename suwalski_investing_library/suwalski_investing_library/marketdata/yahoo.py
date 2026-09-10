"""Yahoo Finance reader.

yfinance is an unofficial scraper: row labels move around and statements come back empty
for symbols Yahoo does not cover. Everything here is therefore defensive — rows are looked
up by a list of known aliases, and anything missing turns into a MarketDataError naming the
field rather than a KeyError or a silent NaN in a valuation.

`build_snapshot` is kept pure (it takes plain frames) so the tests cover the statement
arithmetic without touching the network.
"""

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from suwalski_investing_library.contracts.market import HistoryPoint, TickerSnapshot
from suwalski_investing_library.marketdata.errors import MarketDataError, UnknownTickerError

SOURCE = "yfinance"
_QUARTERS_PER_YEAR = 4


def fetch_snapshot(ticker: str) -> TickerSnapshot:
    """Read one symbol off Yahoo Finance. Network call — cache it (see `provider.py`)."""
    import yfinance

    symbol = ticker.strip().upper()
    handle = yfinance.Ticker(symbol)

    # Statements first, on purpose: for an unknown symbol yfinance's `fast_info` blows up
    # with a KeyError deep inside its own quote parsing, and reporting that as an upstream
    # failure would hide the real answer — there is no such company.
    income = _statement(handle, symbol, "quarterly_income_stmt")
    if income.empty:
        raise UnknownTickerError(f"Yahoo Finance has no financial statements for {symbol}")

    cashflow = _statement(handle, symbol, "quarterly_cashflow")
    balance = _statement(handle, symbol, "quarterly_balance_sheet")
    price, shares, currency = _quote(handle, symbol)

    # Annual statements are a separate request; they carry the reported-year history that
    # the UI charts. Yahoo returns four or five years, so the history is simply as long as
    # it is — a missing one is not worth failing a valuation over.
    annual_income = _statement(handle, symbol, "income_stmt")
    annual_cashflow = _statement(handle, symbol, "cashflow")

    return build_snapshot(
        symbol,
        price=price,
        shares=shares,
        currency=currency,
        income=income,
        cashflow=cashflow,
        balance=balance,
        history=build_history(annual_income, annual_cashflow),
    )


def _statement(handle: Any, symbol: str, attribute: str) -> pd.DataFrame:
    try:
        frame = getattr(handle, attribute)
    except Exception as exc:  # yfinance raises anything from HTTP errors to KeyErrors
        raise MarketDataError(f"Yahoo Finance lookup for {symbol} failed: {exc}") from exc
    return pd.DataFrame() if frame is None else frame


# yfinance ships no type information, so its handle stays untyped on purpose.
def _quote(handle: Any, symbol: str) -> tuple[float, float | None, str | None]:
    try:
        fast_info = handle.fast_info
        price = fast_info.get("lastPrice")
        shares = fast_info.get("shares")
        currency = fast_info.get("currency")
    except Exception as exc:
        raise MarketDataError(f"Yahoo Finance returned no quote for {symbol}: {exc}") from exc

    if not price:
        raise MarketDataError(f"Yahoo Finance returned no price for {symbol}")
    return price, shares, currency


def build_snapshot(
    symbol: str,
    *,
    price: float | None,
    shares: float | None,
    currency: str | None,
    income: pd.DataFrame,
    cashflow: pd.DataFrame,
    balance: pd.DataFrame,
    history: list[HistoryPoint] | None = None,
) -> TickerSnapshot:
    """Turn raw statements into a snapshot. Pure — no network, no clock beyond `as_of`."""
    if not price:
        raise MarketDataError(f"Yahoo Finance reported no price for {symbol}")
    if not shares:
        raise MarketDataError(f"Yahoo Finance reported no share count for {symbol}")

    revenue_ttm = _ttm(symbol, income, "revenue", "Total Revenue", "Operating Revenue")

    # Yahoo publishes a Free Cash Flow row for most companies; where it is missing, fall
    # back to the definition (capital expenditure comes through negative).
    try:
        fcf_ttm = _ttm(symbol, cashflow, "free cash flow", "Free Cash Flow")
    except MarketDataError:
        operating = _ttm(symbol, cashflow, "operating cash flow", "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
        capex = _ttm(symbol, cashflow, "capital expenditure", "Capital Expenditure")
        fcf_ttm = operating - abs(capex)

    return TickerSnapshot(
        ticker=symbol,
        price=float(price),
        shares_outstanding=float(shares),
        revenue_ttm=revenue_ttm,
        fcf_ttm=fcf_ttm,
        net_debt=_net_debt(balance),
        currency=currency,
        as_of=datetime.now(UTC),
        source=SOURCE,
        history=history or [],
    )


class YahooAnnualSource:
    """Yahoo's four or five annual years. Short, but it covers filers EDGAR never sees —
    anything listed outside the US, Warsaw included."""

    name = "yahoo-annual"

    def years(self, symbol: str, **_: object) -> list[HistoryPoint]:
        import yfinance

        handle = yfinance.Ticker(symbol.strip().upper())
        return build_history(
            _statement(handle, symbol, "income_stmt"),
            _statement(handle, symbol, "cashflow"),
        )


def build_history(annual_income: pd.DataFrame, annual_cashflow: pd.DataFrame) -> list[HistoryPoint]:
    """Reported fiscal years, oldest first, for the margin and growth charts.

    Years Yahoo cannot supply both revenue and free cash flow for are dropped rather than
    guessed at — a gap in a history chart is honest, an invented point is not.
    """
    revenue = _row(annual_income, "Total Revenue", "Operating Revenue")
    if revenue is None:
        return []

    fcf = _row(annual_cashflow, "Free Cash Flow")
    if fcf is None:
        operating = _row(annual_cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
        capex = _row(annual_cashflow, "Capital Expenditure")
        fcf = None if operating is None or capex is None else operating - capex.abs()
    if fcf is None:
        return []

    # Growth walks the full revenue series, so a year whose cash-flow row is missing still
    # anchors the growth of the year after it — Yahoo often carries one more year of revenue
    # than of cash flow.
    points: list[HistoryPoint] = []
    previous: float | None = None
    for date in sorted(revenue.index):
        reported = float(revenue[date])
        if reported <= 0:
            continue
        growth = None if previous is None else reported / previous - 1
        previous = reported
        if date not in fcf.index:
            continue
        cash = float(fcf[date])
        points.append(
            HistoryPoint(
                year=date.year,
                revenue=reported,
                fcf=cash,
                fcf_margin=cash / reported,
                revenue_growth=growth,
            )
        )
    return points


def _net_debt(balance: pd.DataFrame) -> float:
    """Total debt minus cash. Absent debt or cash lines mean zero, not a failed snapshot —
    a debt-free balance sheet simply has no such row."""
    debt = _latest_or_none(balance, "Total Debt")
    cash = _latest_or_none(balance, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
    if debt is None and cash is None:
        reported = _latest_or_none(balance, "Net Debt")
        return reported if reported is not None else 0.0
    return (debt or 0.0) - (cash or 0.0)


def _row(frame: pd.DataFrame, *names: str) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    for name in names:
        if name in frame.index:
            series = frame.loc[name].dropna()
            if not series.empty:
                # Columns are report dates; newest first, whatever order Yahoo sent them in.
                return series.sort_index(ascending=False)
    return None


def _ttm(symbol: str, frame: pd.DataFrame, label: str, *names: str) -> float:
    series = _row(frame, *names)
    if series is None:
        raise MarketDataError(f"Yahoo Finance reported no {label} for {symbol}")
    if len(series) < _QUARTERS_PER_YEAR:
        raise MarketDataError(
            f"only {len(series)} quarters of {label} available for {symbol} — not enough for a trailing twelve month figure"
        )
    return float(series.iloc[:_QUARTERS_PER_YEAR].sum())


def _latest_or_none(frame: pd.DataFrame, *names: str) -> float | None:
    series = _row(frame, *names)
    return None if series is None else float(series.iloc[0])
