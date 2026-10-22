"""`just signals init` — asks for what the signals job needs and writes it to the root .env.

Every answer is checked on the spot: a webhook must be Discord's and answer, green and red
must be different channels, the model endpoint must list its models and fill a schema. Enter
keeps the current value. Existing keys are updated in place and the rest of .env is left as
it was; the previous file is kept as .env.bak. Cluster secrets are not here: the platform
repo's setup.sh asks the same questions for the cluster.
"""

import getpass
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import cast

from suwinvtools_library.constants import SOLUTION_ROOT
from suwinvtools_server.settings import Settings
from suwinvtools_server.signals import discord
from suwinvtools_server.signals.llm import Document, LlmError, litellm_extractor
from suwinvtools_server.signals.model import GrowthClaim

ENV_FILE = SOLUTION_ROOT / ".env"
WEBHOOK = re.compile(r"^https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/(\d+)/[\w-]+$")

type Ask = Callable[[str], str]


def set_keys(text: str, values: dict[str, str]) -> str:
    """`text` (a .env file) with each key set: in place where it already is (also when it is
    commented out as an example), appended otherwise."""
    lines = text.splitlines()
    for key, value in values.items():
        line = f"{key}={value}"
        index = next((i for i, existing in enumerate(lines) if existing.startswith(f"{key}=")), None)
        if index is None:
            index = next((i for i, existing in enumerate(lines) if existing.startswith(f"# {key}=")), None)
        if index is None:
            lines.append(line)
        else:
            lines[index] = line
    return "\n".join(lines) + "\n"


def webhook_channel(url: str) -> str | None:
    """The channel id a webhook posts to, or None when it is no Discord webhook or does not answer."""
    if not WEBHOOK.match(url):
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "suwinvtools"}), timeout=15) as response:  # noqa: S310 — a Discord webhook, matched above
            body = cast(dict[str, object], json.loads(response.read()))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    channel = body.get("channel_id")
    return str(channel) if channel else None


def model_names(body: bytes) -> list[str]:
    """Model ids of an OpenAI-compatible GET /models answer."""
    parsed = cast(dict[str, object], json.loads(body))
    return [str(cast(dict[str, object], item).get("id", "")) for item in cast(list[object], parsed.get("data", []))]


def list_models(base_url: str, api_key: str) -> tuple[str, list[str]] | None:
    """The base URL that answers GET /models (as given, or with /v1 added) and its models."""
    for base in (base_url.rstrip("/"), base_url.rstrip("/") + "/v1"):
        request = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {api_key or 'dummy'}"})  # noqa: S310 — the owner's endpoint
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 — same
                return base, model_names(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return None


def write(line: str = "") -> None:
    sys.stdout.write(line + "\n")


class Questions:
    """Asks with the current value as the default; a hidden question never shows the value."""

    def __init__(self, ask: Ask, secret: Ask) -> None:
        self.ask, self.secret = ask, secret

    def __call__(self, prompt: str, now: str, *, hidden: bool = False) -> str:
        shown = "(ustawione)" if hidden and now else now or "—"
        answer = (self.secret if hidden else self.ask)(f"{prompt} [{shown}]: ").strip()
        return answer or now


def ask_channels(question: Questions, current: Settings) -> dict[str, str]:
    values: dict[str, str] = {}
    channels: list[str] = []
    for key, label, required in (
        ("DISCORD_WEBHOOK_GREEN", "Webhook kanału green", True),
        ("DISCORD_WEBHOOK_RED", "Webhook kanału red", True),
        ("DISCORD_WEBHOOK_STATUS", "Webhook kanału status (Enter = bez)", False),
    ):
        now = str(getattr(current, key.lower()))
        while True:
            url = question(label, now, hidden=True)
            if not url and not required:
                break
            channel = webhook_channel(url)
            if channel is None:
                write("  to nie jest działający webhook Discorda — spróbuj jeszcze raz")
                continue
            if channel in channels:
                write("  ten webhook pisze na ten sam kanał co poprzedni — green i red muszą być osobne")
                continue
            channels.append(channel)
            break
        values[key] = url
    values["DISCORD_RED_MENTION"] = question("Wzmianka przy red, np. <@&id roli> (Enter = bez)", current.discord_red_mention)
    return values


def ask_model(question: Questions, current: Settings) -> dict[str, str]:
    while True:
        base = question("Base URL", current.llm_base_url)
        key = question("API key (Enter = bez)", current.llm_api_key, hidden=True)
        found = list_models(base, key) if base else None
        if found is None:
            write("  pod tym adresem nie ma GET /models — spróbuj jeszcze raz")
            continue
        base, models = found
        write("  modele: " + ", ".join(models[:20]))
        model = question("Model", current.llm_model or (models[0] if models else ""))
        return {"LLM_BASE_URL": base, "LLM_API_KEY": key, "LLM_MODEL": model}


def main(ask: Ask = input, secret: Ask = getpass.getpass, env_file: Path = ENV_FILE) -> int:
    current = Settings()
    question = Questions(ask, secret)

    write("== Sygnały: kanały Discorda ==")
    values = ask_channels(question, current)
    write("\n== SEC EDGAR ==")
    # Read by the library straight from the environment, not through Settings.
    values["SEC_USER_AGENT"] = question("Identyfikacja dla SEC: 'Imię Nazwisko email'", os.environ.get("SEC_USER_AGENT", ""))
    write("\n== Model językowy (dowolny endpoint zgodny z OpenAI) ==")
    values |= ask_model(question, current)

    if env_file.exists():
        shutil.copy2(env_file, Path(f"{env_file}.bak"))
    env_file.write_text(set_keys(env_file.read_text() if env_file.exists() else "", values))
    env_file.chmod(0o600)
    write(f"\nzapisane: {env_file}")

    if ask("Sprawdzić model (jedno wywołanie structured output)? [y/N] ").strip().lower() == "y":
        _try_model(Settings())
    if ask("Wysłać wiadomość testową na każdy kanał? [y/N] ").strip().lower() == "y":
        for key, url in values.items():
            if key.startswith("DISCORD_WEBHOOK_") and url:
                discord.post(url, discord.status_message([f"{key}: działa."], title="suwinvtools · init"))
                write(f"  {key}: wysłane")
    write("\nDalej: `just secrets backup` (kopia .env w Bitwardenie); dla klastra — setup.sh w suwalski-platform.")
    return 0


def _try_model(settings: Settings) -> None:
    document = Document(id="d1", title="test", url="", text="Azure and other cloud services revenue increased 39% this quarter.")
    try:
        claim = litellm_extractor(settings)(GrowthClaim, "State the year-over-year growth of Azure.", [document])
    except LlmError as exc:
        write(f"  model nie odpowiedział schematem: {exc}")
        return
    write(f"  model odpowiedział: {claim.model_dump_json()}")
