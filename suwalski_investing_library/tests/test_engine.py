import pytest
from suwalski_investing_library.contracts.valuation import GrowthSegment, ValuationInputs
from suwalski_investing_library.valuation.engine import growth_path, margin_path, project


def _inputs(**overrides) -> ValuationInputs:
    base = {
        "revenue": 100.0,
        "optimized_fcf_margin": 0.10,
        "shares_outstanding": 1.0,
        "discount_rate": 0.10,
        "terminal_growth": 0.0,
        "projection_years": 10,
    }
    return ValuationInputs(**{**base, **overrides})


def test_flat_perpetuity_values_at_fcf_over_discount_rate():
    # No growth, no terminal growth: the whole thing collapses to FCF / r = 10 / 0.10.
    result = project(_inputs(), free_growth=0.0)

    assert result.enterprise_value == pytest.approx(100.0)
    assert result.intrinsic_value_per_share == pytest.approx(100.0)
    assert result.pv_explicit == pytest.approx(61.4457, abs=1e-4)
    assert result.pv_terminal == pytest.approx(38.5543, abs=1e-4)


def test_growth_segments_win_over_the_solved_rate():
    inputs = _inputs(growth_segments=[GrowthSegment(start_year=1, end_year=3, growth=0.40)])

    path = growth_path(inputs, free_growth=0.05)

    assert path[:3] == [(0.40, "input")] * 3
    assert path[3:] == [(0.05, "solved")] * 7


def test_revenue_compounds_year_over_year():
    inputs = _inputs(growth_segments=[GrowthSegment(start_year=1, end_year=3, growth=0.40)])

    years = project(inputs, free_growth=0.05).years

    assert years[0].revenue == pytest.approx(140.0)
    assert years[2].revenue == pytest.approx(100 * 1.4**3)
    assert years[3].revenue == pytest.approx(100 * 1.4**3 * 1.05)
    assert years[3].fcf == pytest.approx(years[3].revenue * 0.10)


def test_margin_ramps_linearly_then_holds_at_optimized():
    inputs = _inputs(optimized_fcf_margin=0.20, current_fcf_margin=0.40, margin_ramp_years=5)

    margins = margin_path(inputs)

    assert margins[0] == pytest.approx(0.36)
    assert margins[4] == pytest.approx(0.20)
    assert margins[9] == pytest.approx(0.20)


def test_no_ramp_applies_the_optimized_margin_from_year_one():
    # The reverse-DCF screens work this way: "optimized FCF" is the base, not a target.
    assert margin_path(_inputs(current_fcf_margin=0.42)) == [0.10] * 10


def test_net_debt_and_share_count_land_on_the_per_share_value():
    result = project(_inputs(net_debt=40.0, shares_outstanding=2.0), free_growth=0.0)

    assert result.equity_value == pytest.approx(60.0)
    assert result.intrinsic_value_per_share == pytest.approx(30.0)


def test_revenue_cagr_blends_the_known_and_solved_years():
    inputs = _inputs(projection_years=4, growth_segments=[GrowthSegment(start_year=1, end_year=2, growth=0.50)])

    result = project(inputs, free_growth=0.10)

    assert result.revenue_cagr == pytest.approx((1.5**2 * 1.1**2) ** 0.25 - 1)
