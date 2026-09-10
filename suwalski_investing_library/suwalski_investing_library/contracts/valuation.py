"""Contracts for the reverse-DCF calculator — shared by the server API and the CLI.

Rates are decimal fractions, not percents: 0.4 == +40% a year. Money units are free-form
(dollars, billions, whatever), as long as revenue, net debt and share count use the same one.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GrowthSegment(BaseModel):
    """A growth assumption pinned to a closed range of projection years (1-based, inclusive)."""

    start_year: int = Field(ge=1)
    end_year: int = Field(ge=1)
    growth: float = Field(gt=-1.0)

    @model_validator(mode="after")
    def _ordered(self) -> "GrowthSegment":
        if self.end_year < self.start_year:
            raise ValueError(f"segment ends before it starts: {self.start_year}-{self.end_year}")
        return self

    @property
    def years(self) -> range:
        return range(self.start_year, self.end_year + 1)


class ValuationInputs(BaseModel):
    """Everything the projection needs except the growth of the years left to the solver.

    The cash-flow driver is revenue: revenue compounds at the per-year growth rate and the
    FCF margin turns it into cash. With the default `margin_ramp_years=0` the optimized
    margin applies from year 1 (so year 1 FCF = revenue * optimized_fcf_margin * (1+g1)),
    which is what the "optimized free cash flow" input of a reverse-DCF screen means.
    """

    revenue: float = Field(gt=0, description="TTM revenue — model year 0")
    optimized_fcf_margin: float = Field(gt=0, le=1, description="FCF margin the business is expected to run at")
    current_fcf_margin: float | None = Field(default=None, gt=0, le=1, description="TTM FCF margin; only used when ramping")
    margin_ramp_years: int = Field(default=0, ge=0, description="0 = optimized margin from year 1; N = linear ramp over N years")

    shares_outstanding: float = Field(gt=0)
    net_debt: float = Field(default=0.0, description="debt minus cash; negative means net cash")

    discount_rate: float = Field(gt=0, lt=1)
    terminal_growth: float = Field(gt=-1.0)
    projection_years: int = Field(default=10, ge=1, le=50)

    growth_segments: list[GrowthSegment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "ValuationInputs":
        if self.terminal_growth >= self.discount_rate:
            raise ValueError(
                f"terminal_growth ({self.terminal_growth}) must stay below discount_rate ({self.discount_rate}) — "
                "the Gordon terminal value diverges otherwise"
            )
        if self.margin_ramp_years and self.current_fcf_margin is None:
            raise ValueError("current_fcf_margin is required when margin_ramp_years > 0")

        seen: set[int] = set()
        for segment in self.growth_segments:
            if segment.end_year > self.projection_years:
                raise ValueError(f"segment {segment.start_year}-{segment.end_year} runs past projection_years ({self.projection_years})")
            for year in segment.years:
                if year in seen:
                    raise ValueError(f"year {year} is covered by two growth segments")
                seen.add(year)
        return self

    @property
    def known_years(self) -> set[int]:
        return {year for segment in self.growth_segments for year in segment.years}

    @property
    def free_years(self) -> list[int]:
        """Projection years with no growth assumption — what the solver fills in."""
        known = self.known_years
        return [year for year in range(1, self.projection_years + 1) if year not in known]


class ReverseDcfRequest(ValuationInputs):
    """Solve the growth of the uncovered years that justifies today's price."""

    current_price: float = Field(gt=0)
    growth_lower_bound: float = Field(default=-0.9, gt=-1.0, description="solver bracket floor")
    growth_upper_bound: float = Field(default=3.0, description="solver bracket ceiling")

    @model_validator(mode="after")
    def _solvable(self) -> "ReverseDcfRequest":
        if not self.free_years:
            raise ValueError(f"growth segments cover all {self.projection_years} years — leave at least one year open for the solver")
        if self.growth_upper_bound <= self.growth_lower_bound:
            raise ValueError("growth_upper_bound must exceed growth_lower_bound")
        return self


class YearProjection(BaseModel):
    year: int
    growth: float
    source: Literal["input", "solved"]
    revenue: float
    fcf_margin: float
    fcf: float
    discount_factor: float
    present_value: float


class Projection(BaseModel):
    """The cash-flow path and its present value, at one particular growth assumption."""

    years: list[YearProjection]
    pv_explicit: float = Field(description="present value of the explicit projection years")
    terminal_value: float
    pv_terminal: float
    enterprise_value: float
    equity_value: float
    intrinsic_value_per_share: float
    revenue_cagr: float


class ReverseDcfResult(BaseModel):
    implied_growth: float = Field(description="the rate every uncovered year must compound at to justify the price")
    solved_years: list[int]
    known_segments: list[GrowthSegment]
    implied_revenue_cagr: float = Field(description="CAGR of the whole path, known years included")
    current_price: float
    projection: Projection
    iterations: int
    residual_per_share: float = Field(description="intrinsic value minus price at the solution; the solver's tolerance")
