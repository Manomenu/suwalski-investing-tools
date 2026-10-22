"""The runner against a real database: what is stored, what is sent, and what is sent again."""

from collections.abc import Sequence
from datetime import date
from typing import override

import pytest
from psycopg_pool import ConnectionPool

from suwinvtools_server.signals import store
from suwinvtools_server.signals.checks.base import Check, CheckMeta, Context, ReadResult
from suwinvtools_server.signals.discord import DiscordError
from suwinvtools_server.signals.model import Category, JsonValue, Outcome, Reading, Verdict
from suwinvtools_server.signals.runner import Channels, Delivery, run
from tests.signals.fakes import context

CHANNELS = Channels(green="https://green", red="https://red", status="https://status", web_base="http://web")


class Scripted(Check):
    """Reads the readings it is given and judges each by a table of value -> verdict."""

    meta = CheckMeta(id="T1", category=Category.A, title="test", question="?", rule_red="r", rule_green="g", unit="", caveat="sample")

    def __init__(self, readings: Sequence[Reading], verdicts: dict[float, Verdict], *, fail: bool = False) -> None:
        self.readings = list(readings)
        self.verdicts = verdicts
        self.fail = fail

    @override
    def read(self, ctx: Context) -> ReadResult:
        if self.fail:
            raise RuntimeError("source down")
        return ReadResult(readings=self.readings)

    @override
    def evaluate(self, history: Sequence[Reading], today: date) -> list[Outcome]:
        latest = max(history, key=lambda reading: reading.period)
        return [self.outcome(latest, self.verdicts[latest.value or 0], f"value {latest.value}")]


class Outbox:
    def __init__(self, *, failing: bool = False) -> None:
        self.sent: list[tuple[str, dict[str, JsonValue]]] = []
        self.failing = failing

    def __call__(self, url: str, payload: dict[str, JsonValue]) -> None:
        if self.failing:
            raise DiscordError("webhook answered 500")
        self.sent.append((url, payload))

    def urls(self) -> list[str]:
        return [url for url, _ in self.sent]


@pytest.fixture
def clean(pool: ConnectionPool) -> ConnectionPool:
    with pool.connection() as conn:
        conn.execute("TRUNCATE signal_readings, signal_outcomes, signal_runs")
    return pool


def reading(period: str, value: float) -> Reading:
    return Reading(check_id="T1", subject="X", period=period, value=value)


def test_a_red_verdict_is_sent_once(clean: ConnectionPool) -> None:
    check = Scripted([reading("2026Q2", 1)], {1: Verdict.RED})
    outbox = Outbox()

    run(clean, [check], context(), Delivery(CHANNELS, outbox))
    run(clean, [check], context(), Delivery(CHANNELS, outbox))

    assert outbox.urls().count("https://red") == 1
    # The run summary goes to the status channel every time.
    assert outbox.urls().count("https://status") == 2


def test_a_changed_verdict_for_the_same_period_is_sent_again(clean: ConnectionPool) -> None:
    outbox = Outbox()
    run(clean, [Scripted([reading("2026Q2", 1)], {1: Verdict.UNCONFIRMED})], context(), Delivery(CHANNELS, outbox))
    run(clean, [Scripted([reading("2026Q2", 2)], {2: Verdict.RED})], context(), Delivery(CHANNELS, outbox))

    # The unconfirmed claim went to status, the confirmed one to red.
    assert [url for url in outbox.urls() if url == "https://red"] == ["https://red"]


def test_quiet_verdicts_are_stored_but_not_sent(clean: ConnectionPool) -> None:
    outbox = Outbox()
    run(clean, [Scripted([reading("2026Q2", 1)], {1: Verdict.NEUTRAL})], context(), Delivery(CHANNELS, outbox))

    assert outbox.urls() == ["https://status"]
    with clean.connection() as conn:
        assert [stored.outcome.verdict for stored in store.outcomes(conn)] == [Verdict.NEUTRAL]


def test_a_failed_post_is_retried_on_the_next_run(clean: ConnectionPool) -> None:
    check = Scripted([reading("2026Q2", 1)], {1: Verdict.GREEN})
    report = run(clean, [check], context(), Delivery(CHANNELS, Outbox(failing=True)))
    outbox = Outbox()
    run(clean, [check], context(), Delivery(CHANNELS, outbox))

    assert report.failed_posts
    assert "https://green" in outbox.urls()


def test_a_broken_check_becomes_invalid_and_the_others_still_run(clean: ConnectionPool) -> None:
    broken = Scripted([], {}, fail=True)
    fine = Scripted([reading("2026Q2", 1)], {1: Verdict.RED})
    outbox = Outbox()

    report = run(clean, [broken, fine], context(), Delivery(CHANNELS, outbox))

    assert [outcome.verdict for outcome in report.outcomes] == [Verdict.INVALID, Verdict.RED]
    assert "source down" in report.outcomes[0].summary
    assert "https://red" in outbox.urls()


def test_a_dry_run_stores_and_sends_nothing(clean: ConnectionPool) -> None:
    outbox = Outbox()
    report = run(clean, [Scripted([reading("2026Q2", 1)], {1: Verdict.RED})], context(), Delivery(CHANNELS, outbox), dry_run=True)

    assert [outcome.verdict for outcome in report.outcomes] == [Verdict.RED]
    assert outbox.sent == []
    with clean.connection() as conn:
        assert store.readings(conn, "T1") == []
        assert store.last_run(conn) is None


def test_messages_link_to_the_check_page(clean: ConnectionPool) -> None:
    outbox = Outbox()
    run(clean, [Scripted([reading("2026Q2", 1)], {1: Verdict.RED})], context(), Delivery(CHANNELS, outbox))

    red = next(payload for url, payload in outbox.sent if url == "https://red")
    embeds = red["embeds"]
    assert isinstance(embeds, list)
    embed = embeds[0]
    assert isinstance(embed, dict)
    assert embed["url"] == "http://web/signals/T1"
