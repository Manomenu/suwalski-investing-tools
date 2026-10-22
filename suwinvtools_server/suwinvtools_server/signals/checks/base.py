"""What every check is: a description a person reads, `read` (fetch, maybe ask the language
model, return values) and `evaluate` (pure: values in, verdicts out).

`read` decides readiness too — a check with nothing new to read returns NOT_READY instead of
readings. `evaluate` sees the whole stored history of the check, so a trend needs no memory
of its own; it returns verdicts for the newest period of each subject (and for every event,
for the checks that track events), and the runner sends only what changed.
"""

import statistics
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from suwinvtools_library.marketdata.edgar import Edgar
from suwinvtools_server.signals.llm import Document, Extractor, verify
from suwinvtools_server.signals.model import Category, Evidence, JsonValue, Outcome, Quote, Reading, Verdict
from suwinvtools_server.signals.sources.http import Fetch
from suwinvtools_server.signals.sources.news import Headline


@dataclass(frozen=True)
class CheckMeta:
    id: str
    category: Category
    title: str
    question: str
    rule_red: str
    rule_green: str
    unit: str
    caveat: str


@dataclass(frozen=True)
class Context:
    """What a check may use. Everything that reaches outside the process is injected, so the
    tests drive a check with recorded answers and a stub model."""

    today: date
    edgar: Edgar
    fetch: Fetch
    # None when no model is configured: the checks that need one report INVALID.
    extract: Extractor | None
    # ticker, day -> closing price on (or just before) that day.
    price: Callable[[str, date], float | None]
    # check id, subject -> the newest period stored, so `read` knows what is new.
    latest_period: Callable[[str, str], str | None]


@dataclass(frozen=True)
class ReadResult:
    readings: list[Reading] = field(default_factory=list[Reading])
    # NOT_READY and INVALID, per subject: what was not read, and why.
    skipped: list[Outcome] = field(default_factory=list[Outcome])


class Check(ABC):
    meta: CheckMeta

    @abstractmethod
    def read(self, ctx: Context) -> ReadResult: ...

    @abstractmethod
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]: ...

    def skip(self, subject: str, period: str, verdict: Verdict, reason: str) -> Outcome:
        return Outcome(check_id=self.meta.id, subject=subject, period=period, verdict=verdict, summary=reason)

    def outcome(
        self,
        reading: Reading,
        verdict: Verdict,
        summary: str,
        *,
        evidence: Iterable[Evidence] = (),
        details: dict[str, JsonValue] | None = None,
    ) -> Outcome:
        return Outcome(
            check_id=self.meta.id,
            subject=reading.subject,
            period=reading.period,
            verdict=verdict,
            summary=summary,
            evidence=tuple(evidence) or reading.evidence,
            details=details or {},
        )


# --- periods ----------------------------------------------------------------------------------


def month(day: date) -> str:
    return f"{day.year}-{day.month:02d}"


def quarter_of_month(period: str) -> str:
    year, mon = period.split("-")[:2]
    return f"{year}Q{(int(mon) - 1) // 3 + 1}"


def shift_quarter(period: str, quarters: int) -> str:
    year, q = int(period[:4]), int(period[5])
    index = year * 4 + (q - 1) + quarters
    return f"{index // 4}Q{index % 4 + 1}"


def shift_month(period: str, months: int) -> str:
    year, mon = int(period[:4]), int(period[5:7])
    index = year * 12 + (mon - 1) + months
    return f"{index // 12}-{index % 12 + 1:02d}"


def quarter_end(period: str) -> date:
    year, q = int(period[:4]), int(period[5])
    return {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[q]


def by_subject(history: Iterable[Reading]) -> dict[str, dict[str, Reading]]:
    """Readings as subject -> period -> reading."""
    grouped: dict[str, dict[str, Reading]] = {}
    for reading in history:
        grouped.setdefault(reading.subject, {})[reading.period] = reading
    return grouped


def number(reading: Reading | None, key: str) -> float | None:
    if reading is None:
        return None
    value = reading.data.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def median(values: Sequence[float]) -> float:
    return statistics.median(values)


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:+.{digits}f}%"


def usd(value: float) -> str:
    for scale, suffix in ((1e12, " bln"), (1e9, " mld"), (1e6, " mln")):
        if abs(value) >= scale:
            return f"{value / scale:.1f}{suffix} USD"
    return f"{value:,.0f} USD"


# --- news claims ------------------------------------------------------------------------------


def documents_from(headlines: Sequence[Headline]) -> list[Document]:
    return [Document(id=item.id, title=f"{item.outlet}: {item.title}", url=item.link, text=item.text) for item in headlines]


def verified(quote: Quote | None, documents: Sequence[Document], headlines: Sequence[Headline]) -> tuple[Evidence, str] | None:
    """The evidence of a quote and the outlet's domain it came from, when the words are real."""
    evidence = verify(quote, documents)
    if evidence is None or quote is None:
        return None
    outlet = next((item.domain for item in headlines if item.id == quote.source_id), "")
    return evidence, outlet


def confirmed(domains: Iterable[str], *, primary: bool = False) -> bool:
    """Two independent outlets, or one primary source (a filing, the company itself)."""
    return primary or len({domain for domain in domains if domain}) >= 2
