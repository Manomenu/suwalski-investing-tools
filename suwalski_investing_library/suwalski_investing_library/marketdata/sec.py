"""Long-run history from SEC EDGAR's XBRL API.

Yahoo carries four or five reported years; EDGAR carries as many as the company has filed
(nineteen for MSFT, ten for KO). It is free, official and needs no API key — the price for
that is XBRL's tag drift: the same line item moves between tags across years, and a year can
be restated by a later filing. Both are handled below by alias lists and by preferring the
most recently filed value for a year.

Only US filers are covered. A symbol EDGAR does not know is not an error — the caller falls
back to the provider's own, shorter history.
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from suwalski_investing_library.contracts.market import HistoryPoint
from suwalski_investing_library.marketdata.errors import MarketDataError

SOURCE = "sec-edgar"

DEFAULT_USER_AGENT = "suwalski-investing-tools/0.1 (homelab)"


def _user_agent() -> str:
    """SEC asks automated callers to identify themselves and add a contact address. Read at
    call time so the environment can be set after import; the default stays anonymous."""
    return os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Order matters: the first alias that reports a year wins it. Two taxonomies are in play —
# domestic filers use us-gaap, foreign ones filing 20-F (ADRs: GRAB, TSM) use ifrs-full.
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
)
OPERATING_CASH_TAGS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)
CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)

IFRS_REVENUE_TAGS = (
    "RevenueFromContractsWithCustomers",
    "Revenue",
)
IFRS_OPERATING_CASH_TAGS = (
    "CashFlowsFromUsedInOperatingActivities",
    "CashFlowsFromUsedInOperatingActivitiesContinuingOperations",
)
IFRS_CAPEX_TAGS = (
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
)

_TAXONOMIES = (
    ("us-gaap", REVENUE_TAGS, OPERATING_CASH_TAGS, CAPEX_TAGS),
    ("ifrs-full", IFRS_REVENUE_TAGS, IFRS_OPERATING_CASH_TAGS, IFRS_CAPEX_TAGS),
)

_ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
_MIN_MONTHS = 11  # a fiscal year, allowing for 52/53-week calendars


class SecEdgarSource:
    """Long history for anything that files with the SEC — 10-K filers and the 20-F filers
    behind US-listed ADRs alike."""

    name = "sec-edgar"

    def years(self, symbol: str, *, cache_dir: Path | None = None, ttl_seconds: int = 7 * 86_400, **_: object) -> list[HistoryPoint]:
        return fetch_history(symbol, cache_dir=cache_dir, ttl_seconds=ttl_seconds)


def fetch_history(symbol: str, *, years: int = 10, cache_dir: Path | None = None, ttl_seconds: int = 7 * 86_400) -> list[HistoryPoint]:
    """Reported fiscal years for `symbol`, oldest first. Empty when EDGAR has no filer."""
    cik = _cik_for(symbol, cache_dir=cache_dir, ttl_seconds=ttl_seconds)
    if cik is None:
        return []
    facts = _cached_json(FACTS_URL.format(cik=cik), cache_dir, f"sec-facts-{cik}.json", ttl_seconds)
    return history_from_facts(facts, years=years)


def history_from_facts(facts: dict, *, years: int = 10) -> list[HistoryPoint]:
    """Turn a companyfacts document into history. Pure — the tests drive it directly.

    Tries each taxonomy and keeps whichever yields the most complete years, so an ADR filing
    IFRS reads the same as a domestic 10-K filer.
    """
    documents = facts.get("facts", {})
    revenue: dict[int, float] = {}
    operating: dict[int, float] = {}
    capex: dict[int, float] = {}
    for namespace, revenue_tags, cash_tags, capex_tags in _TAXONOMIES:
        tagged = documents.get(namespace, {})
        if not tagged:
            continue
        candidate_revenue = _annual_values(tagged, revenue_tags)
        candidate_operating = _annual_values(tagged, cash_tags)
        candidate_capex = _annual_values(tagged, capex_tags)
        complete = set(candidate_revenue) & set(candidate_operating) & set(candidate_capex)
        if len(complete) > len(set(revenue) & set(operating) & set(capex)):
            revenue, operating, capex = candidate_revenue, candidate_operating, candidate_capex
    if not revenue:
        return []

    points: list[HistoryPoint] = []
    previous: float | None = None
    for year in sorted(revenue):
        reported = revenue[year]
        growth = None if previous is None or previous <= 0 else reported / previous - 1
        previous = reported
        if reported <= 0 or year not in operating or year not in capex:
            continue
        fcf = operating[year] - abs(capex[year])
        points.append(HistoryPoint(year=year, revenue=reported, fcf=fcf, fcf_margin=fcf / reported, revenue_growth=growth))
    return points[-years:]


def _annual_values(tagged: dict, tags: tuple[str, ...]) -> dict[int, float]:
    """Fiscal-year values keyed by end year.

    The alias with the widest coverage supplies the series, and the remaining aliases only
    fill years it is missing. Letting the alias order decide per year mixes definitions:
    GRAB tags one year as `RevenueFromContractsWithCustomers` at $0.05B while `Revenue`
    carries seven consistent years including $1.43B for that same year — taking the former
    because it is listed first turns a growth chart into fiction.
    """
    by_tag = [(tag, _values_for_tag(tagged.get(tag, {}))) for tag in tags]
    # Stable sort: widest coverage first, alias order breaks ties.
    by_tag.sort(key=lambda pair: -len(pair[1]))

    values: dict[int, float] = {}
    for _, tag_values in by_tag:
        for year, value in tag_values.items():
            values.setdefault(year, value)
    return values


def _values_for_tag(fact: dict) -> dict[int, float]:
    """One tag's annual figures, taking the most recently filed value for each year."""
    values: dict[int, tuple[str, float]] = {}
    for entry in _monetary_entries(fact):
        if entry.get("form") not in _ANNUAL_FORMS or "start" not in entry:
            continue
        if _months(entry["start"], entry["end"]) < _MIN_MONTHS:
            continue
        year = int(entry["end"][:4])
        filed = entry.get("filed", "")
        # Restatements: a later filing of the same year replaces the earlier figure.
        if year in values and filed <= values[year][0]:
            continue
        values[year] = (filed, float(entry["val"]))
    return {year: value for year, (_, value) in values.items()}


