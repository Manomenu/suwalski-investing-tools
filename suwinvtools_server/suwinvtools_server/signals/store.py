"""SQL of the signals feature: readings, outcomes and runs (migrations/001_signals.sql)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from psycopg import Connection
from psycopg.types.json import Jsonb

from suwinvtools_server.signals.model import Evidence, JsonValue, Outcome, Reading, Verdict


@dataclass(frozen=True)
class StoredReading:
    reading: Reading
    read_at: datetime


@dataclass(frozen=True)
class StoredOutcome:
    outcome: Outcome
    evaluated_at: datetime
    notified_at: datetime | None


@dataclass(frozen=True)
class Run:
    id: int
    started_at: datetime
    finished_at: datetime | None
    dry_run: bool
    counts: dict[str, int]


def _evidence_json(evidence: Iterable[Evidence]) -> Jsonb:
    return Jsonb([{"url": item.url, "title": item.title, "quote": item.quote} for item in evidence])


def _evidence(raw: object) -> tuple[Evidence, ...]:
    items = cast(list[dict[str, str]], raw) if isinstance(raw, list) else []
    return tuple(Evidence(url=item.get("url", ""), title=item.get("title", ""), quote=item.get("quote", "")) for item in items)


def _json(raw: object) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], raw) if isinstance(raw, dict) else {}


def save_reading(conn: Connection, reading: Reading) -> None:
    conn.execute(
        """
        INSERT INTO signal_readings (check_id, subject, period, value, data, evidence)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (check_id, subject, period)
        DO UPDATE SET value = excluded.value, data = excluded.data, evidence = excluded.evidence, read_at = now()
        """,
        (reading.check_id, reading.subject, reading.period, reading.value, Jsonb(reading.data), _evidence_json(reading.evidence)),
    )


def readings(conn: Connection, check_id: str, subject: str | None = None) -> list[StoredReading]:
    """A check's readings, oldest period first (periods sort as text: 2026Q3, 2026-10, …)."""
    rows = conn.execute(
        """
        SELECT check_id, subject, period, value, data, evidence, read_at FROM signal_readings
        WHERE check_id = %s AND (%s::text IS NULL OR subject = %s)
        ORDER BY subject, period
        """,
        (check_id, subject, subject),
    ).fetchall()
    return [
        StoredReading(
            reading=Reading(check_id=row[0], subject=row[1], period=row[2], value=row[3], data=_json(row[4]), evidence=_evidence(row[5])),
            read_at=row[6],
        )
        for row in rows
    ]


def latest_period(conn: Connection, check_id: str, subject: str) -> str | None:
    row = conn.execute(
        "SELECT max(period) FROM signal_readings WHERE check_id = %s AND subject = %s",
        (check_id, subject),
    ).fetchone()
    return None if row is None else cast(str | None, row[0])


def latest_read_at(conn: Connection, check_id: str) -> datetime | None:
    row = conn.execute("SELECT max(read_at) FROM signal_readings WHERE check_id = %s", (check_id,)).fetchone()
    return None if row is None else cast(datetime | None, row[0])


def save_outcome(conn: Connection, outcome: Outcome) -> bool:
    """Stores the verdict and says whether it still has to reach Discord: a verdict new for its
    period, or one that changed (an unconfirmed claim that became red), or one a failed post
    left unsent."""
    previous = conn.execute(
        "SELECT verdict, notified_at FROM signal_outcomes WHERE check_id = %s AND subject = %s AND period = %s",
        (outcome.check_id, outcome.subject, outcome.period),
    ).fetchone()
    changed = previous is None or previous[0] != outcome.verdict
    conn.execute(
        """
        INSERT INTO signal_outcomes (check_id, subject, period, verdict, summary, evidence, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (check_id, subject, period) DO UPDATE SET
            verdict = excluded.verdict, summary = excluded.summary, evidence = excluded.evidence,
            details = excluded.details, evaluated_at = now(),
            notified_at = CASE WHEN signal_outcomes.verdict = excluded.verdict THEN signal_outcomes.notified_at END
        """,
        (
            outcome.check_id,
            outcome.subject,
            outcome.period,
            outcome.verdict.value,
            outcome.summary,
            _evidence_json(outcome.evidence),
            Jsonb(outcome.details),
        ),
    )
    return changed or previous is None or previous[1] is None


def mark_notified(conn: Connection, outcome: Outcome) -> None:
    conn.execute(
        "UPDATE signal_outcomes SET notified_at = now() WHERE check_id = %s AND subject = %s AND period = %s",
        (outcome.check_id, outcome.subject, outcome.period),
    )


def outcomes(
    conn: Connection, *, check_id: str | None = None, verdicts: Iterable[Verdict] | None = None, limit: int = 200
) -> list[StoredOutcome]:
    """Outcomes, newest first."""
    wanted = None if verdicts is None else [verdict.value for verdict in verdicts]
    rows = conn.execute(
        """
        SELECT check_id, subject, period, verdict, summary, evidence, details, evaluated_at, notified_at
        FROM signal_outcomes
        WHERE (%s::text IS NULL OR check_id = %s) AND (%s::text[] IS NULL OR verdict = ANY(%s::text[]))
        ORDER BY evaluated_at DESC, check_id, subject, period DESC
        LIMIT %s
        """,
        (check_id, check_id, wanted, wanted, limit),
    ).fetchall()
    return [
        StoredOutcome(
            outcome=Outcome(
                check_id=row[0],
                subject=row[1],
                period=row[2],
                verdict=Verdict(row[3]),
                summary=row[4],
                evidence=_evidence(row[5]),
                details=_json(row[6]),
            ),
            evaluated_at=row[7],
            notified_at=row[8],
        )
        for row in rows
    ]


def start_run(conn: Connection, *, dry_run: bool) -> int:
    row = conn.execute("INSERT INTO signal_runs (dry_run) VALUES (%s) RETURNING id", (dry_run,)).fetchone()
    assert row is not None  # noqa: S101 — INSERT … RETURNING always returns the row
    return cast(int, row[0])


def finish_run(conn: Connection, run_id: int, counts: dict[str, int]) -> None:
    conn.execute("UPDATE signal_runs SET finished_at = now(), counts = %s WHERE id = %s", (Jsonb(counts), run_id))


def last_run(conn: Connection) -> Run | None:
    row = conn.execute(
        "SELECT id, started_at, finished_at, dry_run, counts FROM signal_runs WHERE NOT dry_run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return Run(id=row[0], started_at=row[1], finished_at=row[2], dry_run=row[3], counts=cast(dict[str, int], row[4]))
