"""Category B — wear of the hardware: do the buyers of GPUs still believe they last?"""

import itertools
from collections.abc import Sequence
from datetime import date, timedelta
from typing import override

from suwinvtools_library.marketdata.edgar import (
    FACTS_URL,
    REVENUE_TAGS,
    RPO_TAGS,
    Filing,
    calendar_quarter,
    instants,
    paragraphs_with,
    quarterly_flows,
)
from suwinvtools_server.signals.checks.base import (
    READ_ERRORS,
    Check,
    CheckMeta,
    Context,
    ReadResult,
    by_subject,
    month,
    number,
    pct,
    shift_month,
    usd,
)
from suwinvtools_server.signals.llm import Document, states_number, verify
from suwinvtools_server.signals.model import Category, Evidence, ImpairmentClaims, Outcome, Reading, UsefulLifeClaim, Verdict
from suwinvtools_server.signals.sources.vast import FAMILIES, family_price

# B1 -------------------------------------------------------------------------------------------

BUYERS = ("MSFT", "AMZN", "GOOGL", "META", "ORCL", "CRWV")


# 10-Qs often leave the useful lives to the 10-K, so a few of the newest reports are tried.
REPORTS_TRIED = 4


class DepreciationLife(Check):
    meta = CheckMeta(
        id="B1",
        category=Category.B,
        title="Skracanie okresu amortyzacji serwerów",
        question="Czy któryś z gigantów skrócił księgowy okres użytkowania serwerów?",
        rule_red="najdłuższy okres użytkowania serwerów w ostatnim 10-K/10-Q jest krótszy niż w poprzednim",
        rule_green="okres jest dłuższy niż w poprzednim raporcie (uwaga: dłuższy okres także poprawia EPS)",
        unit="lat",
        caveat=(
            "Amazon skrócił część serwerów z 6 do 5 lat od 2025-01-01, dlatego porównujemy z zapisanym "
            "poprzednim raportem, a nie z „pierwszym razem w historii”."
        ),
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for ticker in BUYERS:
            try:
                reading = self._read_company(ctx, ticker)
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, str(exc)))
                continue
            if isinstance(reading, Reading):
                result.readings.append(reading)
            else:
                result.skipped.append(reading)
        return result

    def _read_company(self, ctx: Context, ticker: str) -> Reading | Outcome:
        """The reading from the newest report that describes the useful lives, or why there is none."""
        cik = ctx.edgar.cik(ticker)
        reports = [f for f in ctx.edgar.filings(cik) if f.form in {"10-K", "10-Q"} and f.report_date] if cik else []
        if not reports:
            return self.skip(ticker, "—", Verdict.INVALID, f"brak 10-K/10-Q {ticker} w EDGAR")
        for filing in reports[:REPORTS_TRIED]:
            period = calendar_quarter(filing.report_date or ctx.today)
            passages = [p for p in paragraphs_with(ctx.edgar.text(filing.url), "useful life", "useful lives") if _mentions_servers(p)]
            if not passages:
                continue
            if (ctx.latest_period(self.meta.id, ticker) or "") >= period:
                return self.skip(ticker, period, Verdict.NOT_READY, "brak nowego 10-K/10-Q z opisem okresu użytkowania")
            return self._ask(ctx, ticker, filing, period, passages)
        return self.skip(ticker, "—", Verdict.INVALID, f"{ticker}: żaden z ostatnich raportów nie opisuje okresu użytkowania serwerów")

    def _ask(self, ctx: Context, ticker: str, filing: Filing, period: str, passages: list[str]) -> Reading | Outcome:
        """The model reads the passages; its quote must be in them and state the number."""
        if ctx.extract is None:
            return self.skip(ticker, period, Verdict.INVALID, "brak skonfigurowanego LLM")
        document = Document(id="d1", title=f"{filing.form} {ticker}", url=filing.url, text="\n\n".join(passages))
        claim = ctx.extract(UsefulLifeClaim, "State the useful life, in years, the filing gives servers and network equipment.", [document])
        if not isinstance(claim, UsefulLifeClaim) or not claim.found:
            return self.skip(ticker, period, Verdict.INVALID, f"{ticker}: model nie znalazł okresu użytkowania serwerów")
        evidence = verify(claim.quote, [document])
        if evidence is None or not states_number(evidence.quote, claim.years_max):
            return self.skip(ticker, period, Verdict.INVALID, f"{ticker}: cytat o okresie użytkowania nie przeszedł weryfikacji")
        return Reading(
            check_id=self.meta.id,
            subject=ticker,
            period=period,
            value=claim.years_max,
            data={"years_min": claim.years_min, "changed": claim.changed_in_this_filing},
            evidence=(evidence,),
        )

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        grouped = by_subject(history)
        outcomes: list[Outcome] = []
        for ticker, periods in grouped.items():
            ordered = sorted(periods)
            now = periods[ordered[-1]]
            if len(ordered) < 2:
                outcomes.append(
                    self.outcome(now, Verdict.BASELINE, f"{ticker}: okres użytkowania serwerów {_years(now)} — pierwszy zapisany odczyt.")
                )
                continue
            before = periods[ordered[-2]]
            line = f"{ticker}: okres użytkowania serwerów {_years(now)} wobec {_years(before)} ({before.period})."
            if (now.value or 0) < (before.value or 0):
                first = not any(self._shortened(other, now.period) for name, other in grouped.items() if name != ticker)
                head = (
                    "Pierwszy gigant skraca okres użytkowania serwerów. " if first else "Kolejny gigant skraca okres użytkowania serwerów. "
                )
                outcomes.append(self.outcome(now, Verdict.RED, head + line))
            elif (now.value or 0) > (before.value or 0):
                outcomes.append(
                    self.outcome(
                        now, Verdict.GREEN, line + " Dłuższy okres także poprawia zysk na akcję, więc to nie dowód na trwałość sprzętu."
                    )
                )
            else:
                outcomes.append(self.outcome(now, Verdict.NEUTRAL, line))
        return outcomes

    @staticmethod
    def _shortened(periods: dict[str, Reading], before: str) -> bool:
        ordered = [period for period in sorted(periods) if period < before]
        return any((periods[b].value or 0) < (periods[a].value or 0) for a, b in itertools.pairwise(ordered))


