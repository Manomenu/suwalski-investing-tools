import json
from datetime import timedelta

from suwinvtools_server.signals.checks.hardware import (
    ComputeImpairment,
    DepreciationLife,
    GpuRentalPrices,
    NeocloudBacklog,
)
from suwinvtools_server.signals.model import ImpairmentClaim, ImpairmentClaims, ImpairmentReason, Quote, Reading, UsefulLifeClaim, Verdict
from suwinvtools_server.signals.sources.vast import offers_url
from tests.signals.fakes import TODAY, Pages, Sec, Stub, context, reading

# B1 -------------------------------------------------------------------------------------------

LIFE_SENTENCE = "The estimated useful lives of servers and network equipment range from 2 to 6 years."


def msft_ten_k(sec: Sec, html: str) -> None:
    sec.filings("MSFT", 789019, [("10-K", "2026-07-30", "2026-06-30", "0000950170-26-000001", "msft-10k.htm", "")])
    sec.document(789019, "0000950170-26-000001", "msft-10k.htm", html)


def life_claim(quote: str = LIFE_SENTENCE, years_max: float = 6) -> Stub:
    return Stub(
        {
            UsefulLifeClaim: UsefulLifeClaim(
                found=True, years_max=years_max, years_min=2, changed_in_this_filing=False, quote=Quote(source_id="d1", text=quote)
            )
        }
    )


def test_life_is_read_from_the_filing_and_verified() -> None:
    sec = Sec()
    msft_ten_k(sec, f"<p>Property. {LIFE_SENTENCE} Other text.</p><p>Goodwill</p>")
    result = DepreciationLife().read(context(sec=sec, extract=life_claim()))
    msft = next(r for r in result.readings if r.subject == "MSFT")
    assert (msft.period, msft.value, msft.data["years_min"], msft.data["changed"]) == ("2026Q2", 6, 2, False)
    assert msft.evidence[0].quote == LIFE_SENTENCE
    # The five other buyers have no filings in this fake: INVALID, never a guess.
    assert {o.subject for o in result.skipped} == {"AMZN", "GOOGL", "META", "ORCL", "CRWV"}
    assert {o.verdict for o in result.skipped} == {Verdict.INVALID}


def test_life_is_invalid_when_the_quote_is_invented_or_the_number_is_not_in_it() -> None:
    sec = Sec()
    msft_ten_k(sec, f"<p>{LIFE_SENTENCE}</p>")
    invented = DepreciationLife().read(context(sec=sec, extract=life_claim("Servers last exactly twelve years in our books.")))
    assert not invented.readings
    wrong_number = DepreciationLife().read(context(sec=sec, extract=life_claim(years_max=8)))
    assert not wrong_number.readings
    no_model = DepreciationLife().read(context(sec=sec, extract=None))
    assert not no_model.readings
    assert any(o.subject == "MSFT" and "LLM" in o.summary for o in no_model.skipped)


def test_life_is_not_ready_without_a_newer_report_and_invalid_without_servers_text() -> None:
    sec = Sec()
    msft_ten_k(sec, "<p>The useful life of buildings is 40 years.</p>")
    assert (
        next(o for o in DepreciationLife().read(context(sec=sec, extract=life_claim())).skipped if o.subject == "MSFT").verdict
        is Verdict.INVALID
    )
    sec = Sec()
    msft_ten_k(sec, f"<p>{LIFE_SENTENCE}</p>")
    again = DepreciationLife().read(context(sec=sec, extract=life_claim(), latest={("B1", "MSFT"): "2026Q2"}))
    assert next(o for o in again.skipped if o.subject == "MSFT").verdict is Verdict.NOT_READY


def test_life_falls_back_to_an_older_report_when_the_newest_does_not_describe_it() -> None:
    sec = Sec()
    rows = [
        ("10-Q", "2026-08-01", "2026-06-30", "0000000001-26-000002", "q.htm", ""),
        ("10-K", "2026-02-01", "2025-12-31", "0000000001-26-000001", "k.htm", ""),
    ]
    sec.filings("MSFT", 789019, rows)
    sec.document(789019, "0000000001-26-000002", "q.htm", "<p>Interim report without the policy notes.</p>")
    sec.document(789019, "0000000001-26-000001", "k.htm", f"<p>{LIFE_SENTENCE}</p>")
    msft = next(r for r in DepreciationLife().read(context(sec=sec, extract=life_claim())).readings if r.subject == "MSFT")
    assert msft.period == "2025Q4"
    stored = DepreciationLife().read(context(sec=sec, extract=life_claim(), latest={("B1", "MSFT"): "2025Q4"}))
    assert next(o for o in stored.skipped if o.subject == "MSFT").verdict is Verdict.NOT_READY


