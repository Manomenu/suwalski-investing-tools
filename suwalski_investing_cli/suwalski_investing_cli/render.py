"""Terminal rendering of a valuation result. Text only — no colors, so the output stays
readable when piped into a file or a diff."""

from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.contracts.valuation import Projection, ReverseDcfResult
from suwalski_investing_library.marketdata.provider import age_seconds

_HEADER = f"{'YEAR':>4}  {'GROWTH':>8}  {'SOURCE':<7}  {'REVENUE':>13}  {'MARGIN':>7}  {'FCF':>13}  {'PV':>13}"


def render_projection(result: Projection) -> str:
    lines = [_HEADER, "-" * len(_HEADER)]
    for year in result.years:
        lines.append(
            f"{year.year:>4}  {year.growth:>7.2%}  {year.source:<7}  {_humanize(year.revenue):>13}  "
            f"{year.fcf_margin:>6.1%}  {_humanize(year.fcf):>13}  {_humanize(year.present_value):>13}"
        )
    return "\n".join(lines)


def render_summary(result: Projection) -> str:
    rows = [
        ("PV of projected years", _humanize(result.pv_explicit)),
        ("PV of terminal value", _humanize(result.pv_terminal)),
        ("Enterprise value", _humanize(result.enterprise_value)),
        ("Equity value", _humanize(result.equity_value)),
        ("Revenue CAGR", f"{result.revenue_cagr:.2%}"),
        ("Intrinsic value / share", f"{result.intrinsic_value_per_share:,.2f}"),
    ]

    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label:<{width}}  {value:>16}" for label, value in rows)


def render_reverse(result: ReverseDcfResult) -> str:
    segments = sorted(result.known_segments, key=lambda segment: segment.start_year)
    labels = [f"{segment.start_year}-{segment.end_year}" for segment in segments]
    solved = _compact_years(result.solved_years)
    width = max(len(label) for label in [*labels, solved])

    known = [f"  years {label:<{width}}  {segment.growth:>7.2%}   your input" for label, segment in zip(labels, segments, strict=True)]
    return "\n".join(
        [
            "GROWTH THE PRICE REQUIRES",
            *known,
            f"  years {solved:<{width}}  {result.implied_growth:>7.2%}   <- solved",
            "",
            f"  implied revenue CAGR over {len(result.projection.years)} years: {result.implied_revenue_cagr:.2%}",
            (
                f"  at that path intrinsic value is {result.projection.intrinsic_value_per_share:,.2f} "
                f"against a {result.current_price:,.2f} price"
            ),
        ]
    )


def _compact_years(years: list[int]) -> str:
    if not years:
        return "-"
    if years == list(range(years[0], years[-1] + 1)):
        return f"{years[0]}-{years[-1]}"
    return ",".join(str(year) for year in years)


def render_snapshot(snapshot: TickerSnapshot) -> str:
    """The fetched facts, echoed back so it's obvious what the valuation was fed."""
    age = age_seconds(snapshot)
    currency = f" {snapshot.currency}" if snapshot.currency else ""
    return "\n".join(
        [
            (
                f"{snapshot.ticker}  price {snapshot.price:,.2f}{currency}  "
                f"shares {_humanize(snapshot.shares_outstanding)}  market cap {_humanize(snapshot.market_cap)}"
            ),
            (
                f"  revenue TTM {_humanize(snapshot.revenue_ttm)}   "
                f"FCF TTM {_humanize(snapshot.fcf_ttm)} ({snapshot.fcf_margin:.1%})   "
                f"net debt {_humanize(snapshot.net_debt)}"
            ),
            f"  [{snapshot.source}, fetched {_age(age)}]",
        ]
    )


def _humanize(value: float) -> str:
    for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= scale:
            return f"{value / scale:,.2f}{suffix}"
    return f"{value:,.2f}"


def _age(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min ago"
    return f"{seconds / 3600:.1f} h ago"