def _mentions_servers(passage: str) -> bool:
    lowered = passage.lower()
    return "server" in lowered or "network" in lowered


def _years(reading: Reading) -> str:
    low = number(reading, "years_min")
    high = reading.value or 0.0
    return f"{low:g}–{high:g} lat" if low is not None and low != high else f"{high:g} lat"


# B2 -------------------------------------------------------------------------------------------

IMPAIRERS = (*BUYERS, "IREN", "APLD")
SEARCH_DAYS = 35
IMPAIRMENT_QUERIES = (
    '"impairment" "GPU"',
    '"impairment" "servers"',
    '"accelerated depreciation" "servers"',
    '"accelerated depreciation" "GPU"',
)
HARDWARE_WORDS = ("gpu", "server", "accelerator", "data center", "compute")


class ComputeImpairment(Check):
    meta = CheckMeta(
        id="B2",
        category=Category.B,
        title="Odpis sprzętu AI z powodu starzenia",
        question="Czy któraś spółka odpisała lub przyspieszyła amortyzację GPU/serwerów, bo się zestarzały?",
        rule_red="w zgłoszeniu do SEC z ostatnich 35 dni jest odpis lub przyspieszona amortyzacja sprzętu z powodu starzenia",
        rule_green="brak — ten sygnał bywa tylko czerwony",
        unit="USD",
        caveat="Szukamy pełnotekstowo w zgłoszeniach SEC; odpis bez podanej kwoty ma wartość 0.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        period = month(ctx.today)
        ciks = {cik: ticker for ticker in IMPAIRERS if (cik := ctx.edgar.cik(ticker))}
        try:
            hits = {
                hit.url: hit
                for query in IMPAIRMENT_QUERIES
                for hit in ctx.edgar.search(
                    query, forms=("10-Q", "10-K", "8-K"), start=ctx.today - timedelta(days=SEARCH_DAYS), end=ctx.today, ciks=ciks
                )
                if hit.cik.lstrip("0") in {cik.lstrip("0") for cik in ciks}
            }
        except READ_ERRORS as exc:
            result.skipped.append(self.skip("EDGAR", period, Verdict.INVALID, str(exc)))
            return result
        if not hits:
            result.skipped.append(self.skip("EDGAR", period, Verdict.NOT_READY, "brak nowych zgłoszeń o odpisach sprzętu"))
            return result
        if ctx.extract is None:
            result.skipped.append(self.skip("EDGAR", period, Verdict.INVALID, "brak skonfigurowanego LLM"))
            return result
        names = {cik.lstrip("0"): ticker for cik, ticker in ciks.items()}
        found: dict[tuple[str, str], Reading] = {}
        for hit in hits.values():
            ticker = names[hit.cik.lstrip("0")]
            try:
                passages = [
                    p for p in paragraphs_with(ctx.edgar.text(hit.url), "impairment", "accelerated depreciation") if _mentions_hardware(p)
                ]
                if not passages:
                    continue
                document = Document(id="d1", title=f"{hit.form} {ticker}", url=hit.url, text="\n\n".join(passages))
                answer = ctx.extract(
                    ImpairmentClaims,
                    "List every impairment or accelerated depreciation of servers, GPUs or data center equipment.",
                    [document],
                )
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(ticker, period, Verdict.INVALID, str(exc)))
                continue
            for claim in answer.claims if isinstance(answer, ImpairmentClaims) else []:
                evidence = verify(claim.quote, [document])
                if not claim.is_compute_hardware or claim.reason != "obsolescence" or evidence is None:
                    continue
                if claim.amount_usd and not states_number(evidence.quote, claim.amount_usd):
                    continue
                key = (ticker, calendar_quarter(hit.filed))
                if key not in found or claim.amount_usd > (found[key].value or 0):
                    found[key] = Reading(check_id=self.meta.id, subject=ticker, period=key[1], value=claim.amount_usd, evidence=(evidence,))
        result.readings.extend(found.values())
        if not found and not result.skipped:
            result.skipped.append(self.skip("EDGAR", period, Verdict.NOT_READY, "zgłoszenia nie opisują odpisu sprzętu z powodu starzenia"))
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        return [
            self.outcome(
                reading,
                Verdict.RED,
                f"{reading.subject}: odpis lub przyspieszona amortyzacja sprzętu obliczeniowego z powodu starzenia"
                + (f" ({usd(reading.value)})" if reading.value else " (kwota niepodana)")
                + ". Źródło: zgłoszenie do SEC.",
            )
            for reading in history
        ]


