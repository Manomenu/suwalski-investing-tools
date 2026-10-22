"""Discord webhooks: one message per verdict, one embed per message.

Green goes to its own channel so it can be muted on Discord's side (Mute, or "Only
@mentions") without a line of code — the messages are still there to read. Red mentions a
role when DISCORD_RED_MENTION is set, so it pings even on a muted server.
"""

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import cast

from suwinvtools_server.signals.model import JsonValue, Outcome, Verdict

COLORS = {Verdict.RED: 0xD83C3E, Verdict.GREEN: 0x2EA043}
STATUS_COLOR = 0x8B949E
VERDICT_WORDS = {
    Verdict.RED: "RED",
    Verdict.GREEN: "GREEN",
    Verdict.NEUTRAL: "neutral",
    Verdict.BASELINE: "baseline",
    Verdict.NOT_READY: "not ready",
    Verdict.INVALID: "INVALID",
    Verdict.UNCONFIRMED: "unconfirmed",
}

# url, JSON body -> HTTP status, Retry-After seconds. Injectable so the tests post nowhere.
type Send = Callable[[str, bytes], tuple[int, float]]


class DiscordError(RuntimeError):
    pass


def http_send(url: str, body: bytes) -> tuple[int, float]:
    request = urllib.request.Request(  # noqa: S310 — a webhook URL from settings
        url, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": "suwinvtools-signals/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 — same
            return cast(int, response.status), 0.0
    except urllib.error.HTTPError as exc:
        retry = exc.headers.get("Retry-After") if exc.headers else None
        return exc.code, float(retry) if retry else 0.0
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DiscordError(str(exc)) from exc


def post(url: str, payload: dict[str, JsonValue], *, send: Send = http_send, sleep: Callable[[float], None] = time.sleep) -> None:
    """Posts one message, waiting out a rate limit (429) twice at most."""
    body = json.dumps(payload).encode()
    for _ in range(3):
        status, retry_after = send(url, body)
        if 200 <= status < 300:
            return
        if status != 429:
            raise DiscordError(f"webhook answered {status}")
        sleep(min(retry_after or 2.0, 30.0))
    raise DiscordError("webhook kept answering 429")


def verdict_message(outcome: Outcome, *, title: str, link: str, footer: str, mention: str = "") -> dict[str, JsonValue]:
    """The message for a verdict: title with the check and the period, the sentence that
    decided it, up to five sources with their words, and a link to the check's page."""
    sources: list[JsonValue] = []
    for item in outcome.evidence[:5]:
        quote = f" — „{_cut(item.quote, 100)}”" if item.quote else ""
        sources.append(f"[{_cut(item.title, 60)}]({item.url}){quote}")
    fields: list[JsonValue] = []
    if sources:
        fields.append({"name": "Źródła", "value": _cut("\n".join(str(source) for source in sources), 1000)})
    embed: dict[str, JsonValue] = {
        "title": _cut(f"{outcome.check_id} · {title} · {outcome.subject} · {outcome.period}", 250),
        "description": _cut(outcome.summary, 2000),
        "color": COLORS.get(outcome.verdict, STATUS_COLOR),
        "fields": fields,
        "footer": {"text": _cut(footer, 200)},
    }
    if link:
        embed["url"] = link
    message: dict[str, JsonValue] = {"embeds": [embed]}
    if mention and outcome.verdict is Verdict.RED:
        message["content"] = mention
    return message


def status_message(lines: list[str], *, title: str) -> dict[str, JsonValue]:
    return {"embeds": [{"title": _cut(title, 250), "description": _cut("\n".join(lines) or "—", 4000), "color": STATUS_COLOR}]}


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
