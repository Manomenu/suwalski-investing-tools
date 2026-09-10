"""Argument syntax for the CLI. Pure functions — argparse turns their ValueErrors into
usage errors, and the tests cover them directly.
"""

from suwalski_investing_library.contracts.valuation import GrowthSegment


def parse_rate(text: str) -> float:
    """`55%` -> 0.55, `0.55` -> 0.55.

    A bare number is a decimal fraction, never a percent — `0.55` and `55%` are the same
    rate, and `55` means 5500%. Explicit beats guessing at the magnitude.
    """
    text = text.strip()
    if text.endswith("%"):
        return float(text[:-1].strip()) / 100
    return float(text)


def parse_segment(text: str) -> GrowthSegment:
    """`1-3:55%` (years 1 through 3) or `5:10%` (year 5 alone)."""
    years, separator, rate = text.partition(":")
    if not separator:
        raise ValueError(f"expected YEARS:RATE (e.g. 1-3:40%), got {text!r}")

    start_text, dash, end_text = years.strip().partition("-")
    start = int(start_text)
    end = int(end_text) if dash else start

    return GrowthSegment(start_year=start, end_year=end, growth=parse_rate(rate))