def _mentions_hardware(passage: str) -> bool:
    lowered = passage.lower()
    return any(word in lowered for word in HARDWARE_WORDS)


# B3 -------------------------------------------------------------------------------------------

NEOCLOUDS = ("CRWV", "NBIS")
RPO_DROP = -0.05
RPO_SURGE = 0.10
COVERAGE_DROP = -0.10


class NeocloudBacklog(Check):
    meta = CheckMeta(
        id="B3",
        category=Category.B,
        title="Portfel kontraktów neochmur kurczy się",
        question="Czy zakontraktowane przychody (RPO) CoreWeave i Nebius rosną szybciej niż ich sprzedaż?",
        rule_red=(
            f"RPO kw/kw spada o więcej niż {-RPO_DROP:.0%}, albo pokrycie (RPO w miesiącach przychodu) "
            f"spada dwa kwartały z rzędu o łącznie ≥ {-COVERAGE_DROP:.0%}"
        ),
        rule_green=f"RPO kw/kw rośnie o ≥ {RPO_SURGE:.0%} i pokrycie nie spada",
        unit="USD",
        caveat="RPO to kontrakty, nie gotówka; część kontrahentów to sami giganci i laby.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for ticker in NEOCLOUDS:
            try:
                cik = ctx.edgar.cik(ticker)
                facts = ctx.edgar.facts(cik) if cik else {}
                backlog, revenue = instants(facts, RPO_TAGS), quarterly_flows(facts, REVENUE_TAGS)
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, str(exc)))
                continue
            if not backlog:
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, f"{ticker} nie raportuje RPO w XBRL"))
                continue
            ends = sorted(day for day in backlog if revenue.get(day, 0) > 0)
            if not ends:
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, f"{ticker}: brak kwartalnych przychodów do porównania z RPO"))
                continue
            latest = ctx.latest_period(self.meta.id, ticker)
            fresh = [day for day in ends if latest is None or calendar_quarter(day) > latest]
            if not fresh:
                result.skipped.append(self.skip(ticker, calendar_quarter(ends[-1]), Verdict.NOT_READY, "brak nowego kwartału z RPO"))
                continue
            for day in fresh:
                result.readings.append(
                    Reading(
                        check_id=self.meta.id,
                        subject=ticker,
                        period=calendar_quarter(day),
                        value=backlog[day],
                        data={"coverage_months": round(backlog[day] / revenue[day] * 3, 2), "revenue": revenue[day]},
                        evidence=(Evidence(url=FACTS_URL.format(cik=cik), title=f"SEC — dane XBRL {ticker}"),),
                    )
                )
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for ticker, periods in by_subject(history).items():
            ordered = [periods[period] for period in sorted(periods)]
            now = ordered[-1]
            if len(ordered) < 2:
                outcomes.append(self.outcome(now, Verdict.BASELINE, f"{ticker}: RPO {usd(now.value or 0)} — pierwszy zapisany kwartał."))
                continue
            before = ordered[-2]
            growth = (now.value or 0) / before.value - 1 if before.value else 0.0
            cover, cover_before = number(now, "coverage_months") or 0.0, number(before, "coverage_months") or 0.0
            line = f"{ticker}: RPO {usd(now.value or 0)} ({pct(growth)} kw/kw), pokrycie {cover:.1f} mies. (wcześniej {cover_before:.1f})."
            falling_twice = False
            if len(ordered) >= 3:
                cover_earlier = number(ordered[-3], "coverage_months") or 0.0
                falling_twice = cover < cover_before < cover_earlier and cover_earlier > 0 and cover / cover_earlier - 1 <= COVERAGE_DROP
            if growth < RPO_DROP or falling_twice:
                reason = "RPO spadło" if growth < RPO_DROP else "pokrycie spada drugi kwartał z rzędu"
                outcomes.append(self.outcome(now, Verdict.RED, f"Portfel kontraktów słabnie ({reason}). {line}"))
            elif growth >= RPO_SURGE and cover >= cover_before:
                outcomes.append(self.outcome(now, Verdict.GREEN, f"Portfel kontraktów rośnie szybciej niż sprzedaż. {line}"))
            else:
                outcomes.append(self.outcome(now, Verdict.NEUTRAL, line))
        return outcomes


