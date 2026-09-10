from datetime import UTC, datetime, timedelta

from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.marketdata.provider import get_snapshot as _get_snapshot


def get_snapshot(*args, **kwargs):
    """Never let these tests reach SEC EDGAR: the year history has its own suite."""
    kwargs.setdefault("history_sources", ())
    return _get_snapshot(*args, **kwargs)


def _snapshot(price: float = 100.0, as_of: datetime | None = None) -> TickerSnapshot:
    return TickerSnapshot(
        ticker="NVDA",
        price=price,
        shares_outstanding=24.4e9,
        revenue_ttm=302.9e9,
        fcf_ttm=127.0e9,
        net_debt=-46.0e9,
        currency="USD",
        as_of=as_of or datetime.now(UTC),
        source="test",
    )


def test_second_lookup_inside_the_ttl_is_served_from_disk(tmp_path):
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return _snapshot()

    first = get_snapshot("nvda", cache_dir=tmp_path, fetch=fetch)
    second = get_snapshot("NVDA", cache_dir=tmp_path, fetch=fetch)

    assert calls == ["NVDA"]  # symbol normalized, provider hit once
    assert second.price == first.price


def test_an_expired_snapshot_is_refetched(tmp_path):
    stale = _snapshot(price=100.0, as_of=datetime.now(UTC) - timedelta(hours=2))
    get_snapshot("NVDA", cache_dir=tmp_path, fetch=lambda symbol: stale)

    fresh = get_snapshot("NVDA", cache_dir=tmp_path, ttl_seconds=900, fetch=lambda symbol: _snapshot(price=224.03))

    assert fresh.price == 224.03


def test_refresh_bypasses_a_valid_cache_entry(tmp_path):
    get_snapshot("NVDA", cache_dir=tmp_path, fetch=lambda symbol: _snapshot(price=100.0))

    fresh = get_snapshot("NVDA", cache_dir=tmp_path, refresh=True, fetch=lambda symbol: _snapshot(price=224.03))

    assert fresh.price == 224.03


def test_a_corrupt_cache_file_is_ignored_rather_than_raised(tmp_path):
    (tmp_path / "NVDA.json").write_text("{not json")

    assert get_snapshot("NVDA", cache_dir=tmp_path, fetch=lambda symbol: _snapshot(price=224.03)).price == 224.03


def test_a_dotted_symbol_keeps_its_dot(tmp_path):
    get_snapshot("BRK.B", cache_dir=tmp_path, fetch=lambda symbol: _snapshot())

    assert (tmp_path / "BRK.B.json").exists()


def test_a_symbol_cannot_steer_the_cache_write_out_of_the_directory(tmp_path):
    get_snapshot("../escape", cache_dir=tmp_path, fetch=lambda symbol: _snapshot())

    # Whatever gets written lands inside the cache dir, never above it.
    assert [path.name for path in tmp_path.iterdir()] == ["_ESCAPE.json"]
    assert not (tmp_path.parent / "escape.json").exists()
