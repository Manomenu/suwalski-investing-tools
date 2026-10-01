"""MCP surface over the same library the HTTP API uses — for a chat assistant, not a browser.

Three tools: the two reported-history views the web UI charts, and the reverse DCF itself.
Like the routers, this is an adapter: it fetches a snapshot, merges what the caller typed
over it, and calls one library function. No number is computed here.

Served over Streamable HTTP at /mcp, stateless and JSON-only, so it scales with the server's
replicas and passes through any proxy without SSE buffering surprises.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.contracts.valuation import GrowthSegment, ReverseDcfRequest, ReverseDcfResult
from suwalski_investing_library.marketdata.errors import MarketDataError
from suwalski_investing_library.marketdata.provider import get_snapshot
from suwalski_investing_library.valuation.errors import ValuationError
from suwalski_investing_library.valuation.reverse import solve_implied_growth

from suwalski_investing_server.settings import settings

_INSTRUCTIONS = """\
Reverse-DCF toolkit for listed companies. Use it whenever the user asks what growth a stock
price implies, whether a valuation is stretched, or how a company's FCF margin or revenue
growth developed historically.

The core idea: instead of guessing every year and producing a target price, `reverse_dcf`
takes today's price and solves the ONE growth rate the years the user left open must
compound at for intrinsic value to equal the price. The output is a number to argue with
("years 4-10 must grow 4.8% a year") — not a forecast and not advice.

How to use the tools well:
- Before choosing an optimized FCF margin or growth assumptions, call `fcf_margin_history`
  and `revenue_history` for the ticker, so the assumptions are anchored in what the company
  actually reported. Mention that context when presenting the result.
