"""Year-by-year history: several sources, one accumulating store.

The sources are asked **in order and their years are merged**, which is why this is not a
chain of responsibility — that pattern stops at the first handler that can answer, and here
the first answer is often incomplete. EDGAR carries a decade for SEC filers; Yahoo carries
four years but reaches Warsaw and every other market EDGAR never sees. A company can need
both. What the loop does borrow from that pattern is the early exit: once the years asked
for are covered, the remaining sources are not called at all.

The store adds the other half. It keeps history **per fiscal year**, so:
  * A source cannot make a request smaller — EDGAR's `companyfacts` is one document with
    everything — but a covered request makes it unnecessary.
  * Widening the horizon (10Y -> 20Y) costs one round of sources, and `exhausted` records
    that there is no more to find, so it stops asking.
  * Years survive their source. If EDGAR drops a year to tag drift, the stored copy stays.
  * A restated year overwrites the stored one: same key, newer value.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from suwalski_investing_library.contracts.market import HistoryPoint
from suwalski_investing_library.marketdata.errors import MarketDataError
from suwalski_investing_library.marketdata.sec import SecEdgarSource
from suwalski_investing_library.marketdata.yahoo import YahooAnnualSource

DEFAULT_YEARS = 10
# Annual filings land once a year; a week between checks is already eager.
DEFAULT_TTL_SECONDS = 7 * 86_400

_UNSAFE_IN_FILENAME = re.compile(r"[^A-Z0-9.\-]")


class HistorySource(Protocol):
    """A place years can come from. Adding one is a class plus an entry in DEFAULT_SOURCES."""

    name: str

    def years(self, symbol: str, *, cache_dir: Path | None = None, ttl_seconds: int = 0, **kwargs: object) -> list[HistoryPoint]: ...


# Order is priority: the longest history first, so a covered symbol never reaches the rest.
DEFAULT_SOURCES: tuple[HistorySource, ...] = (SecEdgarSource(), YahooAnnualSource())


def get_history(
    symbol: str,
    *,
    years: int = DEFAULT_YEARS,
    cache_dir: Path,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    sources: tuple[HistorySource, ...] = DEFAULT_SOURCES,
    seed: list[HistoryPoint] | None = None,
) -> list[HistoryPoint]:
    """Up to `years` most recent fiscal years, oldest first.

    `seed` is history the caller already holds — the snapshot fetch brings Yahoo's annual
    statements along for free — merged before any source is asked.
    """
    symbol = symbol.strip().upper()
    path = cache_dir / f"history-{_safe_name(symbol)}.json"
    stored = _read(path)

    if _covers(stored, years) and _fresh(stored, ttl_seconds):
        return _points(stored, years)

    before = len(stored["years"])
    merged = _merge(stored, seed or [])
    used: list[str] = []

    for source in sources:
        if _covers(merged, years):
            break
        try:
            found = source.years(symbol, cache_dir=cache_dir, ttl_seconds=ttl_seconds)
        except MarketDataError:
            continue  # a source that is down is not a failed valuation
        if found:
            used.append(source.name)
            merged = _merge(merged, found)

    if len(merged["years"]) == before and not stored["years"]:
        # Nothing anywhere, and nothing stored before: do not mark this as settled.
        return []

    # No source added a year beyond what was already stored — there is no more to find.
    merged["exhausted"] = len(merged["years"]) <= before and before > 0
    merged["fetched_at"] = datetime.now(UTC).isoformat()
    merged["sources"] = sorted({*stored.get("sources", []), *used})
    _write(path, merged)
    return _points(merged, years)


def _covers(stored: dict, years: int) -> bool:
    if not stored["years"]:
        return False
    return len(stored["years"]) >= years or stored.get("exhausted", False)


def _fresh(stored: dict, ttl_seconds: int) -> bool:
    fetched_at = stored.get("fetched_at")
    if not fetched_at:
        return False
    try:
        age = (datetime.now(UTC) - datetime.fromisoformat(fetched_at)).total_seconds()
    except ValueError:
        return False
    return age < ttl_seconds


def _merge(stored: dict, points: list[HistoryPoint]) -> dict:
    years = dict(stored["years"])
    for point in points:
        years[str(point.year)] = point.model_dump(mode="json")
    return {**stored, "years": years}


def _points(stored: dict, years: int) -> list[HistoryPoint]:
    """The most recent unbroken run of years, at most `years` long.

    A filer can be missing a year in the middle — EDGAR has no capex tag for NVDA between
    2013 and 2021. Charting that as a gap reads like a collapse, so only the continuous tail
    is returned. The cache still keeps the older years: another source may fill the hole
    later, and then they join the run on their own.
    """
    parsed = [HistoryPoint.model_validate(value) for _, value in sorted(stored["years"].items())]
    run: list[HistoryPoint] = []
    for point in reversed(parsed):
        if run and run[-1].year - point.year != 1:
            break
        run.append(point)
    run.reverse()
    return run[-years:]


def _read(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"years": {}}
    return loaded if isinstance(loaded.get("years"), dict) else {"years": {}}


def _write(path: Path, stored: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, indent=2))
    except OSError:
        pass  # a cache we cannot write is still history we can return


def _safe_name(symbol: str) -> str:
    return _UNSAFE_IN_FILENAME.sub("_", symbol).lstrip(".") or "_"
