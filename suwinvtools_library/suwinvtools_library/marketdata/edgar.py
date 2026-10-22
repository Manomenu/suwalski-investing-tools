"""EDGAR beyond the annual history: quarters, filings and their text.

`sec.py` answers "what did the company report each year"; this module answers what the
signals job asks every month — which filings arrived since last time, what a 10-Q's cash
flow says for one quarter, and what the words of a filing are. Same source, same rules: free,
official, no API key, a named User-Agent (SEC_USER_AGENT) on every request.

Everything that turns a document into numbers is a pure function the tests drive with
recorded documents; `Edgar` only fetches and caches.
"""

import html
import itertools
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import cast, override

from suwinvtools_library.marketdata.errors import MarketDataError

DEFAULT_USER_AGENT = "suwinvtools/0.1 (homelab)"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

# A body for a URL. The default goes to the network; the tests pass recorded documents.
Fetch = Callable[[str], bytes]
type Json = dict[str, object]

CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
)
RPO_TAGS = ("RevenueRemainingPerformanceObligation",)
EQUITY_TAGS = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
DEBT_TAGS = ("LongTermDebt", "LongTermDebtNoncurrent", "DebtInstrumentCarryingAmount")
CASH_TAGS = ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
# In the dei namespace, not us-gaap: instants(facts, SHARES_TAGS, namespace="dei").
SHARES_TAGS = ("EntityCommonStockSharesOutstanding",)
# Companies with several share classes (Alphabet) report the count above per class, which the
# companyfacts API leaves out; the quarter's diluted average is the fallback (quarter_averages).
DILUTED_SHARES_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding",)


