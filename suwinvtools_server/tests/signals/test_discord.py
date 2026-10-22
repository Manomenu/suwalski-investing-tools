import json

import pytest

from suwinvtools_server.signals.discord import DiscordError, post, status_message, verdict_message
from suwinvtools_server.signals.model import Evidence, JsonValue, Outcome, Verdict


def outcome(verdict: Verdict = Verdict.RED, *, evidence: tuple[Evidence, ...] = ()) -> Outcome:
    return Outcome(
        check_id="B4", subject="GPU", period="2026-10", verdict=verdict, summary="H200 potaniał o 23% w 3 miesiące.", evidence=evidence
    )


def embed(message: dict[str, JsonValue]) -> dict[str, JsonValue]:
    embeds = message["embeds"]
    assert isinstance(embeds, list)
    first = embeds[0]
    assert isinstance(first, dict)
    return first


def test_a_red_verdict_message_carries_the_sentence_sources_link_and_mention() -> None:
    sources = tuple(Evidence(url=f"https://example.com/{i}", title=f"Source {i}", quote="words of the source") for i in range(7))
    message = verdict_message(
        outcome(evidence=sources), title="Ceny GPU", link="https://signals.example/b4", footer="run 12", mention="<@&1>"
    )
    card = embed(message)
    assert card["title"] == "B4 · Ceny GPU · GPU · 2026-10"
    assert card["description"] == "H200 potaniał o 23% w 3 miesiące."
    assert card["color"] == 0xD83C3E
    assert card["url"] == "https://signals.example/b4"
    assert card["footer"] == {"text": "run 12"}
    fields = card["fields"]
    assert isinstance(fields, list)
    [field] = fields
    assert isinstance(field, dict)
    assert field["name"] == "Źródła"
    assert str(field["value"]).count("https://example.com/") == 5  # at most five sources
    assert message["content"] == "<@&1>"


def test_green_has_its_own_colour_and_never_mentions_and_empty_parts_are_left_out() -> None:
    message = verdict_message(outcome(Verdict.GREEN), title="t", link="", footer="f", mention="<@&1>")
    card = embed(message)
    assert card["color"] == 0x2EA043
    assert "content" not in message
    assert "url" not in card
    assert card["fields"] == []


def test_long_text_is_cut_to_what_discord_accepts() -> None:
    long = Outcome(check_id="A1", subject="s", period="p", verdict=Verdict.RED, summary="x" * 5000)
    description = str(embed(verdict_message(long, title="t", link="", footer="f"))["description"])
    assert len(description) == 2000
    assert description.endswith("…")


def test_status_message_joins_lines() -> None:
    card = embed(status_message(["a", "b"], title="Status"))
    assert (card["title"], card["description"]) == ("Status", "a\nb")
    assert embed(status_message([], title="Status"))["description"] == "—"


class Webhook:
    """Answers the given (status, Retry-After) pairs in turn and remembers what it was sent."""

    def __init__(self, *answers: tuple[int, float]) -> None:
        self.answers = list(answers)
        self.sent: list[tuple[str, bytes]] = []
        self.slept: list[float] = []

    def send(self, url: str, body: bytes) -> tuple[int, float]:
        self.sent.append((url, body))
        return self.answers.pop(0)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def test_post_sends_the_payload_once_when_discord_accepts_it() -> None:
    hook = Webhook((204, 0.0))
    post("https://discord.example/hook", {"content": "hi"}, send=hook.send, sleep=hook.sleep)
    assert [(url, json.loads(body)) for url, body in hook.sent] == [("https://discord.example/hook", {"content": "hi"})]
    assert not hook.slept


def test_post_waits_out_a_rate_limit_and_tries_again() -> None:
    hook = Webhook((429, 1.5), (429, 99.0), (204, 0.0))
    post("https://discord.example/hook", {"content": "hi"}, send=hook.send, sleep=hook.sleep)
    assert len(hook.sent) == 3
    assert hook.slept == [1.5, 30.0]  # Retry-After, capped at 30 s


def test_post_gives_up_after_three_rate_limits_and_on_other_errors() -> None:
    limited = Webhook((429, 0.0), (429, 0.0), (429, 0.0))
    with pytest.raises(DiscordError, match="429"):
        post("https://discord.example/hook", {}, send=limited.send, sleep=limited.sleep)
    assert limited.slept == [2.0, 2.0, 2.0]
    broken = Webhook((500, 0.0))
    with pytest.raises(DiscordError, match="500"):
        post("https://discord.example/hook", {}, send=broken.send, sleep=broken.sleep)
    assert len(broken.sent) == 1
