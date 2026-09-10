"""Reverse DCF: hold the price fixed, solve for the growth it demands.

`f(g) = value_per_share(inputs, g) - price` is monotone in g (more growth, more value),
so a bisection on the requested bracket is enough — no numeric dependencies, and the
result is deterministic, which matters for the tests and for reproducing a saved run.
"""

from suwalski_investing_library.contracts.valuation import ReverseDcfRequest, ReverseDcfResult
from suwalski_investing_library.valuation.engine import project, value_per_share
from suwalski_investing_library.valuation.errors import ValuationError

# Bisection stops when the bracket is this narrow (0.0000001% of a growth point) or when
# the value gap is this small relative to the price — whichever comes first.
_GROWTH_TOLERANCE = 1e-12
_RELATIVE_TOLERANCE = 1e-12
_MAX_ITERATIONS = 200


def solve_implied_growth(request: ReverseDcfRequest) -> ReverseDcfResult:
    """Growth every uncovered year must compound at for intrinsic value to meet the price."""
    price = request.current_price
    low, high = request.growth_lower_bound, request.growth_upper_bound

    def gap(growth: float) -> float:
        return value_per_share(request, growth) - price

    gap_low, gap_high = gap(low), gap(high)
    if gap_low > 0 and gap_high > 0:
        raise ValuationError(
            f"even at {low:.1%} growth the model values the share at {value_per_share(request, low):,.2f} — above the "
            f"{price:,.2f} price. The price implies growth below the bracket floor; lower growth_lower_bound or revisit "
            "the margin, discount rate and terminal growth."
        )
    if gap_low < 0 and gap_high < 0:
        raise ValuationError(
            f"even at {high:.1%} growth the model values the share at {value_per_share(request, high):,.2f} — below the "
            f"{price:,.2f} price. No growth inside the bracket justifies today's price; raise growth_upper_bound if you "
            "believe the higher rate is plausible."
        )

    iterations = 0
    midpoint = (low + high) / 2
    for iterations in range(1, _MAX_ITERATIONS + 1):
        midpoint = (low + high) / 2
        gap_mid = gap(midpoint)
        if abs(gap_mid) <= price * _RELATIVE_TOLERANCE or (high - low) <= _GROWTH_TOLERANCE:
            break
        # Keep the sub-bracket whose ends still straddle zero.
        if (gap_mid > 0) == (gap_low > 0):
            low, gap_low = midpoint, gap_mid
        else:
            high, gap_high = midpoint, gap_mid

    projection = project(request, midpoint)

    return ReverseDcfResult(
        implied_growth=midpoint,
        solved_years=request.free_years,
        known_segments=request.growth_segments,
        implied_revenue_cagr=projection.revenue_cagr,
        current_price=price,
        projection=projection,
        iterations=iterations,
        residual_per_share=projection.intrinsic_value_per_share - price,
    )
