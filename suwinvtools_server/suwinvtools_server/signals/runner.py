"""One run of the job: every check reads, is judged, and what changed reaches Discord.

Each check runs in a transaction of its own, so one that breaks halfway leaves nothing half
stored and does not stop the others — it becomes an INVALID verdict with the error. A dry run
does everything in transactions that are rolled back, and posts nothing.
"""

import dataclasses
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import psycopg
from psycopg_pool import ConnectionPool

from suwinvtools_server.signals import discord, store
from suwinvtools_server.signals.checks.base import Check, Context, month
from suwinvtools_server.signals.model import JsonValue, Outcome, Verdict

log = logging.getLogger("suwinvtools.signals")

# Verdicts that are only counted: nothing new, or nothing to say.
QUIET = frozenset({Verdict.NOT_READY, Verdict.NEUTRAL, Verdict.BASELINE})


@dataclass(frozen=True)
class Channels:
    green: str = ""
    red: str = ""
    status: str = ""
    red_mention: str = ""
    web_base: str = ""

    def for_verdict(self, verdict: Verdict) -> str:
        if verdict is Verdict.RED:
            return self.red
        if verdict is Verdict.GREEN:
            return self.green
        return self.status


@dataclass(frozen=True)
class Delivery:
    channels: Channels
    post: "Post"
    # Shown in every message's footer: the image tag the job runs from.
    version: str = ""


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list[Outcome])
    sent: list[Outcome] = field(default_factory=list[Outcome])
    failed_posts: list[str] = field(default_factory=list[str])

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(outcome.verdict.value for outcome in self.outcomes))


type Post = Callable[[str, dict[str, JsonValue]], None]


def run(pool: ConnectionPool, checks: Sequence[Check], ctx: Context, delivery: Delivery, *, dry_run: bool = False) -> Report:
    report = Report()
    run_id = None
    if not dry_run:
        with pool.connection() as conn:
            run_id = store.start_run(conn, dry_run=False)

    for check in checks:
        with pool.connection() as conn:
            try:
                outcomes, pending = _run_in_transaction(conn, check, ctx, dry_run=dry_run)
            except Exception as exc:
                log.exception("check %s failed", check.meta.id)
                failure = check.skip("—", month(ctx.today), Verdict.INVALID, f"błąd: {type(exc).__name__}: {exc}")
                outcomes, pending = [failure], []
                if not dry_run:
                    with conn.transaction():
                        pending = [failure] if _save(conn, failure) else []
        report.outcomes.extend(outcomes)
        if dry_run:
            continue
        for outcome in pending:
            _notify(pool, check, outcome, delivery, report)

    if not dry_run and run_id is not None:
        with pool.connection() as conn:
            store.finish_run(conn, run_id, report.counts)
        _summarise(report, delivery)
    return report


def _run_in_transaction(conn: psycopg.Connection, check: Check, ctx: Context, *, dry_run: bool) -> tuple[list[Outcome], list[Outcome]]:
    """The check's verdicts and those still to be sent. A dry run rolls everything back."""
    outcomes: list[Outcome] = []
    pending: list[Outcome] = []
    with conn.transaction():
        outcomes = _run_check(conn, check, ctx)
        pending = [outcome for outcome in outcomes if _save(conn, outcome)]
        if dry_run:
            raise psycopg.Rollback  # psycopg ends the transaction here and swallows it
    return outcomes, pending


def _run_check(conn: psycopg.Connection, check: Check, ctx: Context) -> list[Outcome]:
    def latest(check_id: str, subject: str) -> str | None:
        return store.latest_period(conn, check_id, subject)

    bound = dataclasses.replace(ctx, latest_period=latest)
    result = check.read(bound)
    for reading in result.readings:
        store.save_reading(conn, reading)
    history = [stored.reading for stored in store.readings(conn, check.meta.id)]
    # A failed attempt is about this month, whatever period it was trying to read: it must
    # never overwrite the verdict a period already has.
    skipped = [
        dataclasses.replace(outcome, period=month(ctx.today)) if outcome.verdict is Verdict.INVALID else outcome
        for outcome in result.skipped
    ]
    return [*check.evaluate(history, ctx.today), *skipped]


def _save(conn: psycopg.Connection, outcome: Outcome) -> bool:
    """Stores a verdict; True when it still has to be posted."""
    if outcome.verdict is Verdict.NOT_READY:
        return False  # "nothing new" is not a verdict on any period
    must_send = store.save_outcome(conn, outcome)
    return must_send and outcome.verdict not in QUIET


def _notify(pool: ConnectionPool, check: Check, outcome: Outcome, delivery: Delivery, report: Report) -> None:
    channels = delivery.channels
    url = channels.for_verdict(outcome.verdict)
    if not url:
        log.info("%s %s %s: %s (channel off)", outcome.check_id, outcome.subject, outcome.verdict, outcome.summary)
        return
    footer = " · ".join(part for part in (check.meta.id, check.meta.caveat, delivery.version) if part)
    link = f"{channels.web_base.rstrip('/')}/signals/{check.meta.id}" if channels.web_base else ""
    message = discord.verdict_message(outcome, title=check.meta.title, link=link, footer=footer, mention=channels.red_mention)
    try:
        delivery.post(url, message)
    except discord.DiscordError as exc:
        # Left unmarked, so the next run tries again.
        report.failed_posts.append(f"{outcome.check_id} {outcome.subject}: {exc}")
        return
    with pool.connection() as conn:
        store.mark_notified(conn, outcome)
    report.sent.append(outcome)


def _summarise(report: Report, delivery: Delivery) -> None:
    """One message per run on the status channel — its absence in a month says the job did not run."""
    channels, post = delivery.channels, delivery.post
    if not channels.status:
        return
    counts = report.counts
    lines = [" · ".join(f"{verdict}: {count}" for verdict, count in sorted(counts.items()))]
    lines += [f"• {o.check_id} {o.subject}: {o.summary}" for o in report.outcomes if o.verdict is Verdict.INVALID][:20]
    if report.failed_posts:
        lines.append("Nie wysłano: " + "; ".join(report.failed_posts))
    try:
        post(channels.status, discord.status_message(lines, title=f"Run sygnałów — wysłano {len(report.sent)}"))
    except discord.DiscordError:
        log.warning("the run summary did not reach the status channel")
