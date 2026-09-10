"""The projection the reverse solver iterates on: assumptions in, value per share out.

    revenue_t = revenue_0 * PROD(1 + g_i) for i in 1..t
    fcf_t     = revenue_t * margin_t
    PV        = SUM fcf_t / (1+r)^t  +  TV / (1+r)^N
    TV        = fcf_N * (1 + g_term) / (r - g_term)          [Gordon growth]
    equity    = PV - net_debt

Pure functions over the contracts — no I/O, no framework. The reverse solver in
`reverse.py` is a root find over `value_per_share`, so keep this side effect free.
"""

from typing import Literal

from suwalski_investing_library.contracts.valuation import Projection, ValuationInputs, YearProjection


def growth_path(inputs: ValuationInputs, free_growth: float) -> list[tuple[float, Literal["input", "solved"]]]:
    """Per-year (growth, source) for years 1..N; uncovered years get `free_growth`."""
    by_year = {year: segment.growth for segment in inputs.growth_segments for year in segment.years}
    return [(by_year[year], "input") if year in by_year else (free_growth, "solved") for year in range(1, inputs.projection_years + 1)]


def margin_path(inputs: ValuationInputs) -> list[float]:
    """Per-year FCF margin for years 1..N.

    Without a ramp every year runs at the optimized margin. With one, the margin walks
    linearly from today's margin to the optimized margin over `margin_ramp_years` and
    stays there — the terminal value therefore always rests on the optimized margin.
    """
    if not inputs.margin_ramp_years:
        return [inputs.optimized_fcf_margin] * inputs.projection_years

    start = inputs.current_fcf_margin
    assert start is not None  # guaranteed by ValuationInputs._consistent
    step = (inputs.optimized_fcf_margin - start) / inputs.margin_ramp_years
    return [start + step * min(year, inputs.margin_ramp_years) for year in range(1, inputs.projection_years + 1)]


def project(inputs: ValuationInputs, free_growth: float) -> Projection:
    """Run the full projection and discount it back."""
    rate = inputs.discount_rate
    margins = margin_path(inputs)

    revenue = inputs.revenue
    years: list[YearProjection] = []
    pv_explicit = 0.0

    for index, (growth, source) in enumerate(growth_path(inputs, free_growth)):
        year = index + 1
        revenue *= 1 + growth
        fcf = revenue * margins[index]
        discount_factor = 1 / (1 + rate) ** year
        present_value = fcf * discount_factor
        pv_explicit += present_value
        years.append(
            YearProjection(
                year=year,
                growth=growth,
                source=source,
                revenue=revenue,
                fcf_margin=margins[index],
                fcf=fcf,
                discount_factor=discount_factor,
                present_value=present_value,
            )
        )

    terminal_value = years[-1].fcf * (1 + inputs.terminal_growth) / (rate - inputs.terminal_growth)
    pv_terminal = terminal_value * years[-1].discount_factor
    enterprise_value = pv_explicit + pv_terminal
    equity_value = enterprise_value - inputs.net_debt

    return Projection(
        years=years,
        pv_explicit=pv_explicit,
        terminal_value=terminal_value,
        pv_terminal=pv_terminal,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        intrinsic_value_per_share=equity_value / inputs.shares_outstanding,
        revenue_cagr=(revenue / inputs.revenue) ** (1 / inputs.projection_years) - 1,
    )


def value_per_share(inputs: ValuationInputs, free_growth: float) -> float:
    """What the reverse solver iterates on."""
    return project(inputs, free_growth).intrinsic_value_per_share