def sec_get(url: str) -> bytes:
    """One request to SEC. It refuses a bare User-Agent and one that impersonates a browser:
    it wants a named tool with a contact, plus an Accept header."""
    agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    request = urllib.request.Request(url, headers={"User-Agent": agent, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})  # noqa: S310 — https URLs built above
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 — same
            return cast(bytes, response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MarketDataError(f"SEC EDGAR request failed ({url}): {exc}") from exc


@dataclass(frozen=True)
class Filing:
    cik: str
    form: str
    filed: date
    report_date: date | None
    accession: str
    primary_document: str
    # 8-K item numbers ("2.02" results, "1.02" a terminated agreement); empty for other forms.
    items: tuple[str, ...]

    @property
    def folder(self) -> str:
        return ARCHIVE_URL.format(cik=int(self.cik), accession=self.accession.replace("-", ""), name="")

    @property
    def url(self) -> str:
        return self.folder + self.primary_document


@dataclass(frozen=True)
class SearchHit:
    cik: str
    company: str
    form: str
    filed: date
    url: str


class Edgar:
    """Fetching with a file cache. Archive documents never change, so they are kept for good;
    the company indexes (facts, submissions) for a few hours."""

    def __init__(self, *, fetch: Fetch = sec_get, cache_dir: Path | None = None, index_ttl: timedelta = timedelta(hours=6)) -> None:
        self._fetch = fetch
        self._cache_dir = cache_dir
        self._index_ttl = index_ttl

    def cik(self, ticker: str) -> str | None:
        table = self._json(TICKERS_URL, ttl=timedelta(days=30))
        wanted = ticker.strip().upper()
        for row in table.values():
            if isinstance(row, dict):
                fields = cast(Json, row)
                if str(fields.get("ticker", "")).upper() == wanted:
                    return f"{int(str(fields['cik_str'])):010d}"
        return None

    def facts(self, cik: str) -> Json:
        return self._json(FACTS_URL.format(cik=cik), ttl=self._index_ttl)

    def filings(self, cik: str) -> list[Filing]:
        return filings_from_submissions(cik, self._json(SUBMISSIONS_URL.format(cik=cik), ttl=self._index_ttl))

    def text(self, url: str) -> str:
        return html_to_text(self._get(url, ttl=None).decode("utf-8", errors="replace"))

    def exhibit(self, filing: Filing, pattern: str = r"ex-?99|exhibit99|dex99") -> str | None:
        """URL of a filing's exhibit (by default the press release of an 8-K), or None."""
        index = self._json(filing.folder + "index.json", ttl=None)
        directory = cast(Json, index.get("directory", {}))
        names = [str(cast(Json, item).get("name", "")) for item in cast(list[object], directory.get("item", []))]
        documents = [name for name in names if name.lower().endswith((".htm", ".html")) and name != filing.primary_document]
        for name in documents:
            if re.search(pattern, name.lower()):
                return filing.folder + name
        return None

    def search(self, query: str, *, forms: Iterable[str], start: date, end: date, ciks: Iterable[str] = ()) -> list[SearchHit]:
        """EDGAR full-text search: filings whose words match `query` (quote phrases)."""
        params = {"q": query, "forms": ",".join(forms), "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat()}
        wanted = [cik.lstrip("0") for cik in ciks]
        if wanted:
            params["ciks"] = ",".join(f"{int(cik):010d}" for cik in wanted)
        url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
        return hits_from_search(self._json(url, ttl=timedelta(hours=6)))

    def _json(self, url: str, *, ttl: timedelta | None) -> Json:
        try:
            parsed: object = json.loads(self._get(url, ttl=ttl))
        except ValueError as exc:
            raise MarketDataError(f"SEC EDGAR answered something other than JSON ({url})") from exc
        if not isinstance(parsed, dict):
            raise MarketDataError(f"SEC EDGAR answered an unexpected shape ({url})")
        return cast(Json, parsed)

    def _get(self, url: str, *, ttl: timedelta | None) -> bytes:
        path = None if self._cache_dir is None else self._cache_dir / "edgar" / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
        if path is not None and path.exists():
            age = datetime.now(UTC) - datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if ttl is None or age < ttl:
                try:
                    return path.read_bytes()
                except OSError:
                    pass  # an unreadable cache file is refetched, not fatal
        body = self._fetch(url)
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            except OSError:
                pass
        return body


# --- pure: documents into values -------------------------------------------------------------


def filings_from_submissions(cik: str, submissions: Json) -> list[Filing]:
    """The recent filings of a submissions document, newest first."""
    recent = cast(Json, cast(Json, submissions.get("filings", {})).get("recent", {}))
    columns = {key: cast(list[object], value) for key, value in recent.items() if isinstance(value, list)}
    forms = columns.get("form", [])
    filings: list[Filing] = []
    for i, form in enumerate(forms):

        def column(name: str, index: int = i) -> str:
            values = columns.get(name, [])
            return str(values[index]) if index < len(values) else ""

        report = column("reportDate")
        items = tuple(item.strip() for item in column("items").split(",") if item.strip())
        filings.append(
            Filing(
                cik=cik,
                form=str(form),
                filed=date.fromisoformat(column("filingDate")),
                report_date=date.fromisoformat(report) if report else None,
                accession=column("accessionNumber"),
                primary_document=column("primaryDocument"),
                items=items,
            )
        )
    filings.sort(key=lambda filing: filing.filed, reverse=True)
    return filings


def hits_from_search(result: Json) -> list[SearchHit]:
    hits = cast(list[object], cast(Json, result.get("hits", {})).get("hits", []))
    found: list[SearchHit] = []
    for hit in hits:
        entry = cast(Json, hit)
        source = cast(Json, entry.get("_source", {}))
        identifier = str(entry.get("_id", ""))  # "<accession>:<document>"
        accession, _, document = identifier.partition(":")
        ciks = cast(list[object], source.get("ciks", []))
        names = cast(list[object], source.get("display_names", []))
        forms = cast(list[object], source.get("root_forms", []))
        if not ciks or not accession:
            continue
        cik = str(ciks[0])
        found.append(
            SearchHit(
                cik=cik,
                company=str(names[0]) if names else cik,
                form=str(forms[0]) if forms else "",
                filed=date.fromisoformat(str(source.get("file_date", "1970-01-01"))),
                url=ARCHIVE_URL.format(cik=int(cik), accession=accession.replace("-", ""), name=document),
            )
        )
    return found


def quarterly_flows(facts: Json, tags: Iterable[str]) -> dict[date, float]:
    """Quarter values of a flow (capex, revenue) keyed by the quarter's end date.

    10-Qs report cash flows year-to-date and the 10-K the whole year, so most quarters exist
    only as a difference: Q2 = 6 months - 3 months, Q4 = 12 months - 9 months, always of
    two figures that start on the same day. Of the tags given, the one with the most recent
    quarter supplies the whole series, so definitions never mix within one (companies move
    between tags: Amazon left PaymentsToAcquirePropertyPlantAndEquipment years ago).
    """
    series = [_quarters_from_cumulative(_usd_entries(facts, tag)) for tag in tags]
    return _freshest(series)


def instants(facts: Json, tags: Iterable[str], *, namespace: str = "us-gaap") -> dict[date, float]:
    """Point-in-time values (backlog, equity, debt) by date, the latest filing winning; of
    the tags given, the one reported most recently."""
    series: list[dict[date, float]] = []
    for tag in tags:
        values: dict[date, tuple[str, float]] = {}
        for entry in _usd_entries(facts, tag, namespace=namespace, unit=None):
            if "start" in entry:
                continue
            end = date.fromisoformat(str(entry["end"]))
            filed = str(entry.get("filed", ""))
            if end not in values or filed > values[end][0]:
                values[end] = (filed, float(cast(float, entry["val"])))
        series.append({end: value for end, (_, value) in values.items()})
    return _freshest(series)


def _freshest(series: list[dict[date, float]]) -> dict[date, float]:
    filled = [values for values in series if values]
    none: dict[date, float] = {}
    return max(filled, key=lambda values: (max(values), len(values)), default=none)


def quarter_averages(facts: Json, tags: Iterable[str], *, unit: str = "shares") -> dict[date, float]:
    """Values reported for exactly one quarter (an average, not a flow: never de-cumulated),
    keyed by the quarter's end, the latest filing winning."""
    series: list[dict[date, float]] = []
    for tag in tags:
        values: dict[date, tuple[str, float]] = {}
        for entry in _usd_entries(facts, tag, unit=unit):
            if "start" not in entry:
                continue
            start, end = date.fromisoformat(str(entry["start"])), date.fromisoformat(str(entry["end"]))
            filed = str(entry.get("filed", ""))
            if _months(start, end) == 3 and (end not in values or filed > values[end][0]):
                values[end] = (filed, float(cast(float, entry["val"])))
        series.append({end: value for end, (_, value) in values.items()})
    return _freshest(series)


def trailing_sum(quarters: Mapping[date, float], end: date, count: int = 4) -> float | None:
    """The sum of `count` consecutive quarters ending at `end`, or None when one is missing."""
    ends = sorted(day for day in quarters if day <= end)[-count:]
    if len(ends) < count or ends[-1] != end:
        return None
    # Consecutive means about a quarter apart; a gap would quietly make a 3-quarter "year".
    if any((later - earlier).days > 100 for earlier, later in itertools.pairwise(ends)):
        return None
    return sum(quarters[day] for day in ends)


def calendar_quarter(day: date) -> str:
    """The calendar quarter a fiscal period ending on `day` belongs to, e.g. "2026Q3".

    Fiscal quarters end on odd days (Apple's on the last Saturday, Microsoft's a calendar
    month ahead of nothing), so the period is placed by its middle rather than its end."""
    middle = day - timedelta(days=45)
    return f"{middle.year}Q{(middle.month - 1) // 3 + 1}"


def quarter_before(filed: date) -> str:
    """The calendar quarter that ended most recently before a filing date — what an earnings
    release published on `filed` reports on."""
    previous = filed.replace(day=1) - timedelta(days=1)
    while previous.month % 3 != 0:
        previous = previous.replace(day=1) - timedelta(days=1)
    return f"{previous.year}Q{previous.month // 3}"


def html_to_text(document: str) -> str:
    """The words of an HTML filing: no tags, no inline-XBRL header, whitespace collapsed."""
    parser = _TextParser()
    parser.feed(document)
    parser.close()
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", "\n", html.unescape("".join(parser.parts)))).strip()


def paragraphs_with(text: str, *words: str, window: int = 600, limit: int = 8) -> list[str]:
    """Passages of `text` around each place where any of `words` appears — what is sent to the
    language model instead of a 300-page 10-K."""
    lowered = text.lower()
    spans: list[tuple[int, int]] = []
    for word in words:
        spans.extend(
            (max(0, match.start() - window // 2), min(len(text), match.end() + window // 2))
            for match in re.finditer(re.escape(word.lower()), lowered)
        )
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [text[start:end].strip() for start, end in merged[:limit]]


def _usd_entries(facts: Json, tag: str, *, namespace: str = "us-gaap", unit: str | None = "USD") -> list[Json]:
    documents = cast(Json, facts.get("facts", {}))
    tagged = cast(Json, documents.get(namespace, {}))
    fact = cast(Json, tagged.get(tag, {}))
    units = cast(Json, fact.get("units", {}))
    if unit is None:
        # Whatever the fact is measured in (USD for money, shares for a share count).
        lists = [cast(list[object], entries) for entries in units.values() if isinstance(entries, list)]
        empty: list[object] = []
        chosen = max(lists, key=len, default=empty)
        return [cast(Json, entry) for entry in chosen]
    return [cast(Json, entry) for entry in cast(list[object], units.get(unit, []))]


def _months(start: date, end: date) -> int:
    return round((end - start).days / 30.44)


def _quarters_from_cumulative(entries: list[Json]) -> dict[date, float]:
    # (start, end) -> (filed, value): restatements replace the earlier figure.
    figures: dict[tuple[date, date], tuple[str, float]] = {}
    for entry in entries:
        if "start" not in entry:
            continue
        start, end = date.fromisoformat(str(entry["start"])), date.fromisoformat(str(entry["end"]))
        if _months(start, end) not in {3, 6, 9, 12}:
            continue
        filed = str(entry.get("filed", ""))
        key = (start, end)
        if key not in figures or filed > figures[key][0]:
            figures[key] = (filed, float(cast(float, entry["val"])))

    quarters: dict[date, float] = {}
    by_start: dict[date, list[tuple[date, float]]] = {}
    for (start, end), (_, value) in figures.items():
        by_start.setdefault(start, []).append((end, value))
    for start, cumulative in by_start.items():
        cumulative.sort()
        previous_end, previous_value = start, 0.0
        for end, value in cumulative:
            months = _months(previous_end, end)
            if months == 3:
                quarters.setdefault(end, value - previous_value)
            previous_end, previous_value = end, value
    return quarters


class _TextParser(HTMLParser):
    _SKIPPED = frozenset({"script", "style", "ix:header", "head"})
    _BREAKS = frozenset({"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIPPED:
            self._skipping += 1
        elif tag in self._BREAKS:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" ")

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED and self._skipping:
            self._skipping -= 1
        elif tag in self._BREAKS:
            self.parts.append("\n")

    @override
    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)
