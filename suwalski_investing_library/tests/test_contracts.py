import pytest
from pydantic import ValidationError
from suwalski_investing_library.contracts.valuation import GrowthSegment, ReverseDcfRequest, ValuationInputs

BASE = {
    "revenue": 100.0,
    "optimized_fcf_margin": 0.10,
    "shares_outstanding": 1.0,
    "discount_rate": 0.10,
    "terminal_growth": 0.02,
    "projection_years": 10,
}


def test_free_years_are_the_ones_no_segment_covers():
    inputs = ValuationInputs(
        **BASE,
        growth_segments=[
            GrowthSegment(start_year=1, end_year=3, growth=0.4),
            GrowthSegment(start_year=8, end_year=8, growth=0.1),
        ],
    )

    assert inputs.free_years == [4, 5, 6, 7, 9, 10]


def test_overlapping_segments_are_rejected():
    with pytest.raises(ValidationError, match="covered by two growth segments"):
        ValuationInputs(
            **BASE,
            growth_segments=[
                GrowthSegment(start_year=1, end_year=4, growth=0.4),
                GrowthSegment(start_year=3, end_year=5, growth=0.2),
            ],
        )


def test_segment_past_the_horizon_is_rejected():
    with pytest.raises(ValidationError, match="runs past projection_years"):
        ValuationInputs(**BASE, growth_segments=[GrowthSegment(start_year=9, end_year=12, growth=0.1)])


def test_terminal_growth_must_stay_below_the_discount_rate():
    with pytest.raises(ValidationError, match="must stay below discount_rate"):
        ValuationInputs(**{**BASE, "terminal_growth": 0.10})


def test_ramp_requires_todays_margin():
    with pytest.raises(ValidationError, match="current_fcf_margin is required"):
        ValuationInputs(**BASE, margin_ramp_years=5)


def test_reverse_run_needs_a_year_left_open():
    with pytest.raises(ValidationError, match="leave at least one year open"):
        ReverseDcfRequest(
            **BASE,
            current_price=50.0,
            growth_segments=[GrowthSegment(start_year=1, end_year=10, growth=0.4)],
        )