- Facts (price, shares, TTM revenue, net debt, today's FCF margin) are fetched from the
  ticker. Assumptions (optimized_fcf_margin, growth_segments, discount_rate,
  terminal_growth) belong to the user. If the user did not state them, pick defensible
  values from the history, say explicitly which values you chose and why, and offer to
  rerun with theirs.
- All rates are decimal fractions: 0.12 means 12%. Never pass 12 for 12%.
- Money units only need to be consistent with each other; the fetched figures are in the
  company's reporting currency, in full units.
- Tickers use Yahoo symbols: MSFT, NVDA, ASML, Warsaw listings as CDR.WA, PKO.WA.
- History comes from SEC EDGAR (up to 10 years, US filers and ADRs) with Yahoo as the
  fallback (about 4 years, every other market).
"""

mcp = MCPServer(name="suwalski-investing-tools", instructions=_INSTRUCTIONS)

_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


class FcfMarginYear(BaseModel):
    year: int = Field(description="fiscal year")
    fcf_margin: float = Field(description="free cash flow / revenue, decimal fraction")
    fcf: float
    revenue: float


class FcfMarginHistory(BaseModel):
    ticker: str
    currency: str | None
    years: list[FcfMarginYear] = Field(description="oldest first")


class RevenueYear(BaseModel):
    year: int = Field(description="fiscal year")
    revenue: float
    revenue_growth: float | None = Field(description="growth over the previous year, decimal fraction; null for the oldest year")


class RevenueHistory(BaseModel):
    ticker: str
    currency: str | None
    years: list[RevenueYear] = Field(description="oldest first")


class MarketFacts(BaseModel):
    """The fetched facts the valuation started from, before any of the caller's overrides."""

    ticker: str
    price: float
    shares_outstanding: float
    revenue_ttm: float
    fcf_ttm: float
    fcf_margin_ttm: float
    net_debt: float
    currency: str | None
    source: str


class ReverseDcfAnswer(BaseModel):
    market: MarketFacts | None = Field(description="what the ticker supplied; null when every fact was typed in")
    request: ReverseDcfRequest = Field(description="the exact inputs that were solved")
    result: ReverseDcfResult


@mcp.tool(annotations=_READ_ONLY)
def fcf_margin_history(ticker: str, refresh: bool = False) -> FcfMarginHistory:
    """Reported free-cash-flow margin per fiscal year for a company, oldest first.

    Use it to judge whether an optimized FCF margin is realistic — a 35% assumption reads
    differently beside a decade of 20%. `refresh` skips the 15-minute snapshot cache.
    """
    with _anticipated():
        snapshot = _snapshot(ticker, refresh)
    return FcfMarginHistory(
        ticker=snapshot.ticker,
        currency=snapshot.currency,
        years=[FcfMarginYear(year=p.year, fcf_margin=p.fcf_margin, fcf=p.fcf, revenue=p.revenue) for p in snapshot.history],
    )


@mcp.tool(annotations=_READ_ONLY)
def revenue_history(ticker: str, refresh: bool = False) -> RevenueHistory:
    """Reported revenue and year-over-year revenue growth per fiscal year, oldest first.

    Use it to judge whether the growth a price implies is plausible against what the
    company has actually delivered. `refresh` skips the 15-minute snapshot cache.
    """
    with _anticipated():
        snapshot = _snapshot(ticker, refresh)
    return RevenueHistory(
        ticker=snapshot.ticker,
        currency=snapshot.currency,
        years=[RevenueYear(year=p.year, revenue=p.revenue, revenue_growth=p.revenue_growth) for p in snapshot.history],
    )


@mcp.tool(annotations=_READ_ONLY)
def reverse_dcf(
    optimized_fcf_margin: Annotated[
        float,
        Field(gt=0, le=1, description="FCF margin the business settles at, decimal (0.30 = 30%). The biggest lever and a bet, not a fact"),
    ],
    ticker: Annotated[str | None, Field(description="Yahoo symbol; fills price, shares, revenue, net debt and today's margin")] = None,
    growth_segments: Annotated[
        list[GrowthSegment] | None,
        Field(
            description="growth the user asserts per year range, e.g. [{start_year:1,end_year:3,growth:0.25}]. Every uncovered year is solved"
        ),
    ] = None,
    discount_rate: Annotated[float, Field(description="required annual return, decimal")] = 0.10,
    terminal_growth: Annotated[
        float, Field(description="perpetual growth after the last year, decimal; must stay below discount_rate")
    ] = 0.025,
    projection_years: Annotated[int, Field(ge=1, le=50)] = 10,
    margin_ramp_years: Annotated[
        int, Field(ge=0, description="0 = optimized margin from year 1; N = walk to it linearly from today's margin")
    ] = 0,
    price: Annotated[float | None, Field(description="overrides the fetched price")] = None,
    shares_outstanding: Annotated[float | None, Field(description="overrides the fetched share count")] = None,
    revenue: Annotated[float | None, Field(description="TTM revenue; overrides the fetched one")] = None,
    net_debt: Annotated[float | None, Field(description="debt minus cash, negative = net cash; overrides the fetched one")] = None,
    current_fcf_margin: Annotated[
        float | None, Field(description="today's FCF margin, only used when ramping; overrides the fetched one")
    ] = None,
    refresh: bool = False,
) -> ReverseDcfAnswer:
    """Solve the revenue growth today's share price requires, for the years left open.

    Pin the growth you have a view on in `growth_segments`; every other projection year
    gets one shared rate, found so that intrinsic value per share equals the price. The
    answer is `result.implied_growth`, with the full year-by-year projection beside it.
    Give a `ticker` to fetch the facts, or pass price, shares_outstanding and revenue by
    hand. Explicit values always win over fetched ones.
    """
    with _anticipated():
        snapshot = _snapshot(ticker, refresh) if ticker else None

        if snapshot is not None:
            # A negative TTM margin is a fact, not a usable ramp start — the contract needs a
            # positive one, and only when ramping, so it is dropped rather than failed on.
            fetched_margin = snapshot.fcf_margin if snapshot.fcf_margin > 0 else None
            price = _pick(price, snapshot.price)
            shares_outstanding = _pick(shares_outstanding, snapshot.shares_outstanding)
            revenue = _pick(revenue, snapshot.revenue_ttm)
            net_debt = _pick(net_debt, snapshot.net_debt)
            current_fcf_margin = _pick(current_fcf_margin, fetched_margin)

        if price is None or shares_outstanding is None or revenue is None:
            raise ValueError("give a ticker, or price, shares_outstanding and revenue")

        request = ReverseDcfRequest(
            revenue=revenue,
            optimized_fcf_margin=optimized_fcf_margin,
            current_fcf_margin=current_fcf_margin,
            margin_ramp_years=margin_ramp_years,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt or 0.0,
            discount_rate=discount_rate,
            terminal_growth=terminal_growth,
            projection_years=projection_years,
            growth_segments=growth_segments or [],
            current_price=price,
        )
        return ReverseDcfAnswer(market=_facts(snapshot) if snapshot else None, request=request, result=solve_implied_growth(request))


@contextmanager
def _anticipated() -> Iterator[None]:
    """Failures the caller can act on reach the model with their message; anything else
    stays a crash, whose text the SDK keeps on the server. Same split as the HTTP handlers."""
    try:
        yield
    except (ValueError, ValuationError, MarketDataError) as exc:  # ValidationError is a ValueError
        raise ToolError(str(exc)) from exc


def _snapshot(ticker: str, refresh: bool) -> TickerSnapshot:
    return get_snapshot(ticker, ttl_seconds=settings.market_cache_ttl_seconds, refresh=refresh)


def _pick(explicit: float | None, fetched: float | None) -> float | None:
    return explicit if explicit is not None else fetched


def _facts(snapshot: TickerSnapshot) -> MarketFacts:
    return MarketFacts(
        ticker=snapshot.ticker,
        price=snapshot.price,
        shares_outstanding=snapshot.shares_outstanding,
        revenue_ttm=snapshot.revenue_ttm,
        fcf_ttm=snapshot.fcf_ttm,
        fcf_margin_ttm=snapshot.fcf_margin,
        net_debt=snapshot.net_debt,
        currency=snapshot.currency,
        source=snapshot.source,
    )
