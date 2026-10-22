"""Category A — monetisation against investment: do revenues from capacity grow as fast as
the spending on it?"""

import re
from collections.abc import Sequence
from datetime import date, timedelta
from typing import override

from suwinvtools_library.marketdata.edgar import CAPEX_TAGS, Edgar, Filing, calendar_quarter, quarter_before, quarterly_flows, trailing_sum
from suwinvtools_server.signals.checks.base import (
    Check,
    CheckMeta,
    Context,
    ReadResult,
    by_subject,
    confirmed,
    documents_from,
    median,
    number,
    pct,
    quarter_end,
    quarter_of_month,
    shift_quarter,
    usd,
    verified,
)
from suwinvtools_server.signals.llm import Document, LlmError, states_number, verify
from suwinvtools_server.signals.model import ArrClaims, Category, Evidence, GrowthClaim, JsonValue, Outcome, Reading, Verdict
from suwinvtools_server.signals.sources.http import SourceError
from suwinvtools_server.signals.sources.news import headlines, search_url

# A1 -------------------------------------------------------------------------------------------

# Cloud -> (ticker, the sentence of the earnings release that states its year-over-year growth).
CLOUDS: dict[str, tuple[str, str]] = {
    "AWS": ("AMZN", r"AWS segment sales increased (\d+(?:\.\d+)?)%"),
    "Azure": ("MSFT", r"Azure and other cloud services revenue (?:increased|grew) (\d+(?:\.\d+)?)%"),
    "Google Cloud": ("GOOGL", r"Google Cloud[^.\n]{0,100}?revenues? (?:increased|grew|rose|accelerating to) (\d+(?:\.\d+)?)%"),
}
# A slowdown counts when growth drops by at least this many points, two quarters running …
SLOWDOWN_POINTS = 1.0
# … while capex grows this many points faster than the cloud.
CAPEX_GAP_POINTS = 20.0
ACCELERATION_POINTS = 1.0
BASKET = "3 chmury"


def earnings_releases(edgar: Edgar, cik: str) -> list[Filing]:
    """8-Ks reporting results (item 2.02), newest first."""
    return [filing for filing in edgar.filings(cik) if filing.form.startswith("8-K") and "2.02" in filing.items]


