"""Recorded answers and stand-ins for the checks' tests: nothing here touches the network.

`Pages` is a dict-backed fetch, `Sec` builds the EDGAR documents a company needs (ticker table,
submissions, companyfacts, filing text), `rss` builds a Google News feed, `stub` is a language
model that returns ready pydantic objects."""

import json
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from pydantic import BaseModel

from suwinvtools_library.marketdata.edgar import ARCHIVE_URL, FACTS_URL, SEARCH_URL, SUBMISSIONS_URL, TICKERS_URL, Edgar
from suwinvtools_server.signals.checks.base import Context
from suwinvtools_server.signals.llm import Document, Extractor
from suwinvtools_server.signals.model import Reading
from suwinvtools_server.signals.sources.http import SourceError

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 22)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class Pages:
    """A fetch that answers from a dict (url -> body); anything else is an error, so a test
    notices a request it did not expect. `default` answers every other url."""

    def __init__(self, pages: Mapping[str, bytes] | None = None, *, default: bytes | None = None) -> None:
        self.pages: dict[str, bytes] = dict(pages or {})
        self.default = default
        self.requested: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.requested.append(url)
        if url in self.pages:
            return self.pages[url]
        if self.default is not None:
            return self.default
        raise SourceError(f"no recorded answer for {url}")


class Stub:
    """A language model that answers each schema with a ready object (or a function of the documents)."""

    def __init__(self, answers: Mapping[type[BaseModel], BaseModel | Callable[[Sequence[Document]], BaseModel]]) -> None:
        self.answers = dict(answers)
        self.calls: list[tuple[type[BaseModel], Sequence[Document]]] = []

    def __call__(self, schema: type[BaseModel], instruction: str, documents: Sequence[Document]) -> BaseModel:
        self.calls.append((schema, documents))
        answer = self.answers[schema]
        return answer(documents) if callable(answer) else answer


def context(
    *,
    sec: "Sec | None" = None,
    fetch: Pages | None = None,
    extract: Extractor | None = None,
    prices: Mapping[tuple[str, date], float] | None = None,
    latest: Mapping[tuple[str, str], str] | None = None,
) -> Context:
    return Context(
        today=TODAY,
        edgar=Edgar(fetch=(sec or Sec()).pages, cache_dir=None),
        fetch=fetch or Pages(),
        extract=extract,
        price=lambda ticker, day: (prices or {}).get((ticker, day)),
        latest_period=lambda check_id, subject: (latest or {}).get((check_id, subject)),
    )


def reading(check_id: str, subject: str, period: str, value: float | None = None, **data: float | str | bool | list[str]) -> Reading:
    return Reading(check_id=check_id, subject=subject, period=period, value=value, data=dict(data))  # pyright: ignore[reportArgumentType] — plain JSON values


# --- EDGAR ------------------------------------------------------------------------------------


def _json(value: object) -> bytes:
    return json.dumps(value).encode()


def archive(cik: int, accession: str, name: str) -> str:
    return ARCHIVE_URL.format(cik=cik, accession=accession.replace("-", ""), name=name)