def test_life_evaluation_baseline_shorter_longer_and_the_first_giant() -> None:
    check = DepreciationLife()
    assert check.evaluate([reading("B1", "MSFT", "2026Q1", 6)], TODAY)[0].verdict is Verdict.BASELINE
    shortened = [reading("B1", "MSFT", "2026Q1", 6), reading("B1", "MSFT", "2026Q2", 5)]
    first = check.evaluate(shortened, TODAY)[0]
    assert first.verdict is Verdict.RED
    assert "Pierwszy gigant" in first.summary
    # Amazon cut earlier, so Microsoft is no longer the first.
    amazon = [reading("B1", "AMZN", "2025Q3", 6), reading("B1", "AMZN", "2025Q4", 5)]
    second = next(o for o in check.evaluate([*amazon, *shortened], TODAY) if o.subject == "MSFT")
    assert second.verdict is Verdict.RED
    assert "Pierwszy" not in second.summary
    longer = check.evaluate([reading("B1", "ORCL", "2026Q1", 5), reading("B1", "ORCL", "2026Q2", 6)], TODAY)[0]
    assert longer.verdict is Verdict.GREEN
    assert "zysk na akcję" in longer.summary
    assert check.evaluate([reading("B1", "META", "2026Q1", 5.5), reading("B1", "META", "2026Q2", 5.5)], TODAY)[0].verdict is Verdict.NEUTRAL


# B2 -------------------------------------------------------------------------------------------

IMPAIRMENT_SENTENCE = "We recorded an impairment of $120 million on GPU servers because newer accelerators made them obsolete."


def impairment_world(html: str) -> Sec:
    sec = Sec()
    sec.company("MSFT", 789019)
    sec.pages.default = b'{"hits": {"hits": []}}'
    window = (TODAY - timedelta(days=35), TODAY)
    sec.search(
        '"impairment" "GPU"',
        "10-Q,10-K,8-K",
        window,
        [("0000950170-26-000002", 789019, "Microsoft Corp (MSFT)", "q.htm", "2026-10-10")],
        "0000789019",
    )
    sec.document(789019, "0000950170-26-000002", "q.htm", html)
    return sec


def impairment_claim(*, reason: ImpairmentReason = "obsolescence", hardware: bool = True, quote: str = IMPAIRMENT_SENTENCE) -> Stub:
    claim = ImpairmentClaim(is_compute_hardware=hardware, reason=reason, amount_usd=120e6, quote=Quote(source_id="d1", text=quote))
    return Stub({ImpairmentClaims: ImpairmentClaims(claims=[claim])})


def test_impairment_of_obsolete_hardware_is_a_reading_and_a_red() -> None:
    check = ComputeImpairment()
    result = check.read(context(sec=impairment_world(f"<p>{IMPAIRMENT_SENTENCE}</p>"), extract=impairment_claim()))
    assert [(r.subject, r.period, r.value) for r in result.readings] == [("MSFT", "2026Q3", 120e6)]
    outcome = check.evaluate(result.readings, TODAY)[0]
    assert outcome.verdict is Verdict.RED
    assert "120.0 mln USD" in outcome.summary


def test_impairment_ignores_other_reasons_other_assets_and_invented_quotes() -> None:
    sec = impairment_world(f"<p>{IMPAIRMENT_SENTENCE}</p>")
    for stub in (
        impairment_claim(reason="restructuring"),
        impairment_claim(hardware=False),
        impairment_claim(quote="We wrote off a whole data center in July."),
    ):
        assert not ComputeImpairment().read(context(sec=sec, extract=stub)).readings


def test_impairment_not_ready_without_hits_and_invalid_without_a_model() -> None:
    quiet = Sec()
    quiet.company("MSFT", 789019)
    quiet.pages.default = b'{"hits": {"hits": []}}'
    assert ComputeImpairment().read(context(sec=quiet, extract=None)).skipped[0].verdict is Verdict.NOT_READY
    no_model = ComputeImpairment().read(context(sec=impairment_world(f"<p>{IMPAIRMENT_SENTENCE}</p>"), extract=None))
    assert no_model.skipped[0].verdict is Verdict.INVALID


# B3 -------------------------------------------------------------------------------------------


def neocloud_world() -> Sec:
    sec = Sec()
    sec.company("CRWV", 1769628)
    sec.facts(1769628, {"RevenueRemainingPerformanceObligation": {"2025-09-30": 20e9, "2025-12-31": 25e9}}, flow=False)
    sec.facts(1769628, {"Revenues": {"2025-09-30": 1.4e9, "2025-12-31": 1.6e9}})
    sec.company("NBIS", 1513845)
    sec.facts(1513845, {"Revenues": {"2025-12-31": 0.3e9}})
    return sec


def test_backlog_is_read_for_every_quarter_and_coverage_is_in_months_of_revenue() -> None:
    result = NeocloudBacklog().read(context(sec=neocloud_world()))
    crwv = {r.period: r for r in result.readings}
    assert set(crwv) == {"2025Q3", "2025Q4"}
    assert crwv["2025Q3"].value == 20e9
    assert crwv["2025Q3"].data["coverage_months"] == round(20e9 / 1.4e9 * 3, 2)
    nbis = next(o for o in result.skipped if o.subject == "NBIS")
    assert (nbis.verdict, "nie raportuje RPO" in nbis.summary) == (Verdict.INVALID, True)