class CloudVsCapex(Check):
    meta = CheckMeta(
        id="A1",
        category=Category.A,
        title="Chmura hamuje przy rosnącym capeksie",
        question="Czy przychody AWS, Azure i Google Cloud rosną tak szybko jak capex, który je buduje?",
        rule_red=(
            f"co najmniej 2 z 3 chmur: wzrost r/r spada 2 kwartały z rzędu (o ≥ {SLOWDOWN_POINTS:g} pp każdy) "
            f"i capex TTM rośnie o ≥ {CAPEX_GAP_POINTS:g} pp szybciej niż chmura"
        ),
        rule_green=f"co najmniej 2 z 3 chmur przyspieszają (wzrost r/r w górę o ≥ {ACCELERATION_POINTS:g} pp kw/kw)",
        unit="% r/r",
        caveat="Azure podaje tylko procent wzrostu, bez kwoty; capex obejmuje całą firmę, nie tylko chmurę.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for cloud, (ticker, pattern) in CLOUDS.items():
            cik = ctx.edgar.cik(ticker)
            releases = earnings_releases(ctx.edgar, cik) if cik else []
            if not releases or cik is None:
                result.skipped.append(self.skip(cloud, "—", Verdict.INVALID, f"brak komunikatów wynikowych {ticker} w EDGAR"))
                continue
            release = releases[0]
            period = quarter_before(release.filed)
            if ctx.latest_period(self.meta.id, cloud) == period:
                result.skipped.append(self.skip(cloud, period, Verdict.NOT_READY, "brak nowego komunikatu wynikowego"))
                continue
            capex = quarterly_flows(ctx.edgar.facts(cik), CAPEX_TAGS)
            ends = [day for day in capex if calendar_quarter(day) == period]
            if not ends:
                result.skipped.append(self.skip(cloud, period, Verdict.NOT_READY, f"capex {ticker} za {period} nie ma jeszcze w 10-Q"))
                continue
            ttm, ttm_before = trailing_sum(capex, ends[0]), _ttm_year_before(capex, ends[0])
            if ttm is None or ttm_before is None or ttm_before <= 0:
                result.skipped.append(self.skip(cloud, period, Verdict.INVALID, f"brak 8 kwartałów capeksu {ticker}"))
                continue
            url = ctx.edgar.exhibit(release)
            growth = self._growth(ctx, cloud, url, pattern) if url else None
            if growth is None:
                result.skipped.append(self.skip(cloud, period, Verdict.INVALID, f"komunikat {ticker} nie podaje wzrostu {cloud}"))
                continue
            value, evidence = growth
            capex_growth = (ttm / ttm_before - 1) * 100
            result.readings.append(
                Reading(
                    check_id=self.meta.id,
                    subject=cloud,
                    period=period,
                    value=value,
                    data={"capex_growth": round(capex_growth, 2), "capex_ttm": ttm, "ticker": ticker},
                    evidence=(evidence,),
                )
            )
        return result

    @staticmethod
    def _growth(ctx: Context, cloud: str, url: str, pattern: str) -> tuple[float, Evidence] | None:
        text = ctx.edgar.text(url)
        match = re.search(pattern, text)
        title = f"komunikat wynikowy — {cloud}"
        if match:
            return float(match.group(1)), Evidence(url=url, title=title, quote=match.group(0))
        if ctx.extract is None:
            return None
        # The release reworded the sentence: let the model find it, and keep only words it really quoted.
        document = Document(id="d1", title=title, url=url, text=text[:20_000])
        try:
            claim = ctx.extract(GrowthClaim, f"State the year-over-year revenue growth of {cloud} this quarter.", [document])
        except LlmError:
            return None
        if not isinstance(claim, GrowthClaim) or not claim.found:
            return None
        evidence = verify(claim.quote, [document])
        if evidence is None or not states_number(evidence.quote, claim.growth_percent):
            return None
        return claim.growth_percent, evidence

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        grouped = by_subject(history)
        outcomes: list[Outcome] = []
        slowing: dict[str, set[str]] = {}
        speeding: dict[str, set[str]] = {}
        for cloud, periods in grouped.items():
            latest = max(periods)
            now, before, earlier = periods[latest], periods.get(shift_quarter(latest, -1)), periods.get(shift_quarter(latest, -2))
            growth, capex = now.value or 0.0, number(now, "capex_growth") or 0.0
            line = f"{cloud}: {growth:.0f}% r/r, capex TTM {capex:+.0f}% r/r"
            if before is not None:
                line += f" (kwartał wcześniej {before.value or 0:.0f}%)"
            slows = (
                before is not None
                and earlier is not None
                and growth <= (before.value or 0) - SLOWDOWN_POINTS
                and (before.value or 0) <= (earlier.value or 0) - SLOWDOWN_POINTS
                and capex - growth >= CAPEX_GAP_POINTS
            )
            speeds = before is not None and growth - (before.value or 0) >= ACCELERATION_POINTS
            if slows:
                slowing.setdefault(latest, set()).add(cloud)
                line += " — hamuje drugi kwartał z rzędu (wczesne ostrzeżenie)"
            if speeds:
                speeding.setdefault(latest, set()).add(cloud)
            outcomes.append(self.outcome(now, Verdict.NEUTRAL, line))

        # The verdict is on the basket, for the newest quarter all three clouds reported.
        complete = [period for period in {r.period for r in history} if all(period in grouped.get(cloud, {}) for cloud in CLOUDS)]
        if complete:
            quarter = max(complete)
            evidence = tuple(item for cloud in CLOUDS for item in grouped[cloud][quarter].evidence)
            lines = [outcome.summary for outcome in outcomes if outcome.period == quarter]
            red, green = slowing.get(quarter, set()), speeding.get(quarter, set())
            basket = Reading(check_id=self.meta.id, subject=BASKET, period=quarter, value=None)
            if len(red) >= 2:
                verdict, head = Verdict.RED, f"Monetyzacja przegrywa z inwestycjami: hamują {', '.join(sorted(red))}."
            elif len(green) >= 2:
                verdict, head = Verdict.GREEN, f"Chmury przyspieszają: {', '.join(sorted(green))}."
            else:
                verdict, head = Verdict.NEUTRAL, "Bez sygnału."
            outcomes.append(self.outcome(basket, verdict, " ".join([head, *lines]), evidence=evidence))
        return outcomes


def _ttm_year_before(quarters: dict[date, float], end: date) -> float | None:
    earlier = [day for day in quarters if abs((day - (end - timedelta(days=365))).days) <= 20]
    return trailing_sum(quarters, earlier[0]) if earlier else None


# A2 -------------------------------------------------------------------------------------------

LABS = ("OpenAI", "Anthropic")
STALL_GROWTH = 0.05
STRONG_GROWTH = 0.15


class LabRevenueStall(Check):
    meta = CheckMeta(
        id="A2",
        category=Category.A,
        title="ARR labów stoi w miejscu",
        question="Czy roczny przychód (ARR) OpenAI i Anthropic nadal rośnie z kwartału na kwartał?",
        rule_red=f"ARR kw/kw rośnie mniej niż {STALL_GROWTH:.0%} (albo spada), potwierdzone przez 2 niezależne źródła",
        rule_green=f"ARR kw/kw rośnie o ≥ {STRONG_GROWTH:.0%}",
        unit="USD",
        caveat="Laby nie raportują przychodów; liczby pochodzą z przecieków i wywiadów, często zaokrąglone.",
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for lab in LABS:
            if ctx.extract is None:
                result.skipped.append(self.skip(lab, _month(ctx.today), Verdict.INVALID, "brak skonfigurowanego LLM"))
                continue
            query = f'"{lab}" ("annualized revenue" OR "run-rate" OR "annual recurring revenue" OR ARR)'
            try:
                found = headlines(ctx.fetch(search_url(query)))
                documents = documents_from(found)
                answer = ctx.extract(ArrClaims, f"List every annualised revenue figure of {lab} the headlines state.", documents)
            except (SourceError, LlmError) as exc:
                result.skipped.append(self.skip(lab, _month(ctx.today), Verdict.INVALID, str(exc)))
                continue
            months: dict[str, list[tuple[float, bool, str, Evidence, str]]] = {}
            for claim in answer.claims if isinstance(answer, ArrClaims) else []:
                checked = verified(claim.quote, documents, found)
                if checked is None or claim.lab.lower() != lab.lower() or not states_number(claim.quote.text, claim.amount_usd):
                    continue
                evidence, domain = checked
                months.setdefault(claim.as_of_month[:7], []).append(
                    (claim.amount_usd, claim.is_lower_bound, claim.metric_kind, evidence, domain)
                )
            for period, claims in months.items():
                exact = [claim for claim in claims if not claim[1]] or claims
                result.readings.append(
                    Reading(
                        check_id=self.meta.id,
                        subject=lab,
                        period=period,
                        value=median([claim[0] for claim in exact]),
                        data={
                            "lower_bound": all(claim[1] for claim in exact),
                            "kind": exact[0][2],
                            "domains": list[JsonValue](sorted({claim[4] for claim in claims})),
                        },
                        evidence=tuple(claim[3] for claim in claims),
                    )
                )
        return result

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for lab, periods in by_subject(history).items():
            quarters: dict[str, Reading] = {}
            for period in sorted(periods):  # the latest month of each quarter wins
                quarters[quarter_of_month(period)] = periods[period]
            # A quarter is judged a month after it ends: the news about it comes late.
            closed = [q for q in sorted(quarters) if quarter_end(q) + timedelta(days=30) <= today]
            if len(closed) < 2:
                continue
            current, previous = quarters[closed[-1]], quarters[closed[-2]]
            if not current.value or not previous.value or closed[-2] != shift_quarter(closed[-1], -1):
                continue
            growth = current.value / previous.value - 1
            summary = (
                f"{lab}: ARR {usd(current.value)} ({current.period}) wobec {usd(previous.value)} ({previous.period}), {pct(growth)} kw/kw."
            )
            reading = Reading(check_id=self.meta.id, subject=lab, period=closed[-1], value=current.value, evidence=current.evidence)
            domains = current.data.get("domains")
            sure = confirmed([str(domain) for domain in domains]) if isinstance(domains, list) else False
            if growth < STALL_GROWTH:
                head = "ARR spadł. " if growth <= 0 else "ARR stanął. "
                lower = current.data.get("lower_bound") is True
                verdict = Verdict.RED if sure and not lower else Verdict.UNCONFIRMED
                outcomes.append(self.outcome(reading, verdict, head + summary))
            elif growth >= STRONG_GROWTH:
                outcomes.append(self.outcome(reading, Verdict.GREEN if sure else Verdict.UNCONFIRMED, summary))
            else:
                outcomes.append(self.outcome(reading, Verdict.NEUTRAL, summary))
        return outcomes


def _month(day: date) -> str:
    return f"{day.year}-{day.month:02d}"
