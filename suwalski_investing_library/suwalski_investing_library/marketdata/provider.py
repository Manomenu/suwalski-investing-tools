"""Snapshot lookup with an on-disk cache.

Fundamentals move quarterly and the price barely moves inside a working session, so every
`rdcf --ticker` run refetching from Yahoo would be rude to them and slow for you. Snapshots
land in one JSON file per symbol and are reused until the TTL expires.

The cache is a convenience, never a dependency: an unreadable, corrupt or read-only cache
degrades to a plain fetch instead of failing the valuation.
"""

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from suwalski_investing_library.constants import SOLUTION_ROOT
from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.marketdata.yahoo import fetch_snapshot

CACHE_DIR = Path(os.environ.get("SUWALSKI_MARKET_CACHE", SOLUTION_ROOT / ".artifacts" / "market"))
DEFAULT_TTL_SECONDS = 900

_UNSAFE_IN_FILENAME = re.compile(r"[^A-Z0-9.\-]")


def get_snapshot(
    ticker: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    cache_dir: Path = CACHE_DIR,
    refresh: bool = False,
    fetch: Callable[[str], TickerSnapshot] = fetch_snapshot,
) -> TickerSnapshot:
    """Cached snapshot for `ticker`. `refresh=True` skips the cache but still refills it."""
    symbol = ticker.strip().upper()
    path = cache_dir / f"{_safe_name(symbol)}.json"

    if not refresh:
        cached = _read(path, ttl_seconds)
        if cached is not None:
            return cached

    snapshot = fetch(symbol)
    _write(path, snapshot)
    return snapshot


def age_seconds(snapshot: TickerSnapshot) -> float:
    """How stale the snapshot is, in seconds."""
    return (datetime.now(UTC) - snapshot.as_of).total_seconds()


def _safe_name(symbol: str) -> str:
    # The symbol reaches this from an HTTP path in the server — it must never steer the
    # write anywhere but into the cache directory. Dots stay (BRK.B), leading ones do not.
    return _UNSAFE_IN_FILENAME.sub("_", symbol).lstrip(".") or "_"


def _read(path: Path, ttl_seconds: int) -> TickerSnapshot | None:
    try:
        snapshot = TickerSnapshot.model_validate_json(path.read_text())
    except (OSError, ValueError):
        return None
    return snapshot if age_seconds(snapshot) < ttl_seconds else None


def _write(path: Path, snapshot: TickerSnapshot) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2))
    except OSError:
        pass  # a cache we cannot write is still a valuation we can return