@dataclass
class Sec:
    """The EDGAR documents of a few companies, as a `Pages`."""

    pages: Pages = field(default_factory=Pages)
    tickers: dict[str, dict[str, object]] = field(default_factory=dict[str, dict[str, object]])
    _facts: dict[int, dict[str, dict[str, object]]] = field(default_factory=dict[int, dict[str, dict[str, object]]])

    def company(self, ticker: str, cik: int) -> str:
        self.tickers[str(len(self.tickers))] = {"cik_str": cik, "ticker": ticker}
        self.pages.pages[TICKERS_URL] = _json(self.tickers)
        return f"{cik:010d}"

    def filings(self, ticker: str, cik: int, rows: Sequence[tuple[str, str, str, str, str, str]]) -> None:
        """rows: (form, filed, report date, accession, primary document, 8-K items)."""
        padded = self.company(ticker, cik)
        recent = {
            "form": [r[0] for r in rows],
            "filingDate": [r[1] for r in rows],
            "reportDate": [r[2] for r in rows],
            "accessionNumber": [r[3] for r in rows],
            "primaryDocument": [r[4] for r in rows],
            "items": [r[5] for r in rows],
        }
        self.pages.pages[SUBMISSIONS_URL.format(cik=padded)] = _json({"filings": {"recent": recent}})

    def document(self, cik: int, accession: str, name: str, html: str) -> str:
        url = archive(cik, accession, name)
        self.pages.pages[url] = html.encode()
        return url

    def exhibit(self, cik: int, accession: str, primary: str, name: str, html: str) -> str:
        """An 8-K's folder index and its press release exhibit."""
        folder = archive(cik, accession, "")
        self.pages.pages[folder + "index.json"] = _json({"directory": {"item": [{"name": primary}, {"name": name}]}})
        return self.document(cik, accession, name, html)

    def facts(self, cik: int, tags: Mapping[str, Mapping[str, float]], *, flow: bool = True) -> None:
        """companyfacts: tag -> {period end (ISO): value}. Flows get 3-month entries, instants a point in time."""
        self._add_facts(cik, tags, flow=flow, namespace="us-gaap", unit="USD")

    def shares(self, cik: int, series: Mapping[str, float]) -> None:
        """The share count on a cover page (dei namespace)."""
        self._add_facts(cik, {"EntityCommonStockSharesOutstanding": series}, flow=False, namespace="dei", unit="shares")

    def _add_facts(self, cik: int, tags: Mapping[str, Mapping[str, float]], *, flow: bool, namespace: str, unit: str) -> None:
        document = self._facts.setdefault(cik, {})
        for tag, series in tags.items():
            entries: list[dict[str, object]] = []
            for end, value in series.items():
                ended = date.fromisoformat(end)
                entry: dict[str, object] = {"end": end, "val": value, "filed": end}
                if flow:
                    entry["start"] = date(ended.year, ended.month - 2, 1).isoformat()  # quarter ends only: Mar, Jun, Sep, Dec
                entries.append(entry)
            document.setdefault(namespace, {})[tag] = {"units": {unit: entries}}
        self.pages.pages[FACTS_URL.format(cik=f"{cik:010d}")] = _json({"facts": document})

    def search(
        self, query: str, forms: str, window: tuple[date, date], hits: Sequence[tuple[str, int, str, str, str]], ciks: str = ""
    ) -> None:
        """hits: (accession, cik, company, document, filed). The url mirrors Edgar.search."""
        params: dict[str, str] = {
            "q": query,
            "forms": forms,
            "dateRange": "custom",
            "startdt": window[0].isoformat(),
            "enddt": window[1].isoformat(),
        }
        if ciks:
            params["ciks"] = ciks
        body = {
            "hits": {
                "hits": [
                    {
                        "_id": f"{accession}:{document}",
                        "_source": {
                            "ciks": [f"{cik:010d}"],
                            "display_names": [company],
                            "root_forms": [forms.split(",", maxsplit=1)[0]],
                            "file_date": filed,
                        },
                    }
                    for accession, cik, company, document, filed in hits
                ]
            }
        }
        self.pages.pages[f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"] = _json(body)


# --- news -------------------------------------------------------------------------------------


def rss(*items: tuple[str, str, str]) -> bytes:
    """A Google News feed of (title, outlet, outlet url)."""
    body = "".join(
        f"<item><title>{escape(title)} - {escape(outlet)}</title><link>https://news.google.com/{i}</link>"
        f"<pubDate>Mon, 19 Oct 2026 10:00:00 GMT</pubDate><description></description>"
        f'<source url="{url}">{escape(outlet)}</source></item>'
        for i, (title, outlet, url) in enumerate(items)
    )
    return f"<rss><channel><title>x</title>{body}</channel></rss>".encode()
