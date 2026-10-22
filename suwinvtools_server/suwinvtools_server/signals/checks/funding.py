"""Category D — funding of the labs: does the money that pays for the compute keep coming?"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import override

from suwinvtools_library.marketdata.edgar import paragraphs_with
from suwinvtools_server.signals.checks.base import (
    READ_ERRORS,
    Check,
    CheckMeta,
    Context,
    ReadResult,
    ask_news,
    by_subject,
    confirmed,
    is_news,
    month,
    pct,
    usd,
    verified,
)
from suwinvtools_server.signals.checks.hardware import SEARCH_DAYS
from suwinvtools_server.signals.llm import Document, LlmError, states_number, verify
from suwinvtools_server.signals.model import (
    CapacityEvent,
    CapacityEvents,
    Category,
    Evidence,
    FundingEvents,
    IpoEvents,
    JsonValue,
    Outcome,
    Reading,
    Verdict,
)

LABS = ("OpenAI", "Anthropic", "xAI", "Mistral", "Safe Superintelligence", "Thinking Machines")


def _domains(reading: Reading) -> list[str]:
    domains = reading.data.get("domains")
    return [str(domain) for domain in domains] if isinstance(domains, list) else []


def _claims_verdict(reading: Reading, verdict: Verdict) -> Verdict:
    """A red or green from the news waits for a second outlet; a filing is enough on its own."""
    if verdict in {Verdict.RED, Verdict.GREEN} and not confirmed(_domains(reading), primary=reading.data.get("primary") is True):
        return Verdict.UNCONFIRMED
    return verdict


# D1 -------------------------------------------------------------------------------------------

FLAT_BAND = 0.05
FLAT_MONTHS = 9
STRONG_RISE = 0.25
FUNDING_KINDS = ("priced_round", "tender", "convertible", "debt", "round_cut")


class LabFunding(Check):
    meta = CheckMeta(
        id="D1",
        category=Category.D,
        title="Wyceny w rundach labów",
        question="Czy laby nadal zbierają pieniądze po wyższej wycenie i bez zaostrzonych warunków?",
        rule_red=(
            "runda obcięta, twarde warunki (transze, ratchety, preferencja > 1x), wycena niższa niż poprzednia "
            f"albo płaska (±{FLAT_BAND:.0%}) po ≥ {FLAT_MONTHS} miesiącach; potwierdzone przez 2 źródła"
        ),
        rule_green=f"wycena wyższa o ≥ {STRONG_RISE:.0%} od poprzedniej",
        unit="USD (wycena post-money)",
        caveat="Wyceny pochodzą z doniesień prasy, nie z dokumentów; oferta wtórna (tender) bywa wyceniana inaczej niż runda.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for lab in LABS:
            query = f'"{lab}" (funding OR valuation OR raises OR "tender offer")'
            try:
                answer, documents, found = ask_news(
                    ctx, query, FundingEvents, f"List every funding round, tender or valuation of {lab} the headlines state."
                )
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(lab, month(ctx.today), Verdict.INVALID, str(exc)))
                continue
            readings: dict[str, Reading] = {}
            for event in answer.events if answer else []:
                checked = verified(event.quote, documents, found)
                if checked is None or event.company.lower() != lab.lower() or event.kind not in FUNDING_KINDS:
                    continue
                if not is_news(event.month, ctx.today):
                    continue
                if event.post_money_usd and not states_number(event.quote.text, event.post_money_usd):
                    continue
                evidence, domain = checked
                period = f"{event.month[:7]} {event.kind}"
                earlier = readings.get(period)
                domains = sorted({domain, *(_domains(earlier) if earlier else [])} - {""})
                readings[period] = Reading(
                    check_id=self.meta.id,
                    subject=lab,
                    period=period,
                    value=max(event.post_money_usd, (earlier.value or 0) if earlier else 0),
                    data={
                        "protective_terms": event.protective_terms
                        or (earlier is not None and earlier.data.get("protective_terms") is True),
                        "domains": list[JsonValue](domains),
                    },
                    evidence=(*(earlier.evidence if earlier else ()), evidence),
                )
            if readings:
                result.readings.extend(readings.values())
            else:
                result.skipped.append(self.skip(lab, month(ctx.today), Verdict.NOT_READY, "brak nowych doniesień o rundach"))
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for lab, periods in by_subject(history).items():
            ordered = sorted(periods.values(), key=lambda reading: reading.period)
            for index, reading in enumerate(ordered):
                priced = [earlier for earlier in ordered[:index] if (earlier.value or 0) > 0 and earlier.period[:7] <= reading.period[:7]]
                outcomes.append(self._judge(lab, reading, priced[-1] if priced else None))
        return outcomes

    def _judge(self, lab: str, reading: Reading, previous: Reading | None) -> Outcome:
        value, kind = reading.value or 0.0, reading.period.partition(" ")[2]
        line = f"{lab}: {kind} {reading.period[:7]}" + (f", wycena {usd(value)}" if value else ", wycena niepodana")
        notes: list[str] = []
        verdict = Verdict.NEUTRAL
        if kind == "round_cut":
            verdict = Verdict.RED
            notes.append("runda została obcięta")
        if reading.data.get("protective_terms") is True:
            verdict = Verdict.RED
            notes.append("inwestorzy dostali zaostrzone warunki (transze, ratchety lub preferencja)")
        if previous is not None and value > 0 and previous.value:
            change = value / previous.value - 1
            line += f" wobec {usd(previous.value)} ({previous.period[:7]}): {pct(change)}"
            months_between = _months_between(previous.period[:7], reading.period[:7])
            if change < 0:
                verdict = Verdict.RED
                notes.append("wycena niższa niż w poprzedniej rundzie")
            elif abs(change) <= FLAT_BAND and months_between >= FLAT_MONTHS:
                verdict = Verdict.RED
                notes.append(f"wycena stoi w miejscu od {months_between} miesięcy")
            elif change >= STRONG_RISE and verdict is Verdict.NEUTRAL:
                verdict = Verdict.GREEN
        elif previous is None and verdict is Verdict.NEUTRAL:
            verdict = Verdict.BASELINE
        summary = " ".join([line + ".", *(f"{note.capitalize()}." for note in notes)])
        return self.outcome(reading, _claims_verdict(reading, verdict), summary)


def _months_between(earlier: str, later: str) -> int:
    return (int(later[:4]) - int(earlier[:4])) * 12 + int(later[5:7]) - int(earlier[5:7])


# D2 -------------------------------------------------------------------------------------------

IPO_KINDS = ("filed", "postponed", "withdrawn", "priced")


class LabIpo(Check):
    meta = CheckMeta(
        id="D2",
        category=Category.D,
        title="Debiuty giełdowe labów",
        question="Czy wejścia laboratoriów AI na giełdę dochodzą do skutku i jak wypadają?",
        rule_red=(
            "debiut odłożony lub wycofany, cena poniżej widełek albo pierwszy dzień poniżej ceny oferty; "
            "potwierdzone przez 2 źródła lub formularz RW"
        ),
        rule_green="cena oferty powyżej widełek; potwierdzone przez 2 źródła",
        unit="—",
        caveat="Doniesienia prasowe, aż do formularza w SEC; dopóki żaden lab nie złożył wniosku o IPO, sygnał milczy.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        period = month(ctx.today)
        for lab in LABS:
            readings: dict[str, Reading] = {}
            query = f'"{lab}" IPO (postponed OR delayed OR withdrawn OR priced OR filed)'
            try:
                answer, documents, found = ask_news(
                    ctx, query, IpoEvents, f"List every IPO event of {lab} (filing, postponement, withdrawal, pricing) the headlines state."
                )
                for event in answer.events if answer else []:
                    checked = verified(event.quote, documents, found)
                    if checked is None or event.company.lower() != lab.lower() or event.kind not in IPO_KINDS:
                        continue
                    if not is_news(event.month, ctx.today):
                        continue
                    evidence, domain = checked
                    readings[f"{event.month[:7]} {event.kind}"] = Reading(
                        check_id=self.meta.id,
                        subject=lab,
                        period=f"{event.month[:7]} {event.kind}",
                        value=None,
                        data={
                            "price_vs_range": event.price_vs_range,
                            "first_day_below_offer": event.first_day_below_offer,
                            "domains": list[JsonValue]([domain]),
                        },
                        evidence=(evidence,),
                    )
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(lab, period, Verdict.INVALID, str(exc)))
            try:
                for hit in ctx.edgar.search(f'"{lab}"', forms=("RW",), start=ctx.today - timedelta(days=SEARCH_DAYS), end=ctx.today):
                    if lab.lower() not in hit.company.lower():
                        continue
                    key = f"{hit.filed:%Y-%m} withdrawn"
                    readings[key] = Reading(
                        check_id=self.meta.id,
                        subject=lab,
                        period=key,
                        value=None,
                        data={"price_vs_range": "unknown", "first_day_below_offer": False, "primary": True},
                        evidence=(Evidence(url=hit.url, title=f"SEC — wycofanie rejestracji (RW) {hit.company}"),),
                    )
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(lab, period, Verdict.INVALID, f"EDGAR: {exc}"))
            if readings:
                result.readings.extend(readings.values())
            elif not any(item.subject == lab for item in result.skipped):
                result.skipped.append(self.skip(lab, period, Verdict.NOT_READY, "brak nowych doniesień o IPO"))
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for lab, periods in by_subject(history).items():
            for reading in periods.values():
                kind = reading.period.partition(" ")[2]
                below = reading.data.get("price_vs_range") == "below" or reading.data.get("first_day_below_offer") is True
                above = reading.data.get("price_vs_range") == "above"
                verdict = Verdict.NEUTRAL
                what = f"{lab}: IPO — {kind} ({reading.period[:7]})."
                if kind in {"postponed", "withdrawn"}:
                    verdict, what = Verdict.RED, f"{lab}: IPO {'odłożone' if kind == 'postponed' else 'wycofane'} ({reading.period[:7]})."
                elif kind == "priced" and below:
                    verdict, what = (
                        Verdict.RED,
                        f"{lab}: IPO wyceniono poniżej widełek lub kurs spadł poniżej ceny oferty ({reading.period[:7]}).",
                    )
                elif kind == "priced" and above:
                    verdict, what = Verdict.GREEN, f"{lab}: IPO wyceniono powyżej widełek ({reading.period[:7]})."
                outcomes.append(self.outcome(reading, _claims_verdict(reading, verdict), what))
        return outcomes


# D3 -------------------------------------------------------------------------------------------

# Subject -> the lowercase names a news item calls it by. Labs by name, companies by ticker.
ALIASES: dict[str, tuple[str, ...]] = {
    **{lab: (lab.lower(),) for lab in LABS},
    "MSFT": ("microsoft",),
    "AMZN": ("amazon", "aws"),
    "GOOGL": ("google", "alphabet"),
    "META": ("meta",),
    "ORCL": ("oracle",),
    "CRWV": ("coreweave",),
    "NBIS": ("nebius",),
}
CAPACITY_WORDS = '("data center" OR compute OR capacity OR lease)'
CUT_WORDS = '(cancel OR "scale back" OR "walk away" OR renegotiate OR "sell GPUs")'
CUT_KINDS = ("cancel", "reduce", "delay", "resell_capacity", "sell_gpus_discount")
BIG_USD = 1e9
BIG_MW = 500.0
FILERS = tuple(subject for subject in ALIASES if subject not in LABS)


def _subject_of(*names: str) -> str | None:
    lowered = [name.lower() for name in names]
    return next((subject for subject, aliases in ALIASES.items() if any(alias in name for name in lowered for alias in aliases)), None)


class ComputeCuts(Check):
    meta = CheckMeta(
        id="D3",
        category=Category.D,
        title="Odwoływanie i odsprzedaż mocy obliczeniowej",
        question="Czy laby i giganci anulują, ograniczają lub odsprzedają zamówioną moc (centra danych, GPU)?",
        rule_red=(
            "anulowanie, ograniczenie, opóźnienie lub odsprzedaż mocy albo wyprzedaż GPU ze zniżką; "
            "potwierdzone przez 2 źródła lub zgłoszenie 8-K (pkt 1.02)"
        ),
        rule_green=f"rozbudowa o ≥ {usd(BIG_USD)} albo ≥ {BIG_MW:.0f} MW",
        unit="USD",
        caveat="Doniesienia prasowe mieszają plany z umowami; 8-K z punktem 1.02 dotyczy też spraw bez związku z mocą obliczeniową.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        period = month(ctx.today)
        readings: dict[tuple[str, str], Reading] = {}
        for subject, aliases in ALIASES.items():
            query = f'"{aliases[0]}" {CAPACITY_WORDS} {CUT_WORDS}'
            task = f"List every cancelled, reduced, delayed, resold or expanded compute capacity of {subject} the headlines state."
            try:
                answer, documents, found = ask_news(ctx, query, CapacityEvents, task)
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(subject, period, Verdict.INVALID, str(exc)))
                continue
            for event in answer.events if answer else []:
                checked = verified(event.quote, documents, found)
                if checked is not None and _subject_of(event.who, event.counterparty) == subject and is_news(event.month, ctx.today):
                    self._keep(readings, subject, event, checked)
        for ticker in FILERS:
            try:
                for url, text in self._terminations(ctx, ticker):
                    document = Document(id="d1", title=f"8-K {ticker} (pkt 1.02)", url=url, text=text)
                    task = f"Does this 8-K end, reduce or delay a compute or data center agreement of {ticker}? List each such event."
                    if ctx.extract is None:
                        raise LlmError("brak skonfigurowanego LLM")
                    answer = ctx.extract(CapacityEvents, task, [document])
                    for event in answer.events if isinstance(answer, CapacityEvents) else []:
                        evidence = verify(event.quote, [document])
                        if evidence is not None and is_news(event.month, ctx.today):
                            self._keep(readings, ticker, event, (evidence, ""), primary=True)
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(ticker, period, Verdict.INVALID, f"8-K: {exc}"))
        result.readings.extend(readings.values())
        if not readings and not result.skipped:
            result.skipped.append(self.skip("moc obliczeniowa", period, Verdict.NOT_READY, "brak nowych doniesień o zmianach mocy"))
        return result

    @staticmethod
    def _terminations(ctx: Context, ticker: str) -> list[tuple[str, str]]:
        """URL and text of the 8-Ks with item 1.02 the company filed lately."""
        cik = ctx.edgar.cik(ticker)
        since = ctx.today - timedelta(days=SEARCH_DAYS)
        filings = [f for f in ctx.edgar.filings(cik) if f.form.startswith("8-K") and "1.02" in f.items and f.filed >= since] if cik else []
        return [(filing.url, "\n\n".join(paragraphs_with(ctx.edgar.text(filing.url), "terminat", limit=4))[:12_000]) for filing in filings]

    def _keep(
        self,
        readings: dict[tuple[str, str], Reading],
        subject: str,
        event: CapacityEvent,
        source: tuple[Evidence, str],
        *,
        primary: bool = False,
    ) -> None:
        evidence, domain = source
        key = (subject, f"{event.month[:7]} {event.kind}")
        earlier = readings.get(key)
        domains = sorted({domain, *(_domains(earlier) if earlier else [])} - {""})
        readings[key] = Reading(
            check_id=self.meta.id,
            subject=subject,
            period=key[1],
            value=event.size_usd or None,
            data={
                "size_usd": event.size_usd,
                "size_mw": event.size_mw,
                "counterparty": event.counterparty,
                "domains": list[JsonValue](domains),
                "primary": primary or (earlier is not None and earlier.data.get("primary") is True),
            },
            evidence=(*(earlier.evidence if earlier else ()), evidence),
        )

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for subject, periods in by_subject(history).items():
            for reading in periods.values():
                kind = reading.period.partition(" ")[2]
                size_usd, size_mw = float(reading.data.get("size_usd") or 0), float(reading.data.get("size_mw") or 0)  # pyright: ignore[reportArgumentType] — JsonValue narrowed by the or-0
                size = ", ".join(part for part in (usd(size_usd) if size_usd else "", f"{size_mw:g} MW" if size_mw else "") if part)
                what = f"{subject}: {kind} ({reading.period[:7]})" + (f", skala: {size}" if size else "") + "."
                verdict = Verdict.NEUTRAL
                if kind in CUT_KINDS:
                    verdict = Verdict.RED
                elif kind == "expand" and (size_usd >= BIG_USD or size_mw >= BIG_MW):
                    verdict = Verdict.GREEN
                outcomes.append(self.outcome(reading, _claims_verdict(reading, verdict), what))
        return outcomes
