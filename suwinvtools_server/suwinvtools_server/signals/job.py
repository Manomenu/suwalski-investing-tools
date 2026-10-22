"""The signals job from a terminal or a CronJob.

    python -m suwinvtools_server.signals.job run [--dry-run] [--only A1,B2]
    python -m suwinvtools_server.signals.job check A1      # one check, nothing stored or sent
    python -m suwinvtools_server.signals.job test-discord  # a test message on every channel
    python -m suwinvtools_server.signals.job init          # interactive setup of .env

Humans call it through `just signals …` (.just/signals.just); the cluster's CronJob runs `run`.
"""

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime

from suwinvtools_library.marketdata.edgar import Edgar
from suwinvtools_library.marketdata.provider import CACHE_DIR
from suwinvtools_server import db
from suwinvtools_server.settings import settings
from suwinvtools_server.signals import discord, setup
from suwinvtools_server.signals.checks import ALL_CHECKS, by_id
from suwinvtools_server.signals.checks.base import Check, Context
from suwinvtools_server.signals.llm import LlmError, litellm_extractor
from suwinvtools_server.signals.model import Outcome
from suwinvtools_server.signals.runner import Channels, Delivery, run
from suwinvtools_server.signals.sources.http import http_get
from suwinvtools_server.signals.sources.prices import closing_price


def context(today: date) -> Context:
    try:
        extract = litellm_extractor(settings)
    except LlmError as exc:
        logging.getLogger("suwinvtools.signals").warning("%s — the checks that need a model report INVALID", exc)
        extract = None
    return Context(
        today=today,
        edgar=Edgar(cache_dir=CACHE_DIR),
        fetch=http_get,
        extract=extract,
        price=closing_price,
        latest_period=lambda _check_id, _subject: None,  # bound per check by the runner
    )


def channels() -> Channels:
    return Channels(
        green=settings.discord_webhook_green,
        red=settings.discord_webhook_red,
        status=settings.discord_webhook_status,
        red_mention=settings.discord_red_mention,
        web_base=settings.web_base,
    )


def write(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def show(outcomes: list[Outcome]) -> None:
    for outcome in outcomes:
        write(f"{outcome.check_id:<3} {outcome.verdict.value:<11} {outcome.subject:<16} {outcome.period:<10} {outcome.summary}")
        for item in outcome.evidence[:3]:
            write(f"    ↳ {item.title}: {item.url}" + (f" — „{item.quote[:120]}”" if item.quote else ""))


def selected(only: str) -> list[Check]:
    if not only:
        return list(ALL_CHECKS)
    wanted = [by_id(check_id.strip()) for check_id in only.split(",") if check_id.strip()]
    missing = [check_id for check_id, check in zip(only.split(","), wanted, strict=True) if check is None]
    if missing:
        raise SystemExit(f"unknown checks: {', '.join(missing)} (known: {', '.join(c.meta.id for c in ALL_CHECKS)})")
    return [check for check in wanted if check is not None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signals", description="AI cycle signals")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="one run: read, judge, send what changed")
    run_parser.add_argument("--dry-run", action="store_true", help="print the verdicts; store and send nothing")
    run_parser.add_argument("--only", default="", help="comma-separated check ids, e.g. A1,B4")
    check_parser = commands.add_parser("check", help="one check with every verdict and source; nothing stored or sent")
    check_parser.add_argument("check_id")
    commands.add_parser("test-discord", help="a test message on every configured channel")
    commands.add_parser("init", help="interactive setup of the webhooks and the model in .env")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.command == "init":
        return setup.main()
    if args.command == "test-discord":
        return test_discord()

    dry_run = args.command == "check" or bool(args.dry_run)
    checks = selected(args.check_id if args.command == "check" else args.only)
    pool = db.new_pool(settings.database_url, max_size=2)
    with pool:
        with pool.connection() as conn:
            db.migrate(conn)
        delivery = Delivery(channels=channels(), post=discord.post, version=os.environ.get("IMAGE_TAG", ""))
        report = run(pool, checks, context(datetime.now(UTC).date()), delivery, dry_run=dry_run)
    show(report.outcomes)
    write()
    write(" · ".join(f"{verdict}: {count}" for verdict, count in sorted(report.counts.items())) + f" · wysłano: {len(report.sent)}")
    for failure in report.failed_posts:
        write(f"nie wysłano: {failure}")
    return 1 if report.failed_posts else 0


def test_discord() -> int:
    sent = 0
    for name, url in (
        ("green", settings.discord_webhook_green),
        ("red", settings.discord_webhook_red),
        ("status", settings.discord_webhook_status),
    ):
        if not url:
            write(f"{name}: off")
            continue
        try:
            discord.post(url, discord.status_message([f"Kanał {name} działa."], title="suwinvtools · test"))
        except discord.DiscordError as exc:
            write(f"{name}: {exc}")
            continue
        write(f"{name}: sent")
        sent += 1
    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
