"""The cache accumulates years across fetches — EDGAR cannot serve a year range, so the
saving is in not calling it at all."""

import json

import pytest
from suwalski_investing_library.contracts.market import HistoryPoint
from suwalski_investing_library.marketdata.errors import MarketDataError
from suwalski_investing_library.marketdata.history import get_history


def _point(year: int, margin: float = 0.2) -> HistoryPoint:
    return HistoryPoint(year=year, revenue=100.0 * year, fcf=100.0 * year * margin, fcf_margin=margin)


class _Source:
    """A stand-in for SecEdgarSource / YahooAnnualSource."""

    def __init__(self, points, calls, name="stub", raises=None):
        self.name = name
        self._points = points
        self._calls = calls
        self._raises = raises

    def years(self, symbol, **kwargs):
        self._calls.append((self.name, symbol))
        if self._raises is not None:
            raise self._raises
        return self._points


def test_years_from_separate_fetches_are_merged(tmp_path):
    calls: list[str] = []
    get_history("NVDA", years=10, cache_dir=tmp_path, sources=(_Source([_point(y) for y in (2020, 2021, 2022)], calls),))

    # A later fetch that knows different years must not lose the earlier ones.
    merged = get_history("NVDA", years=10, cache_dir=tmp_path, ttl_seconds=0, sources=(_Source([_point(y) for y in (2022, 2023)], calls),))

    assert [point.year for point in merged] == [2020, 2021, 2022, 2023]
    assert len(calls) == 2


def test_a_covered_and_fresh_request_never_touches_the_network(tmp_path):
    calls: list[str] = []
    sources = (_Source([_point(y) for y in range(2017, 2027)], calls),)
    get_history("MSFT", years=10, cache_dir=tmp_path, sources=sources)

    again = get_history("MSFT", years=10, cache_dir=tmp_path, sources=sources)

    assert len(calls) == 1
    assert len(again) == 10


def test_widening_the_horizon_refetches_once_then_stops_asking(tmp_path):
    calls: list[str] = []
    sources = (_Source([_point(y) for y in range(2022, 2027)], calls),)
    get_history("NVDA", years=5, cache_dir=tmp_path, sources=sources)

    # 20 years wanted, 5 on disk: one fetch proves the filer has no more, and the flag it
    # leaves behind keeps the next request local.
    get_history("NVDA", years=20, cache_dir=tmp_path, sources=sources)
    get_history("NVDA", years=20, cache_dir=tmp_path, sources=sources)

    assert len(calls) == 2


def test_the_providers_own_history_is_merged_in_as_a_fallback(tmp_path):
    calls: list[str] = []

    history = get_history(
        "ASML",
        years=10,
        cache_dir=tmp_path,
        sources=(_Source([], calls, name="sec"),),  # EDGAR does not cover it
        seed=[_point(2024), _point(2025)],
    )

    assert [point.year for point in history] == [2024, 2025]


def test_a_failed_fetch_falls_back_to_what_is_already_stored(tmp_path):
    calls: list[str] = []
    get_history("KO", years=10, cache_dir=tmp_path, sources=(_Source([_point(2024), _point(2025)], calls),))

    history = get_history(
        "KO",
        years=10,
        cache_dir=tmp_path,
        ttl_seconds=0,
        sources=(_Source([], calls, raises=MarketDataError("SEC unreachable")),),
    )

    assert [point.year for point in history] == [2024, 2025]


def test_only_the_continuous_tail_is_returned(tmp_path):
    calls: list[str] = []
    scattered = [_point(y) for y in (2010, 2011, 2022, 2023, 2024)]

    history = get_history("NVDA", years=10, cache_dir=tmp_path, sources=(_Source(scattered, calls),))

    assert [point.year for point in history] == [2022, 2023, 2024]


def test_the_older_years_stay_in_the_cache_even_when_not_returned(tmp_path):
    calls: list[str] = []
    get_history("NVDA", years=10, cache_dir=tmp_path, sources=(_Source([_point(y) for y in (2010, 2022, 2023)], calls),))

    stored = json.loads((tmp_path / "history-NVDA.json").read_text())

    assert sorted(stored["years"]) == ["2010", "2022", "2023"]


def test_a_corrupt_cache_file_is_rebuilt_rather_than_raised(tmp_path):
    (tmp_path / "history-NVDA.json").write_text("{not json")
    calls: list[str] = []

    history = get_history("NVDA", years=5, cache_dir=tmp_path, sources=(_Source([_point(2025)], calls),))

    assert [point.year for point in history] == [2025]


@pytest.mark.parametrize("symbol", ["nvda", " NVDA "])
def test_symbols_are_normalised_to_one_cache_file(symbol, tmp_path):
    calls: list[str] = []
    get_history(symbol, years=5, cache_dir=tmp_path, sources=(_Source([_point(2025)], calls),))

    assert [path.name for path in tmp_path.iterdir()] == ["history-NVDA.json"]


def test_sources_are_asked_in_order_and_their_years_merged(tmp_path):
    calls: list[tuple[str, str]] = []
    long_source = _Source([_point(y) for y in (2016, 2017)], calls, name="sec")
    short_source = _Source([_point(y) for y in (2018, 2019)], calls, name="yahoo")

    history = get_history("KO", years=10, cache_dir=tmp_path, sources=(long_source, short_source))

    assert [name for name, _ in calls] == ["sec", "yahoo"]
    assert [point.year for point in history] == [2016, 2017, 2018, 2019]


def test_a_source_that_already_covers_the_horizon_short_circuits_the_rest(tmp_path):
    calls: list[tuple[str, str]] = []
    sources = (
        _Source([_point(y) for y in range(2017, 2027)], calls, name="sec"),
        _Source([_point(2026)], calls, name="yahoo"),
    )

    get_history("MSFT", years=10, cache_dir=tmp_path, sources=sources)

    assert [name for name, _ in calls] == ["sec"]


def test_a_seed_that_covers_the_horizon_reaches_no_source_at_all(tmp_path):
    calls: list[tuple[str, str]] = []

    history = get_history(
        "MSFT",
        years=4,
        cache_dir=tmp_path,
        sources=(_Source([_point(2026)], calls, name="sec"),),
        seed=[_point(y) for y in (2022, 2023, 2024, 2025)],
    )

    assert calls == []
    assert [point.year for point in history] == [2022, 2023, 2024, 2025]
