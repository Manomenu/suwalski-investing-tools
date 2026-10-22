"""Read-only HTTP view of the signals: the board, the feed and one check's history."""

from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from suwinvtools_server import db
from suwinvtools_server.signals import store
from suwinvtools_server.signals.checks import ALL_CHECKS, by_id
from suwinvtools_server.signals.checks.base import Check
from suwinvtools_server.signals.model import (
    CATEGORY_NAMES,
    Board,
    BoardItem,
    CheckHistory,
    CheckInfo,
    EvidenceOut,
    OutcomeOut,
    ReadingOut,
    RunOut,
    Verdict,
)

router = APIRouter(prefix="/signals", tags=["signals"])

# What the board puts first: a red tells more than a green, a green more than silence.
_WEIGHT = {Verdict.RED: 4, Verdict.GREEN: 3, Verdict.UNCONFIRMED: 2, Verdict.NEUTRAL: 1, Verdict.BASELINE: 1}


def info(check: Check) -> CheckInfo:
    meta = check.meta
    return CheckInfo(
        id=meta.id,
        category=meta.category,
        category_name=CATEGORY_NAMES[meta.category],
        title=meta.title,
        question=meta.question,
        rule_red=meta.rule_red,
        rule_green=meta.rule_green,
        unit=meta.unit,
        caveat=meta.caveat,
    )


def outcome_out(stored: store.StoredOutcome) -> OutcomeOut:
    outcome = stored.outcome
    return OutcomeOut(
        check_id=outcome.check_id,
        subject=outcome.subject,
        period=outcome.period,
        verdict=outcome.verdict,
        summary=outcome.summary,
        evidence=[EvidenceOut(url=item.url, title=item.title, quote=item.quote) for item in outcome.evidence],
        evaluated_at=stored.evaluated_at.isoformat(),
        notified=stored.notified_at is not None,
    )


def headline(latest: Iterable[OutcomeOut]) -> OutcomeOut | None:
    """The newest period wins; within it, the weightiest verdict."""
    scored = [item for item in latest if item.verdict in _WEIGHT]
    return max(scored, key=lambda item: (item.period, _WEIGHT[item.verdict]), default=None)


@router.get("")
def board(conn: Connection = Depends(db.connection)) -> Board:
    """Every check with its current verdict — the page the web app opens on."""
    items: list[BoardItem] = []
    for check in ALL_CHECKS:
        stored = store.outcomes(conn, check_id=check.meta.id, limit=500)
        newest: dict[str, OutcomeOut] = {}
        for item in sorted((outcome_out(entry) for entry in stored), key=lambda out: out.period):
            newest[item.subject] = item
        latest = sorted(newest.values(), key=lambda out: out.subject)
        top = headline(latest)
        spark = (
            [r.reading.value for r in store.readings(conn, check.meta.id, top.subject) if r.reading.value is not None]
            if top is not None
            else []
        )
        items.append(BoardItem(check=info(check), headline=top, latest=latest, spark=spark[-12:]))
    run = store.last_run(conn)
    last = (
        None
        if run is None
        else RunOut(
            id=run.id,
            started_at=run.started_at.isoformat(),
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            dry_run=run.dry_run,
            counts=run.counts,
        )
    )
    return Board(items=items, last_run=last)


@router.get("/feed")
def feed(
    verdict: list[Verdict] = Query(default=[Verdict.RED, Verdict.GREEN]),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(db.connection),
) -> list[OutcomeOut]:
    """Verdicts, newest first — the same as the Discord channels, muted greens included."""
    return [outcome_out(item) for item in store.outcomes(conn, verdicts=verdict, limit=limit)]


@router.get("/{check_id}")
def history(check_id: str, conn: Connection = Depends(db.connection)) -> CheckHistory:
    check = by_id(check_id)
    if check is None:
        raise HTTPException(status_code=404, detail=f"nie ma checka {check_id}")
    readings = [
        ReadingOut(subject=r.reading.subject, period=r.reading.period, value=r.reading.value, read_at=r.read_at.isoformat())
        for r in store.readings(conn, check.meta.id)
    ]
    outcomes = [outcome_out(item) for item in store.outcomes(conn, check_id=check.meta.id, limit=500)]
    return CheckHistory(check=info(check), readings=readings, outcomes=outcomes)
