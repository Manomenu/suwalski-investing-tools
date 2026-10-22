from suwinvtools_server.signals.checks.monetization import CloudVsCapex, LabRevenueStall
from suwinvtools_server.signals.model import ArrClaim, ArrClaims, GrowthClaim, Quote, Reading, Verdict
from tests.signals.fakes import TODAY, Pages, Sec, Stub, context, reading, rss

# A1 -------------------------------------------------------------------------------------------

CAPEX_ENDS = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
CLOUD_SENTENCE = "Google Cloud segment revenues increased 32% year over year, driven by AI infrastructure."


def google(sec: Sec, release: str) -> None:
    sec.filings("GOOGL", 1652044, [("8-K", "2026-07-23", "2026-07-23", "0001652044-26-000001", "g8k.htm", "2.02,9.01")])
    sec.exhibit(1652044, "0001652044-26-000001", "g8k.htm", "ex99-1.htm", f"<p>{release}</p>")
    capex = [10e9, 10e9, 10e9, 10e9, 12e9, 14e9, 16e9, 18e9]  # TTM 40 bn a year before, 60 bn now: +50 %
    sec.facts(1652044, {"PaymentsToAcquirePropertyPlantAndEquipment": dict(zip(CAPEX_ENDS, capex, strict=True))})


def test_cloud_growth_is_read_by_pattern_with_capex_from_companyfacts() -> None:
    sec = Sec()
    google(sec, CLOUD_SENTENCE)
    result = CloudVsCapex().read(context(sec=sec))
    [row] = result.readings
    assert (row.subject, row.period, row.value) == ("Google Cloud", "2026Q2", 32.0)
    assert row.data["capex_growth"] == 50.0
    assert row.evidence[0].quote == "Google Cloud segment revenues increased 32%"
    # AWS and Azure have no filings in this fake.
    assert {o.subject for o in result.skipped} == {"AWS", "Azure"}


def test_a_reworded_release_goes_to_the_model_and_its_quote_is_verified() -> None:
    sec = Sec()
    reworded = "Cloud revenue climbed 32 percent from a year ago, and backlog doubled."
    google(sec, reworded)
    claim = GrowthClaim(found=True, growth_percent=32, quote=Quote(source_id="d1", text="Cloud revenue climbed 32 percent from a year ago"))
    assert CloudVsCapex().read(context(sec=sec, extract=Stub({GrowthClaim: claim}))).readings[0].value == 32
    invented = GrowthClaim(
        found=True, growth_percent=32, quote=Quote(source_id="d1", text="Cloud revenue exploded by 32 percent this quarter")
    )
    assert not CloudVsCapex().read(context(sec=sec, extract=Stub({GrowthClaim: invented}))).readings
    wrong_number = GrowthClaim(
        found=True, growth_percent=45, quote=Quote(source_id="d1", text="Cloud revenue climbed 32 percent from a year ago")
    )
    assert not CloudVsCapex().read(context(sec=sec, extract=Stub({GrowthClaim: wrong_number}))).readings
    assert not CloudVsCapex().read(context(sec=sec, extract=None)).readings


def test_cloud_not_ready_without_a_newer_release_or_without_capex_for_the_quarter() -> None:
    sec = Sec()
    google(sec, CLOUD_SENTENCE)
    done = CloudVsCapex().read(context(sec=sec, latest={("A1", "Google Cloud"): "2026Q2"}))
    assert next(o for o in done.skipped if o.subject == "Google Cloud").verdict is Verdict.NOT_READY
    early = Sec()
    google(early, CLOUD_SENTENCE)
    early.filings("GOOGL", 1652044, [("8-K", "2026-10-22", "2026-10-22", "0001652044-26-000002", "g8k.htm", "2.02")])
    early.exhibit(1652044, "0001652044-26-000002", "g8k.htm", "ex99-1.htm", f"<p>{CLOUD_SENTENCE}</p>")
    assert next(o for o in CloudVsCapex().read(context(sec=early)).skipped if o.subject == "Google Cloud").verdict is Verdict.NOT_READY


def cloud(name: str, growths: tuple[float, float, float], capex: float) -> list[Reading]:
    return [reading("A1", name, period, g, capex_growth=capex) for period, g in zip(("2026Q2", "2026Q3", "2026Q4"), growths, strict=True)]


def basket_verdict(*clouds: list[Reading]) -> Verdict:
    rows = [row for cloud_rows in clouds for row in cloud_rows]
    return CloudVsCapex().evaluate(rows, TODAY)[-1].verdict


