from datetime import date

from suwinvtools_server.signals.checks.capital import CapitalVsValuation
from suwinvtools_server.signals.model import Reading, Verdict
from tests.signals.fakes import TODAY, Sec, context

ENDS = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
CAPEX_ENDS = ["2023-12-31", "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", *ENDS]


def company(sec: Sec, ticker: str, cik: int, *, rpo: bool = True) -> dict[tuple[str, date], float]:
    """A company with 11 quarters of capex (10 bn each), four of backlog and balance sheet; returns its prices."""
    sec.company(ticker, cik)
    sec.facts(cik, {"PaymentsToAcquirePropertyPlantAndEquipment": dict.fromkeys(CAPEX_ENDS, 10e9)})
    balance = {
        "StockholdersEquity": dict.fromkeys(ENDS, 200e9),
        "LongTermDebt": dict.fromkeys(ENDS, 40e9),
        "CashAndCashEquivalentsAtCarryingValue": dict.fromkeys(ENDS, 20e9),
    }
    if rpo:
        balance["RevenueRemainingPerformanceObligation"] = dict(zip(ENDS, (320e9, 360e9, 400e9, 440e9), strict=True))
    sec.facts(cik, balance, flow=False)
    sec.shares(cik, {f"{end[:8]}{int(end[8:]) - 5:02d}": 1e9 for end in ENDS})  # the cover page, a few days after the quarter ends
    return {(ticker, date.fromisoformat(end)): 100.0 for end in ENDS}


def test_company_readings_backfill_the_last_quarters() -> None:
    sec = Sec()
    prices = company(sec, "MSFT", 789019)
    company(sec, "AMZN", 1018724, rpo=False)
    result = CapitalVsValuation().read(context(sec=sec, prices=prices))
    msft = {r.period: r for r in result.readings}
    assert list(msft) == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    last = msft["2026Q2"]
    assert last.value == 440e9 / 80e9  # backlog / capex of the last 8 quarters
    assert last.data["ev"] == 100.0 * 1e9 + 40e9 - 20e9
    assert last.data["ic"] == 200e9 + 40e9 - 20e9
    amzn = next(o for o in result.skipped if o.subject == "AMZN")
    assert (amzn.verdict, "RPO" in amzn.summary) == (Verdict.INVALID, True)


def test_company_without_a_share_count_is_named_as_invalid() -> None:
    sec = Sec()
    sec.company("GOOGL", 1652044)
    sec.facts(1652044, {"PaymentsToAcquirePropertyPlantAndEquipment": dict.fromkeys(CAPEX_ENDS, 10e9)})
    sec.facts(
        1652044,
        {"RevenueRemainingPerformanceObligation": dict.fromkeys(ENDS, 1e11), "StockholdersEquity": dict.fromkeys(ENDS, 1e11)},
        flow=False,
    )
    [skipped] = [o for o in CapitalVsValuation().read(context(sec=sec)).skipped if o.subject == "GOOGL"]
    assert skipped.verdict is Verdict.INVALID
    assert "liczba akcji" in skipped.summary


def test_company_without_a_price_is_invalid_and_stored_quarters_are_skipped() -> None:
    sec = Sec()
    prices = company(sec, "MSFT", 789019)
    assert not CapitalVsValuation().read(context(sec=sec, prices={})).readings
    newer = CapitalVsValuation().read(context(sec=sec, prices=prices, latest={("E1", "MSFT"): "2026Q1"}))
    assert [r.period for r in newer.readings] == ["2026Q2"]
    done = CapitalVsValuation().read(context(sec=sec, prices=prices, latest={("E1", "MSFT"): "2026Q2"}))
    assert next(o for o in done.skipped if o.subject == "MSFT").verdict is Verdict.NOT_READY


def basket(*quarters: tuple[str, float, float], names: tuple[str, ...] = ("MSFT", "GOOGL")) -> list[Reading]:
    """(quarter, EV/IC, backlog/capex) for every company: IC 100 bn, capex 24 months 100 bn."""
    return [
        Reading(
            check_id="E1",
            subject=name,
            period=quarter,
            value=coverage,
            data={"ev": ratio * 100e9, "ic": 100e9, "rpo": coverage * 100e9, "capex_24m": 100e9},
        )
        for quarter, ratio, coverage in quarters
        for name in names
    ]


def test_basket_evaluation() -> None:
    check = CapitalVsValuation()

    def verdict(rows: list[Reading]) -> Verdict:
        return check.evaluate(rows, TODAY)[0].verdict

    assert verdict(basket(("2026Q1", 1.0, 5), ("2026Q2", 1.2, 4), ("2026Q3", 1.4, 3))) is Verdict.RED
    assert verdict(basket(("2026Q1", 1.4, 3), ("2026Q2", 1.2, 4), ("2026Q3", 1.0, 5))) is Verdict.GREEN
    assert verdict(basket(("2026Q1", 1.0, 3), ("2026Q2", 1.2, 4), ("2026Q3", 1.4, 5))) is Verdict.NEUTRAL  # pricier, but better covered
    assert verdict(basket(("2026Q1", 1.0, 5), ("2026Q2", 0.9, 4), ("2026Q3", 1.4, 3))) is Verdict.NEUTRAL  # valuation did not rise twice
    assert check.evaluate([], TODAY) == []


def test_basket_names_the_companies_it_left_out() -> None:
    rows = basket(("2026Q1", 1.0, 5), ("2026Q2", 1.2, 4), ("2026Q3", 1.4, 3))
    rows += basket(("2026Q3", 1.0, 3), names=("ORCL",))  # Oracle has only the newest quarter
    [outcome] = CapitalVsValuation().evaluate(rows, TODAY)
    assert outcome.verdict is Verdict.RED
    assert "Pominięte" in outcome.summary
    assert "ORCL" in outcome.summary
    assert "MSFT, GOOGL" in outcome.summary or "GOOGL, MSFT" in outcome.summary
    few = CapitalVsValuation().evaluate(basket(("2026Q3", 1.0, 3)), TODAY)[0]
    assert few.verdict is Verdict.BASELINE
