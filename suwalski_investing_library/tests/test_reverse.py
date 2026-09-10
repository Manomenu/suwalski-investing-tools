import pytest
from suwalski_investing_library.contracts.valuation import GrowthSegment, ReverseDcfRequest
from suwalski_investing_library.valuation.engine import value_per_share
from suwalski_investing_library.valuation.errors import ValuationError
from suwalski_investing_library.valuation.reverse import solve_implied_growth


def _request(price: float, **overrides) -> ReverseDcfRequest:
    base = {
        "revenue": 100.0,
        "optimized_fcf_margin": 0.10,
        "shares_outstanding": 1.0,
        "discount_rate": 0.10,
        "terminal_growth": 0.02,
        "projection_years": 10,
        "growth_segments": [GrowthSegment(start_year=1, end_year=3, growth=0.40)],
    }
    return ReverseDcfRequest(**{**base, **overrides}, current_price=price)


def test_solved_growth_reproduces_the_price_it_was_solved_from():
    # Price the company at a known rate, then ask the solver to recover that rate.
    priced_at = value_per_share(_request(1.0), free_growth=0.113)

    result = solve_implied_growth(_request(priced_at))

    assert result.implied_growth == pytest.approx(0.113, abs=1e-9)
    assert result.residual_per_share == pytest.approx(0.0, abs=priced_at * 1e-9)


def test_only_the_uncovered_years_are_solved():
    result = solve_implied_growth(_request(400.0))

    assert result.solved_years == [4, 5, 6, 7, 8, 9, 10]
    assert [year.growth for year in result.projection.years[:3]] == [0.40] * 3
    assert {year.growth for year in result.projection.years[3:]} == {result.implied_growth}


def test_a_richer_price_demands_more_growth():
    cheap = solve_implied_growth(_request(300.0)).implied_growth
    rich = solve_implied_growth(_request(600.0)).implied_growth

    assert rich > cheap


def test_price_below_the_brackets_floor_is_reported_not_clamped():
    with pytest.raises(ValuationError, match="above the"):
        solve_implied_growth(_request(1.0))


def test_price_above_the_brackets_ceiling_is_reported_not_clamped():
    with pytest.raises(ValuationError, match="below the"):
        solve_implied_growth(_request(10_000_000.0))


def test_reference_screen_numbers_reproduce_its_published_answer():
    # Reference reverse-DCF screen for NVDA: $224.03 price, 24.40B shares, TTM FCF
    # $127.01B at a 42% margin, optimized FCF $106.04B at 35%, 55% growth in years 1-3,
    # 10% discount, 3% terminal growth. Its published answer for years 4-10 is 4.7%.
    result = solve_implied_growth(
        ReverseDcfRequest(
            revenue=127.01 / 0.42,
            optimized_fcf_margin=0.35,
            shares_outstanding=24.40,
            discount_rate=0.10,
            terminal_growth=0.03,
            projection_years=10,
            current_price=224.03,
            growth_segments=[GrowthSegment(start_year=1, end_year=3, growth=0.55)],
        )
    )

    assert result.implied_growth == pytest.approx(0.047, abs=0.001)
    assert result.implied_revenue_cagr == pytest.approx(0.178, abs=0.001)
