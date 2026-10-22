"""Category C — Jevons' paradox: does cheaper intelligence make people spend more on it?"""

from collections.abc import Sequence
from datetime import date
from typing import override

from suwinvtools_library.marketdata.edgar import paragraphs_with, quarter_before
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
    quarter_end,
    quarter_of_month,
    shift_quarter,
    usd,
)
from suwinvtools_server.signals.checks.monetization import earnings_releases
from suwinvtools_server.signals.llm import Document, states_number, verify
from suwinvtools_server.signals.model import Category, Evidence, Outcome, Reading, TokenVolumeClaim, Verdict
from suwinvtools_server.signals.sources.openrouter import MODELS_URL, RANKINGS_URL, prices_from_models, token_market, usage_from_rankings

# C1 -------------------------------------------------------------------------------------------

OPENROUTER = "OpenRouter"
# A quarter is judged when at least this many of its three months were read.
MIN_MONTHS = 2


class TokenSpend(Check):
    meta = CheckMeta(
        id="C1",
        category=Category.C,
        title="Wydatki na tokeny a ich ilość",
        question="Czy taniejące tokeny nadal oznaczają rosnące wydatki (Jevons), czy wolumen już nie nadrabia ceny?",
        rule_red="wydatki na tokeny spadają kw/kw dwa kwartały z rzędu, choć liczba tokenów rośnie (trzeci raz: „scenariusz telekomów”)",
        rule_green="wydatki na tokeny rosną kw/kw (podajemy, ile z wolumenu, a ile z ceny)",
        unit="USD/dzień",
        caveat="Jeden dzień w miesiącu, 20 najpopularniejszych modeli, próba skrzywiona w stronę programistów; ceny katalogowe.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        period = month(ctx.today)
        if ctx.latest_period(self.meta.id, OPENROUTER) == period:
            return ReadResult(skipped=[self.skip(OPENROUTER, period, Verdict.NOT_READY, "dane z tego miesiąca już odczytane")])
        try:
            usage = usage_from_rankings(ctx.fetch(RANKINGS_URL))
            market = token_market(usage, prices_from_models(ctx.fetch(MODELS_URL)))
        except READ_ERRORS as exc:
            return ReadResult(skipped=[self.skip(OPENROUTER, period, Verdict.INVALID, str(exc))])
        reading = Reading(
            check_id=self.meta.id,
            subject=OPENROUTER,
            period=period,
            value=market.spend,
            data={"tokens": market.tokens, "priced_share": round(market.priced_share, 3), "day": market.day, "models": market.models},
            evidence=(Evidence(url=RANKINGS_URL, title=f"OpenRouter — ranking modeli z {market.day}"),),
        )
        return ReadResult(readings=[reading])

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        months = by_subject(history).get(OPENROUTER, {})
        # quarter -> (mean spend, mean tokens, last month's reading), for closed quarters with enough months.
        quarters: dict[str, tuple[float, float, Reading]] = {}
        for quarter in sorted({quarter_of_month(period) for period in months}):
            if quarter_end(quarter) >= today:
                continue
            readings = [months[period] for period in sorted(months) if quarter_of_month(period) == quarter]
            if len(readings) >= MIN_MONTHS:
                quarters[quarter] = (
                    sum(r.value or 0 for r in readings) / len(readings),
                    sum(number(r, "tokens") or 0 for r in readings) / len(readings),
                    readings[-1],
                )
        closed = sorted(quarters)
        if not closed:
            return []
        last = closed[-1]
        reading = Reading(
            check_id=self.meta.id, subject=OPENROUTER, period=last, value=quarters[last][0], evidence=quarters[last][2].evidence
        )
        if len(closed) < 2 or closed[-2] != shift_quarter(last, -1):
            return [
                self.outcome(
                    reading, Verdict.BASELINE, f"OpenRouter {last}: {usd(quarters[last][0])} dziennie — pierwszy zamknięty kwartał."
                )
            ]

        def step(quarter: str) -> tuple[float, float] | None:
            before = quarters.get(shift_quarter(quarter, -1))
            if before is None or not before[0] or not before[1]:
                return None
            return quarters[quarter][0] / before[0] - 1, quarters[quarter][1] / before[1] - 1

        spend_change, token_change = step(last) or (0.0, 0.0)
        line = f"OpenRouter {last}: {usd(quarters[last][0])} dziennie ({pct(spend_change)} kw/kw), tokeny {pct(token_change)}."
        run = 0
        quarter = last
        while (moved := step(quarter)) is not None and moved[0] < 0 < moved[1]:
            run, quarter = run + 1, shift_quarter(quarter, -1)
        if run >= 2:
            tail = " Trzeci kwartał z rzędu — scenariusz telekomów: wolumen rośnie, przychód nie." if run >= 3 else ""
            return [self.outcome(reading, Verdict.RED, f"Tokeny tanieją szybciej, niż rośnie ich użycie. {line}{tail}")]
        if spend_change > 0:
            price_change = (1 + spend_change) / (1 + token_change) - 1
            return [
                self.outcome(
                    reading,
                    Verdict.GREEN,
                    f"Wydatki na tokeny rosną: wolumen {pct(token_change)}, cena za token {pct(price_change)}. {line}",
                )
            ]
        return [self.outcome(reading, Verdict.NEUTRAL, line)]


# C2 -------------------------------------------------------------------------------------------

REPORTERS = ("GOOGL", "MSFT")


class HyperscalerTokens(Check):
    meta = CheckMeta(
        id="C2",
        category=Category.C,
        title="Tokeny przetwarzane przez Google i Microsoft",
        question="Ile tokenów miesięcznie przetwarzają Google i Microsoft i jak szybko to rośnie?",
        rule_red="brak — kontekst, nigdy nie wysyła alarmu",
        rule_green="brak — kontekst, nigdy nie wysyła alarmu",
        unit="tokenów/miesiąc",
        caveat="Firmy podają liczbę tokenów nieregularnie i według własnej definicji.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for ticker in REPORTERS:
            try:
                cik = ctx.edgar.cik(ticker)
                releases = earnings_releases(ctx.edgar, cik) if cik else []
                if not releases:
                    result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, f"brak komunikatów wynikowych {ticker} w EDGAR"))
                    continue
                period = quarter_before(releases[0].filed)
                if ctx.latest_period(self.meta.id, ticker) == period:
                    result.skipped.append(self.skip(ticker, period, Verdict.NOT_READY, "brak nowego komunikatu wynikowego"))
                    continue
                url = ctx.edgar.exhibit(releases[0])
                passages = paragraphs_with(ctx.edgar.text(url), "token") if url else []
                if not url or not passages:
                    result.skipped.append(self.skip(ticker, period, Verdict.INVALID, f"komunikat {ticker} nie podaje liczby tokenów"))
                    continue
                if ctx.extract is None:
                    result.skipped.append(self.skip(ticker, period, Verdict.INVALID, "brak skonfigurowanego LLM"))
                    continue
                document = Document(id="d1", title=f"komunikat wynikowy {ticker}", url=url, text="\n\n".join(passages))
                claim = ctx.extract(TokenVolumeClaim, "State how many tokens per month the company processes.", [document])
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, str(exc)))
                continue
            evidence = verify(claim.quote, [document]) if isinstance(claim, TokenVolumeClaim) else None
            if (
                not isinstance(claim, TokenVolumeClaim)
                or not claim.found
                or evidence is None
                or not states_number(evidence.quote, claim.tokens_per_month)
            ):
                result.skipped.append(self.skip(ticker, period, Verdict.INVALID, f"{ticker}: brak zweryfikowanej liczby tokenów"))
                continue
            result.readings.append(
                Reading(check_id=self.meta.id, subject=ticker, period=period, value=claim.tokens_per_month, evidence=(evidence,))
            )
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for ticker, periods in by_subject(history).items():
            now = periods[max(periods)]
            line = f"{ticker}: {(now.value or 0):.3g} tokenów miesięcznie ({now.period})"
            year_ago = periods.get(shift_quarter(now.period, -4))
            if year_ago is not None and year_ago.value and now.value:
                line += f", {pct(now.value / year_ago.value - 1, 0)} r/r"
            outcomes.append(self.outcome(now, Verdict.NEUTRAL, line + "."))
        return outcomes