def _monetary_entries(fact: dict) -> list[dict]:
    """Facts for the currency the company reports in.

    A filer reports in one currency — ASML in EUR, TSM in TWD — and reading only `USD`
    silently returns nothing for them. Whichever currency has the most entries is the
    reporting one; the valuation is currency-agnostic as long as it stays consistent.
    """
    units = fact.get("units", {})
    currencies = [(name, entries) for name, entries in units.items() if len(name) == 3 and name.isalpha()]
    if not currencies:
        return []
    return max(currencies, key=lambda pair: len(pair[1]))[1]


def _months(start: str, end: str) -> int:
    return (int(end[:4]) - int(start[:4])) * 12 + int(end[5:7]) - int(start[5:7])


def _cik_overrides() -> dict[str, str]:
    """Ticker -> CIK pairs from SEC_CIK_OVERRIDES, e.g. "SE:1703399,BABA:1577552".

    SEC's ticker map only covers filers it has a ticker on record for, which leaves out
    several ADRs — Sea Limited files 20-F under CIK 1703399 but lists no ticker at all.
    Matching those by company name would mean guessing (EDGAR carries two "SEA LTD"
    entries), and attaching the wrong company's history is worse than having none, so the
    mapping is yours to state explicitly.
    """
    raw = os.environ.get("SEC_CIK_OVERRIDES", "")
    pairs = {}
    for item in raw.split(","):
        ticker, _, cik = item.partition(":")
        if ticker.strip() and cik.strip().isdigit():
            pairs[ticker.strip().upper()] = f"{int(cik):010d}"
    return pairs


def _cik_for(symbol: str, *, cache_dir: Path | None, ttl_seconds: int) -> str | None:
    wanted = symbol.strip().upper()
    override = _cik_overrides().get(wanted)
    if override:
        return override

    table = _cached_json(TICKERS_URL, cache_dir, "sec-tickers.json", 30 * 86_400)
    for row in table.values():
        if str(row.get("ticker", "")).upper() == wanted:
            return f"{int(row['cik_str']):010d}"
    return None


def _cached_json(url: str, cache_dir: Path | None, name: str, ttl_seconds: int) -> dict:
    path = None if cache_dir is None else cache_dir / re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if path is not None and path.exists():
        age = datetime.now(UTC).timestamp() - path.stat().st_mtime
        if age < ttl_seconds:
            try:
                return json.loads(path.read_text())
            except (OSError, ValueError):
                pass  # a broken cache file is refetched, not fatal

    # SEC rejects a bare User-Agent and, oddly, one that impersonates a browser — it wants a
    # named tool plus an Accept header. No Accept-Encoding: urllib would not decode gzip.
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _user_agent(), "Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise MarketDataError(f"SEC EDGAR request failed ({url}): {exc}") from exc

    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
        except OSError:
            pass
    return payload
