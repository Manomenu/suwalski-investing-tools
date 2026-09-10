import pytest
from suwalski_investing_cli.parsing import parse_rate, parse_segment


@pytest.mark.parametrize(
    ("text", "expected"),
    [("55%", 0.55), ("0.55", 0.55), (" 3 % ", 0.03), ("-5%", -0.05)],
)
def test_parse_rate(text, expected):
    assert parse_rate(text) == pytest.approx(expected)


def test_parse_segment_range():
    segment = parse_segment("1-3:55%")

    assert (segment.start_year, segment.end_year) == (1, 3)
    assert segment.growth == pytest.approx(0.55)


def test_parse_segment_single_year():
    segment = parse_segment("5:10%")

    assert (segment.start_year, segment.end_year) == (5, 5)


def test_parse_segment_without_rate_is_rejected():
    with pytest.raises(ValueError, match="expected YEARS:RATE"):
        parse_segment("1-3")


def test_parse_segment_rejects_a_backwards_range():
    with pytest.raises(ValueError):
        parse_segment("5-2:10%")
