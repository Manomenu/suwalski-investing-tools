"""What the signals feature is made of.

Two kinds of classes, on purpose (AGENTS.md, "pydantic at the boundary, dataclass inside"):
frozen dataclasses for what lives only inside the job — a reading, an outcome — and pydantic
for what crosses the process: the API's answers and the schemas the language model fills.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class Verdict(StrEnum):
    # A warning sign of the AI cycle turning — goes to the red channel.
    RED = "red"
    # A sign that monetisation keeps up — goes to the green channel.
    GREEN = "green"
    # A valid reading that meets neither condition.
    NEUTRAL = "neutral"
    # The first reading of something measured as a change; nothing to compare it with yet.
    BASELINE = "baseline"
    # Nothing new to read since the last run (no new filing, too early in the quarter).
    NOT_READY = "not_ready"
    # A reading was attempted and could not be trusted: missing data, a changed source, a quote
    # the language model invented. Goes to the status channel with the reason.
    INVALID = "invalid"
    # A red or green claim from a single news source — waits for a second one or a filing.
    UNCONFIRMED = "unconfirmed"


class Category(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


CATEGORY_NAMES: dict[Category, str] = {
    Category.A: "Monetyzacja vs inwestycje",
    Category.B: "Zużycie sprzętu",
    Category.C: "Paradoks Jevonsa",
    Category.D: "Finansowanie labów",
    Category.E: "Wycena vs zwrot z kapitału",
}


@dataclass(frozen=True)
class Evidence:
    """Where a number came from: the document, and the words in it that say so."""

    url: str
    title: str
    quote: str = ""


@dataclass(frozen=True)
class Reading:
    """One value of one check for one subject (a company, a GPU, a lab) and one period."""

    check_id: str
    subject: str
    period: str
    value: float | None
    data: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Outcome:
    """A verdict on one subject and period, with the sentence a person reads."""

    check_id: str
    subject: str
    period: str
    verdict: Verdict
    summary: str
    evidence: tuple[Evidence, ...] = ()
    details: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])


# --- what the API answers ---------------------------------------------------------------------


class EvidenceOut(BaseModel):
    url: str
    title: str
    quote: str


class CheckInfo(BaseModel):
    id: str = Field(description="A1, B4, …")
    category: Category
    category_name: str
    title: str
    question: str
    rule_red: str
    rule_green: str
    unit: str = Field(description="what `value` is measured in, e.g. '%', 'lat', 'USD/h'")
    caveat: str


class OutcomeOut(BaseModel):
    check_id: str
    subject: str
    period: str
    verdict: Verdict
    summary: str
    evidence: list[EvidenceOut]
    evaluated_at: str
    notified: bool


class ReadingOut(BaseModel):
    subject: str
    period: str
    value: float | None
    read_at: str


class BoardItem(BaseModel):
    check: CheckInfo
    # The verdict that best describes the check now: the latest red, else green, else neutral.
    headline: OutcomeOut | None
    latest: list[OutcomeOut] = Field(description="the latest outcome of every subject")
    spark: list[float] = Field(description="the headline subject's values, oldest first")


class RunOut(BaseModel):
    id: int
    started_at: str
    finished_at: str | None
    dry_run: bool
    counts: dict[str, int]


class Board(BaseModel):
    items: list[BoardItem]
    last_run: RunOut | None


class CheckHistory(BaseModel):
    check: CheckInfo
    readings: list[ReadingOut]
    outcomes: list[OutcomeOut]


# --- what the language model fills ------------------------------------------------------------
# Every claim carries the words it rests on. The job checks them against the documents it sent
# (llm.verify) and drops the reading when they are not there — the model reads, it never knows.


type ImpairmentReason = Literal["obsolescence", "restructuring", "other"]
type ArrKind = Literal["arr", "annualized_revenue", "revenue_run_rate"]
type FundingKind = Literal["priced_round", "tender", "convertible", "debt", "round_cut"]
type IpoKind = Literal["filed", "postponed", "withdrawn", "priced"]
type PriceVsRange = Literal["above", "within", "below", "unknown"]
type CapacityKind = Literal["cancel", "reduce", "delay", "resell_capacity", "sell_gpus_discount", "expand"]


class Quote(BaseModel):
    source_id: str = Field(description="the id of the document the words come from, exactly as given")
    text: str = Field(description="words copied verbatim from that document, 5–40 words")


class GrowthClaim(BaseModel):
    """A year-over-year growth rate stated in an earnings release."""

    found: bool = Field(description="false when the documents do not state it")
    growth_percent: float = Field(description="e.g. 39 for 'grew 39%'; 0 when not found")
    quote: Quote = Field(description="the words that state it; empty text when not found")


class UsefulLifeClaim(BaseModel):
    found: bool
    years_max: float = Field(description="the longest useful life the filing gives servers / network equipment, in years")
    years_min: float = Field(description="the shortest, equal to years_max when one number is given")
    changed_in_this_filing: bool = Field(description="true when the filing announces a change of the estimate")
    quote: Quote = Field(description="the words that state it; empty text when not found")


class ImpairmentClaim(BaseModel):
    is_compute_hardware: bool = Field(description="true only for servers, GPUs, accelerators, AI/data center equipment")
    reason: ImpairmentReason
    amount_usd: float = Field(description="0 when not stated")
    quote: Quote = Field(description="the words that state it; empty text when not found")


class ImpairmentClaims(BaseModel):
    claims: list[ImpairmentClaim]


class ArrClaim(BaseModel):
    lab: str = Field(description="OpenAI, Anthropic, …")
    amount_usd: float = Field(description="annualised revenue in US dollars, e.g. 5000000000")
    is_lower_bound: bool = Field(description="true for 'more than', 'over', 'at least'")
    as_of_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="the month the figure describes, YYYY-MM, e.g. 2026-09")
    metric_kind: ArrKind
    quote: Quote


class ArrClaims(BaseModel):
    claims: list[ArrClaim]


class FundingEvent(BaseModel):
    company: str
    kind: FundingKind
    post_money_usd: float = Field(description="valuation after the round in US dollars; 0 when not stated")
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM, e.g. 2026-09")
    protective_terms: bool = Field(description="tranches, ratchets or liquidation preference above 1x are reported")
    quote: Quote


class FundingEvents(BaseModel):
    events: list[FundingEvent]


class IpoEvent(BaseModel):
    company: str
    kind: IpoKind
    price_vs_range: PriceVsRange
    first_day_below_offer: bool
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM, e.g. 2026-09")
    quote: Quote


class IpoEvents(BaseModel):
    events: list[IpoEvent]


class CapacityEvent(BaseModel):
    who: str = Field(description="the company cutting or buying capacity")
    counterparty: str
    kind: CapacityKind
    size_usd: float = Field(description="0 when not stated")
    size_mw: float = Field(description="0 when not stated")
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM, e.g. 2026-09")
    quote: Quote


class CapacityEvents(BaseModel):
    events: list[CapacityEvent]


class TokenVolumeClaim(BaseModel):
    found: bool
    tokens_per_month: float = Field(description="tokens processed per month, e.g. 1.3e15 for 1.3 quadrillion")
    quote: Quote = Field(description="the words that state it; empty text when not found")
