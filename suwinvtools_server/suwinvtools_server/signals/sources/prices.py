"""Closing share prices from Yahoo, through yfinance — for the one signal that values companies
(E1). Which day a quarter's price is taken on is the check's business; this only asks."""

from datetime import date, timedelta


def closing_price(ticker: str, day: date) -> float | None:
    """The last close on or before `day`, or None when Yahoo has no price for that stretch."""
    import yfinance  # pyright: ignore[reportMissingTypeStubs] — yfinance ships no stubs  # noqa: PLC0415 — heavy import, only E1 pays for it

    frame = yfinance.Ticker(ticker).history(start=day - timedelta(days=10), end=day + timedelta(days=1), auto_adjust=False)  # pyright: ignore[reportUnknownMemberType] — untyped library
    closes = frame["Close"].dropna()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] — pandas without stubs
    return float(closes.iloc[-1]) if len(closes) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType] — same