# B4 -------------------------------------------------------------------------------------------

MIN_OFFERS = 5
H200_DROP = -0.20
AGE_RATIO_DROP = -0.15
FLOOR_3M = -0.05
GPU = "GPU"


class GpuRentalPrices(Check):
    meta = CheckMeta(
        id="B4",
        category=Category.B,
        title="Ceny wynajmu GPU",
        question="Czy cena godziny H100/H200/B200 spada, a starsze układy tanieją szybciej niż nowe?",
        rule_red=(
            f"mediana H200 spadła o ≥ {-H200_DROP:.0%} w 3 miesiące, albo stosunek cen H100/B200 spadł o ≥ {-AGE_RATIO_DROP:.0%} "
            "w 6 miesięcy („popyt zaczął płacić za wiek chipa”)"
        ),
        rule_green=f"żadna rodzina GPU nie potaniała o więcej niż {-FLOOR_3M:.0%} w 3 miesiące",
        unit="USD/h za GPU",
        caveat="vast.ai to rynek spot mniejszych hostów, a nie kontrakty neochmur; ceny bywają szumem.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        period = month(ctx.today)
        for family in FAMILIES:
            if ctx.latest_period(self.meta.id, family) == period:
                result.skipped.append(self.skip(family, period, Verdict.NOT_READY, "ceny z tego miesiąca już odczytane"))
                continue
            try:
                price = family_price(family, ctx.fetch)
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(family, period, Verdict.INVALID, str(exc)))
                continue
            if price is None or price.offers < MIN_OFFERS:
                result.skipped.append(self.skip(family, period, Verdict.INVALID, f"{family}: za mało ofert na vast.ai (< {MIN_OFFERS})"))
                continue
            result.readings.append(
                Reading(
                    check_id=self.meta.id,
                    subject=family,
                    period=period,
                    value=price.median,
                    data={"p25": price.p25, "offers": price.offers},
                )
            )
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        grouped = by_subject(history)
        periods = {period for series in grouped.values() for period in series}
        if not periods:
            return []
        newest = max(periods)

        def price(family: str, period: str) -> float | None:
            reading = grouped.get(family, {}).get(period)
            return reading.value if reading and reading.value else None

        def change(family: str, months: int) -> float | None:
            now, earlier = price(family, newest), price(family, shift_month(newest, -months))
            return now / earlier - 1 if now and earlier else None

        def ratio(period: str) -> float | None:
            high, flagship = price("H100", period), price("B200", period)
            return high / flagship if high and flagship else None

        evidence = tuple(item for family in grouped.values() if newest in family for item in family[newest].evidence)
        aggregate = Reading(check_id=self.meta.id, subject=GPU, period=newest, value=None, evidence=evidence)
        changes = {family: change(family, 3) for family in FAMILIES}
        line = ", ".join(
            f"{family} {price(family, newest):.2f} USD/h ({pct(delta)} w 3 mies.)"
            for family, delta in changes.items()
            if delta is not None and price(family, newest)
        )
        ratio_now, ratio_before = ratio(newest), ratio(shift_month(newest, -6))
        ratio_change = ratio_now / ratio_before - 1 if ratio_now and ratio_before else None
        if line == "" and ratio_change is None:
            return [self.outcome(aggregate, Verdict.BASELINE, "Ceny GPU: za mało historii do porównania (potrzeba 3 miesięcy).")]
        if changes["H200"] is not None and changes["H200"] <= H200_DROP:
            return [self.outcome(aggregate, Verdict.RED, f"H200 potaniał o {-changes['H200']:.0%} w 3 miesiące. {line}")]
        if ratio_change is not None and ratio_change <= AGE_RATIO_DROP:
            return [
                self.outcome(
                    aggregate,
                    Verdict.RED,
                    f"Stosunek cen H100/B200 spadł o {-ratio_change:.0%} w 6 miesięcy — popyt zaczął płacić za wiek chipa. {line}",
                )
            ]
        if all(delta is not None and delta >= FLOOR_3M for delta in changes.values()):
            return [self.outcome(aggregate, Verdict.GREEN, f"Ceny wynajmu GPU trzymają się. {line}")]
        return [self.outcome(aggregate, Verdict.NEUTRAL, line or "Ceny GPU: bez sygnału.")]