def test_backlog_reads_only_quarters_newer_than_the_stored_one() -> None:
    result = NeocloudBacklog().read(context(sec=neocloud_world(), latest={("B3", "CRWV"): "2025Q3"}))
    assert [r.period for r in result.readings] == ["2025Q4"]
    again = NeocloudBacklog().read(context(sec=neocloud_world(), latest={("B3", "CRWV"): "2025Q4"}))
    assert next(o for o in again.skipped if o.subject == "CRWV").verdict is Verdict.NOT_READY


def backlog(*rows: tuple[str, float, float]) -> list[Reading]:
    return [reading("B3", "CRWV", period, rpo, coverage_months=coverage) for period, rpo, coverage in rows]


def test_backlog_evaluation() -> None:
    check = NeocloudBacklog()
    assert check.evaluate(backlog(("2026Q1", 20e9, 40)), TODAY)[0].verdict is Verdict.BASELINE
    assert check.evaluate(backlog(("2026Q1", 20e9, 40), ("2026Q2", 18e9, 38)), TODAY)[0].verdict is Verdict.RED  # RPO -10 %
    assert check.evaluate(backlog(("2026Q1", 20e9, 40), ("2026Q2", 23e9, 42)), TODAY)[0].verdict is Verdict.GREEN
    assert check.evaluate(backlog(("2026Q1", 20e9, 40), ("2026Q2", 21e9, 41)), TODAY)[0].verdict is Verdict.NEUTRAL
    # RPO still grows, but coverage fell two quarters running by more than 10 % in total.
    slipping = backlog(("2026Q1", 20e9, 45), ("2026Q2", 20.5e9, 41), ("2026Q3", 21e9, 38))
    assert check.evaluate(slipping, TODAY)[0].verdict is Verdict.RED
    # Falling coverage blocks the green even when RPO jumps.
    assert check.evaluate(backlog(("2026Q1", 20e9, 45), ("2026Q2", 23e9, 40)), TODAY)[0].verdict is Verdict.NEUTRAL


# B4 -------------------------------------------------------------------------------------------


def offers(count: int, price: float) -> bytes:
    return json.dumps({"offers": [{"dph_total": price * 2, "num_gpus": 2} for _ in range(count)]}).encode()


def test_gpu_prices_are_pooled_per_family_and_thin_markets_are_invalid() -> None:
    fetch = Pages({offers_url("B200"): offers(3, 5.0)}, default=offers(10, 2.0))
    result = GpuRentalPrices().read(context(fetch=fetch))
    by_family = {r.subject: r for r in result.readings}
    assert set(by_family) == {"H100", "H200"}
    assert (by_family["H100"].period, by_family["H100"].value, by_family["H100"].data["offers"]) == ("2026-10", 2.0, 30)
    b200 = result.skipped[0]
    assert (b200.subject, b200.verdict) == ("B200", Verdict.INVALID)


def test_gpu_prices_not_ready_when_the_month_was_read_and_invalid_on_a_changed_shape() -> None:
    done = GpuRentalPrices().read(
        context(
            fetch=Pages(default=offers(10, 2.0)), latest={("B4", "H100"): "2026-10", ("B4", "H200"): "2026-10", ("B4", "B200"): "2026-10"}
        )
    )
    assert {o.verdict for o in done.skipped} == {Verdict.NOT_READY}
    changed = GpuRentalPrices().read(context(fetch=Pages(default=b'{"rows": []}')))
    assert {o.verdict for o in changed.skipped} == {Verdict.INVALID}


def prices(month_values: dict[str, tuple[float, float, float]]) -> list[Reading]:
    rows: list[Reading] = []
    for period, (h100, h200, b200) in month_values.items():
        rows += [reading("B4", "H100", period, h100), reading("B4", "H200", period, h200), reading("B4", "B200", period, b200)]
    return rows


def test_gpu_evaluation() -> None:
    check = GpuRentalPrices()
    assert check.evaluate([], TODAY) == []
    only_now = check.evaluate(prices({"2026-10": (2.0, 3.0, 5.0)}), TODAY)
    assert (only_now[0].subject, only_now[0].verdict) == ("GPU", Verdict.BASELINE)
    h200_falls = prices({"2026-07": (2.0, 3.0, 5.0), "2026-10": (2.0, 2.3, 5.0)})  # H200 -23 %
    assert check.evaluate(h200_falls, TODAY)[0].verdict is Verdict.RED
    flat = prices({"2026-07": (2.0, 3.0, 5.0), "2026-10": (2.0, 3.0, 5.0)})
    assert check.evaluate(flat, TODAY)[0].verdict is Verdict.GREEN
    mild = prices({"2026-07": (2.0, 3.0, 5.0), "2026-10": (1.8, 3.0, 5.0)})  # H100 -10 %: no red, no green
    assert check.evaluate(mild, TODAY)[0].verdict is Verdict.NEUTRAL
    ratio = prices({"2026-04": (2.0, 3.0, 4.0), "2026-07": (2.0, 3.0, 4.0), "2026-10": (2.0, 3.0, 5.0)})  # H100/B200 0.5 -> 0.4
    outcome = check.evaluate(ratio, TODAY)[0]
    assert outcome.verdict is Verdict.RED
    assert "wiek chipa" in outcome.summary
