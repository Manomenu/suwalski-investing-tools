"""Contract for the numbers a ticker can supply. Filled by suwalski_investing_marketdata,
consumed by the CLI and the API — defined here so neither side owns it.

Only observable facts live here. Assumptions (optimized margin, growth, discount rate,
terminal growth) are yours and never come from a data provider.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class TickerSnapshot(BaseModel):
    ticker: str
    price: float = Field(gt=0, description="last traded price per share")
    shares_outstanding: float = Field(gt=0)
    revenue_ttm: float = Field(gt=0, description="sum of the last four reported quarters")
    fcf_ttm: float = Field(description="trailing twelve month free cash flow; can be negative")
    net_debt: float = Field(description="total debt minus cash and short-term investments; negative means net cash")
    currency: str | None = None
    as_of: datetime = Field(description="when the snapshot was fetched, UTC")
    source: str = Field(description="provider that produced it, e.g. 'yfinance'")

    @property
    def fcf_margin(self) -> float:
        return self.fcf_ttm / self.revenue_ttm

    @property
    def market_cap(self) -> float:
        return self.price * self.shares_outstanding
