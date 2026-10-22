from suwinvtools_server.signals.checks.jevons import HyperscalerTokens, TokenSpend
from suwinvtools_server.signals.model import Quote, Reading, TokenVolumeClaim, Verdict
from suwinvtools_server.signals.sources.openrouter import MODELS_URL, RANKINGS_URL
from tests.signals.fakes import TODAY, Pages, Sec, Stub, context, fixture, reading

# C1 -------------------------------------------------------------------------------------------


def test_token_spend_reads_the_rankings_with_list_prices() -> None:
    fetch = Pages({RANKINGS_URL: fixture("openrouter_rankings.html"), MODELS_URL: fixture("openrouter_models.json")})
    result = TokenSpend().read(context(fetch=fetch))
    [row] = result.readings
    assert (row.subject, row.period) == ("OpenRouter", "2026-10")
    assert row.data["day"] == "2026-10-21"
    assert row.value is not None
    assert row.value > 0
    assert row.data["models"] == 4
    assert 0 < float(str(row.data["priced_share"])) <= 1


def test_token_spend_not_ready_within_the_month_and_invalid_on_a_changed_page() -> None:
    fetch = Pages({RANKINGS_URL: fixture("openrouter_rankings.html"), MODELS_URL: fixture("openrouter_models.json")})
    done = TokenSpend().read(context(fetch=fetch, latest={("C1", "OpenRouter"): "2026-10"}))
    assert done.skipped[0].verdict is Verdict.NOT_READY
    assert not fetch.requested
    changed = TokenSpend().read(context(fetch=Pages({RANKINGS_URL: b"<html></html>", MODELS_URL: fixture("openrouter_models.json")})))
    assert changed.skipped[0].verdict is Verdict.INVALID


def quarters(*rows: tuple[str, float, float]) -> list[Reading]:
    """(quarter, spend, tokens) as the three monthly readings of each quarter."""
    first = {"Q1": 1, "Q2": 4, "Q3": 7, "Q4": 10}
    return [
        Reading(
            check_id="C1", subject="OpenRouter", period=f"{quarter[:4]}-{first[quarter[4:]] + i:02d}", value=spend, data={"tokens": tokens}
        )
        for quarter, spend, tokens in rows
        for i in range(3)
    ]


def verdict(rows: list[Reading]) -> tuple[Verdict, str]:
    [outcome] = TokenSpend().evaluate(rows, TODAY)
    return outcome.verdict, outcome.summary


def test_token_spend_red_after_two_quarters_of_falling_spend_on_rising_volume() -> None:
    two = verdict(quarters(("2025Q4", 100, 10), ("2026Q1", 90, 12), ("2026Q2", 80, 15)))
    assert two[0] is Verdict.RED
    assert "telekomów" not in two[1]
    three = verdict(quarters(("2025Q3", 110, 8), ("2025Q4", 100, 10), ("2026Q1", 90, 12), ("2026Q2", 80, 15)))
    assert three[0] is Verdict.RED
    assert "scenariusz telekomów" in three[1]


def test_token_spend_green_says_how_much_is_volume_and_how_much_price() -> None:
    state, summary = verdict(quarters(("2026Q1", 100, 10), ("2026Q2", 120, 20)))
    assert state is Verdict.GREEN
    assert "wolumen +100.0%" in summary
    assert "cena za token -40.0%" in summary


def test_token_spend_neutral_baseline_and_open_quarters() -> None:
    assert verdict(quarters(("2026Q1", 100, 10), ("2026Q2", 90, 9)))[0] is Verdict.NEUTRAL  # spend and tokens both fell
    assert verdict(quarters(("2026Q2", 100, 10)))[0] is Verdict.BASELINE
    # The current quarter is still open: it is not judged.
    assert verdict(quarters(("2026Q1", 100, 10), ("2026Q2", 90, 12), ("2026Q4", 1, 99)))[0] is Verdict.NEUTRAL
    assert TokenSpend().evaluate([], TODAY) == []


# C2 -------------------------------------------------------------------------------------------

VOLUME_SENTENCE = "We now process more than 1.3 quadrillion tokens per month across our surfaces."


def google_release(sec: Sec) -> None:
    sec.filings("GOOGL", 1652044, [("8-K", "2026-07-23", "2026-07-23", "0001652044-26-000001", "g8k.htm", "2.02,9.01")])
    sec.exhibit(1652044, "0001652044-26-000001", "g8k.htm", "ex99-1.htm", f"<p>Highlights. {VOLUME_SENTENCE} Revenue grew.</p>")


def token_stub(quote: str = VOLUME_SENTENCE, tokens: float = 1.3e15) -> Stub:
    return Stub({TokenVolumeClaim: TokenVolumeClaim(found=True, tokens_per_month=tokens, quote=Quote(source_id="d1", text=quote))})


def test_hyperscaler_tokens_are_read_from_the_earnings_release() -> None:
    sec = Sec()
    google_release(sec)
    result = HyperscalerTokens().read(context(sec=sec, extract=token_stub()))
    [row] = result.readings
    assert (row.subject, row.period, row.value) == ("GOOGL", "2026Q2", 1.3e15)
    assert {o.subject for o in result.skipped} == {"MSFT"}


def test_hyperscaler_tokens_invalid_on_wrong_number_missing_model_or_silent_release() -> None:
    sec = Sec()
    google_release(sec)
    assert not HyperscalerTokens().read(context(sec=sec, extract=token_stub(tokens=9e15))).readings
    no_model = HyperscalerTokens().read(context(sec=sec, extract=None))
    assert [o.verdict for o in no_model.skipped if o.subject == "GOOGL"] == [Verdict.INVALID]
    silent = Sec()
    silent.filings("GOOGL", 1652044, [("8-K", "2026-07-23", "2026-07-23", "0001652044-26-000001", "g8k.htm", "2.02")])
    silent.exhibit(1652044, "0001652044-26-000001", "g8k.htm", "ex99-1.htm", "<p>Revenue grew 14%.</p>")
    assert not HyperscalerTokens().read(context(sec=silent, extract=token_stub())).readings
    again = HyperscalerTokens().read(context(sec=sec, extract=token_stub(), latest={("C2", "GOOGL"): "2026Q2"}))
    assert next(o for o in again.skipped if o.subject == "GOOGL").verdict is Verdict.NOT_READY


def test_hyperscaler_tokens_never_send_and_show_the_yearly_growth() -> None:
    history = [reading("C2", "GOOGL", "2025Q2", 0.5e15), reading("C2", "GOOGL", "2026Q2", 1.3e15)]
    [outcome] = HyperscalerTokens().evaluate(history, TODAY)
    assert outcome.verdict is Verdict.NEUTRAL
    assert "+160% r/r" in outcome.summary
    [alone] = HyperscalerTokens().evaluate([reading("C2", "MSFT", "2026Q2", 4e14)], TODAY)
    assert "r/r" not in alone.summary