def test_cloud_basket_evaluation() -> None:
    slow = [cloud("AWS", (20, 18, 16), 60), cloud("Azure", (39, 37, 35), 70), cloud("Google Cloud", (32, 33, 34), 60)]
    assert basket_verdict(*slow) is Verdict.RED  # two of three slow down for the second quarter with capex far ahead
    fast = [cloud("AWS", (16, 18, 20), 60), cloud("Azure", (35, 37, 39), 70), cloud("Google Cloud", (32, 32, 32), 60)]
    assert basket_verdict(*fast) is Verdict.GREEN
    mixed = [cloud("AWS", (20, 18, 16), 60), cloud("Azure", (35, 36, 36), 70), cloud("Google Cloud", (32, 32, 32), 60)]
    assert basket_verdict(*mixed) is Verdict.NEUTRAL
    unfunded = [cloud("AWS", (20, 18, 16), 25), cloud("Azure", (39, 37, 35), 30), cloud("Google Cloud", (32, 32, 32), 60)]
    assert basket_verdict(*unfunded) is Verdict.NEUTRAL  # capex is not 20 points ahead of the cloud
    # Until all three clouds reported a quarter there is no basket verdict, only the lines.
    assert {o.subject for o in CloudVsCapex().evaluate(slow[0], TODAY)} == {"AWS"}


# A2 -------------------------------------------------------------------------------------------

HEADLINES = (
    ("OpenAI hits $12 billion annualized revenue, sources say", "Reuters", "https://www.reuters.com"),
    ("OpenAI annualized revenue reaches $12 billion, The Information reports", "The Information", "https://www.theinformation.com"),
)


def arr(source: str, text: str, amount: float = 12e9, month: str = "2026-09") -> ArrClaim:
    return ArrClaim(
        lab="OpenAI",
        amount_usd=amount,
        is_lower_bound=False,
        as_of_month=month,
        metric_kind="annualized_revenue",
        quote=Quote(source_id=source, text=text),
    )


def test_arr_from_two_outlets_is_one_monthly_reading() -> None:
    claims = ArrClaims(
        claims=[arr("n1", "OpenAI hits $12 billion annualized revenue"), arr("n2", "OpenAI annualized revenue reaches $12 billion")]
    )
    result = LabRevenueStall().read(context(fetch=Pages(default=rss(*HEADLINES)), extract=Stub({ArrClaims: claims})))
    openai = [r for r in result.readings if r.subject == "OpenAI"]
    assert [(r.period, r.value) for r in openai] == [("2026-09", 12e9)]
    assert openai[0].data["domains"] == ["reuters.com", "theinformation.com"]


def test_arr_claims_with_a_wrong_number_or_an_invented_quote_are_dropped() -> None:
    fetch = Pages(default=rss(*HEADLINES))
    wrong = ArrClaims(claims=[arr("n1", "OpenAI hits $12 billion annualized revenue", amount=20e9)])
    assert not LabRevenueStall().read(context(fetch=fetch, extract=Stub({ArrClaims: wrong}))).readings
    invented = ArrClaims(claims=[arr("n1", "OpenAI hits $12 billion in profit this week")])
    assert not LabRevenueStall().read(context(fetch=fetch, extract=Stub({ArrClaims: invented}))).readings
    assert {o.verdict for o in LabRevenueStall().read(context(fetch=fetch, extract=None)).skipped} == {Verdict.INVALID}


def arr_history(march: float, june: float, *domains: str, lower_bound: bool = False) -> list[Reading]:
    return [
        reading("A2", "OpenAI", "2026-03", march, domains=["a.com", "b.com"], lower_bound=False),
        reading("A2", "OpenAI", "2026-06", june, domains=list(domains), lower_bound=lower_bound),
    ]


def test_arr_evaluation() -> None:
    check = LabRevenueStall()

    def verdict(rows: list[Reading]) -> Verdict:
        return check.evaluate(rows, TODAY)[0].verdict

    assert verdict(arr_history(10e9, 10.2e9, "a.com", "b.com")) is Verdict.RED  # +2 %
    assert verdict(arr_history(10e9, 10.2e9, "a.com")) is Verdict.UNCONFIRMED  # one outlet
    assert verdict(arr_history(10e9, 10.2e9, "a.com", "b.com", lower_bound=True)) is Verdict.UNCONFIRMED  # "more than"
    assert verdict(arr_history(10e9, 12e9, "a.com", "b.com")) is Verdict.GREEN
    assert verdict(arr_history(10e9, 10.8e9, "a.com", "b.com")) is Verdict.NEUTRAL
    assert check.evaluate(arr_history(10e9, 12e9, "a.com")[:1], TODAY) == []
