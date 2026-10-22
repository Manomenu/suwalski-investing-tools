"""Category E — valuation against the return on capital: is the market paying more for a
backlog that covers less of the capex?

The idea comes from Convequity's AI Bubble Barometer, without its fixed haircuts: only what
the filings and the share price say, compared with the same figures a quarter and two quarters ago."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import override

from suwinvtools_library.marketdata.edgar import (
    CAPEX_TAGS,
    CASH_TAGS,
    DEBT_TAGS,
    DILUTED_SHARES_TAGS,
    EQUITY_TAGS,
    FACTS_URL,
    RPO_TAGS,
    SHARES_TAGS,
    calendar_quarter,
    instants,
    quarter_averages,
    quarterly_flows,
    trailing_sum,
)
from suwinvtools_server.signals.checks.base import (
    READ_ERRORS,
    Check,
    CheckMeta,
    Context,
    ReadResult,
    by_subject,
    number,
    shift_quarter,
)
from suwinvtools_server.signals.model import Category, Evidence, Outcome, Reading, Verdict

BASKET = ("MSFT", "AMZN", "GOOGL", "ORCL", "CRWV")
BASKET_SUBJECT = "koszyk"
BACKFILL_QUARTERS = 4
CAPEX_QUARTERS = 8
# A balance-sheet figure counts for a quarter end when it is dated within this many days of it.
BALANCE_TOLERANCE_DAYS = 10
# The share count on a cover page comes with the filing, up to this many days after the quarter ends.
SHARES_AFTER_DAYS = 60
SHARES_BEFORE_DAYS = 30
# An RPO series whose newest figure is older than this is not "fresh": the company stopped tagging it.
RPO_FRESH_DAYS = 200


def _near(series: Mapping[date, float], day: date, *, before: int, after: int = 0) -> float | None:
    """The figure dated closest to `day`, from `before` days earlier to `after` days later."""
    candidates = [d for d in series if -before <= (d - day).days <= after]
    return series[min(candidates, key=lambda d: abs((d - day).days))] if candidates else None


class CapitalVsValuation(Check):
    meta = CheckMeta(
        id="E1",
        category=Category.E,
        title="Wycena rośnie, a pokrycie capeksu kontraktami słabnie",
        question="Czy rynek płaci coraz więcej za kapitał zainwestowany w AI, choć kontrakty pokrywają coraz mniejszą część capeksu?",
        rule_red="EV/kapitał zainwestowany rośnie dwa kwartały z rzędu, a RPO/capeks z 24 miesięcy w tym czasie spada",
        rule_green="EV/kapitał zainwestowany spada, a RPO/capeks z 24 miesięcy rośnie",
        unit="RPO / capeks z 8 kwartałów",
        caveat=(
            "Koszyk MSFT, AMZN, GOOGL, ORCL, CRWV; spółki bez świeżego RPO lub liczby akcji w XBRL (np. Amazon, Alphabet) są pomijane. "
            "Kapitał zainwestowany to kapitał własny + dług - gotówka, więc to wskaźnik zgrubny."
        ),
    )

    @override
    def read(self, ctx: Context) -> ReadResult:
        result = ReadResult()
        for ticker in BASKET:
            try:
                readings = self._company(ctx, ticker)
            except READ_ERRORS as exc:
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, str(exc)))
                continue
            if isinstance(readings, str):
                result.skipped.append(self.skip(ticker, "—", Verdict.INVALID, readings))
                continue
            latest = ctx.latest_period(self.meta.id, ticker)
            fresh = [reading for reading in readings if latest is None or reading.period > latest]
            if fresh:
                result.readings.extend(fresh)
            else:
                result.skipped.append(self.skip(ticker, readings[-1].period, Verdict.NOT_READY, "brak nowego kwartału"))
        return result

    def _company(self, ctx: Context, ticker: str) -> list[Reading] | str:
        """Readings of the last quarters, or the reason there are none."""
        cik = ctx.edgar.cik(ticker)
        if cik is None:
            return f"{ticker}: brak w EDGAR"
        facts = ctx.edgar.facts(cik)
        backlog = instants(facts, RPO_TAGS)
        if not backlog or (ctx.today - max(backlog)).days > RPO_FRESH_DAYS:
            return f"{ticker}: brak świeżego RPO w XBRL"
        capex, equity, debt, cash = (
            quarterly_flows(facts, CAPEX_TAGS),
            *(instants(facts, tags) for tags in (EQUITY_TAGS, DEBT_TAGS, CASH_TAGS)),
        )
        shares = instants(facts, SHARES_TAGS, namespace="dei")
        diluted = quarter_averages(facts, DILUTED_SHARES_TAGS)
        readings: list[Reading] = []
        missing: set[str] = set()
        for end in sorted(day for day in backlog if day in capex)[-BACKFILL_QUARTERS:]:
            capex_24m = trailing_sum(capex, end, CAPEX_QUARTERS)
            balance = [_near(series, end, before=BALANCE_TOLERANCE_DAYS, after=BALANCE_TOLERANCE_DAYS) for series in (equity, debt, cash)]
            count = _near(shares, end, before=SHARES_BEFORE_DAYS, after=SHARES_AFTER_DAYS) or diluted.get(end)
            lacks = {
                name
                for name, absent in (
                    ("capeks z 8 kwartałów", capex_24m is None or capex_24m <= 0),
                    ("liczba akcji", count is None),
                    ("kapitał własny", balance[0] is None),
                    ("dług", balance[1] is None),
                    ("gotówka", balance[2] is None),
                )
                if absent
            }
            if lacks or capex_24m is None or count is None:
                missing |= lacks
                continue
            book, borrowed, cash_held = (value or 0.0 for value in balance)
            close = ctx.price(ticker, end)
            if close is None:
                return f"{ticker}: brak kursu zamknięcia z {end}"
            readings.append(
                Reading(
                    check_id=self.meta.id,
                    subject=ticker,
                    period=calendar_quarter(end),
                    value=backlog[end] / capex_24m,
                    data={
                        "ev": close * count + borrowed - cash_held,
                        "ic": book + borrowed - cash_held,
                        "rpo": backlog[end],
                        "capex_24m": capex_24m,
                    },
                    evidence=(Evidence(url=FACTS_URL.format(cik=cik), title=f"SEC — dane XBRL {ticker}"),),
                )
            )
        return readings or f"{ticker}: brak w XBRL: {', '.join(sorted(missing)) or 'RPO z capeksem w tych samych kwartałach'}"

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        grouped = by_subject(history)
        if not grouped:
            return []
        newest = max(period for periods in grouped.values() for period in periods)
        quarters = [shift_quarter(newest, -2), shift_quarter(newest, -1), newest]
        members = sorted(name for name, periods in grouped.items() if all(q in periods for q in quarters))
        left_out = [name for name in BASKET if name not in members]
        note = f" Pominięte (brak danych): {', '.join(left_out)}." if left_out else ""
        anchor = Reading(check_id=self.meta.id, subject=BASKET_SUBJECT, period=newest, value=None)
        if not members:
            return [self.outcome(anchor, Verdict.BASELINE, f"Koszyk: za mało danych z trzech kolejnych kwartałów.{note}")]
        evidence = tuple(item for name in members for item in grouped[name][newest].evidence)

        def total(quarter: str, key: str) -> float:
            return sum(number(grouped[name][quarter], key) or 0.0 for name in members)

        valuation = [total(q, "ev") / total(q, "ic") if total(q, "ic") > 0 else 0.0 for q in quarters]
        coverage = [total(q, "rpo") / total(q, "capex_24m") if total(q, "capex_24m") > 0 else 0.0 for q in quarters]
        line = (
            f"Koszyk ({', '.join(members)}): EV/kapitał zainwestowany {valuation[0]:.2f} → {valuation[1]:.2f} → {valuation[2]:.2f}, "
            f"RPO/capeks 24 mies. {coverage[0]:.2f} → {coverage[1]:.2f} → {coverage[2]:.2f} ({quarters[0]} → {newest}).{note}"
        )
        if valuation[0] < valuation[1] < valuation[2] and coverage[2] < coverage[0]:
            return [
                self.outcome(anchor, Verdict.RED, f"Rynek płaci więcej, a kontrakty pokrywają mniej capeksu. {line}", evidence=evidence)
            ]
        if valuation[2] < valuation[0] and coverage[2] > coverage[0]:
            return [self.outcome(anchor, Verdict.GREEN, f"Wycena spada, a kontrakty pokrywają więcej capeksu. {line}", evidence=evidence)]
        return [self.outcome(anchor, Verdict.NEUTRAL, line, evidence=evidence)]
