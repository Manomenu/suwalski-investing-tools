"""Token prices and volumes from OpenRouter — a sample of the market, skewed to developers.

Prices come from the public models API. Volumes are not in any API: the rankings page embeds
the previous day's top models with their prompt and completion tokens, and this reads that.
It is scraping, so the parser fails loudly (SourceChangedError) rather than guessing.
"""

import json
import re
from dataclasses import dataclass
from typing import cast

from suwinvtools_server.signals.sources.http import SourceChangedError

MODELS_URL = "https://openrouter.ai/api/v1/models"
RANKINGS_URL = "https://openrouter.ai/rankings"

_USAGE = re.compile(
    r'\{"date":"(?P<date>\d{4}-\d{2}-\d{2})[^"]*","model_permaslug":"(?P<model>[^"]+)","variant":"[^"]*",'
    r'"total_completion_tokens":(?P<completion>\d+),"total_prompt_tokens":(?P<prompt>\d+)'
)


@dataclass(frozen=True)
class ModelUsage:
    day: str
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Price:
    prompt: float  # USD per token
    completion: float


@dataclass(frozen=True)
class TokenMarket:
    day: str
    tokens: float  # all tokens of the top models that day
    spend: float  # what those tokens cost at list prices, USD
    priced_share: float  # share of the tokens whose model had a price (free models count as 0 USD)
    models: int


def usage_from_rankings(page: bytes) -> list[ModelUsage]:
    text = page.decode("utf-8", errors="replace").replace('\\"', '"')
    rows = [
        ModelUsage(day=match["date"], model=match["model"], prompt_tokens=int(match["prompt"]), completion_tokens=int(match["completion"]))
        for match in _USAGE.finditer(text)
    ]
    if not rows:
        raise SourceChangedError("the OpenRouter rankings page no longer embeds per-model token counts")
    latest = max(row.day for row in rows)
    return [row for row in rows if row.day == latest]


def prices_from_models(body: bytes) -> dict[str, Price]:
    """Prices by canonical slug (what the rankings call a model) and by id."""
    try:
        parsed: object = json.loads(body)
    except ValueError as exc:
        raise SourceChangedError("OpenRouter models API answered something other than JSON") from exc
    data = cast(dict[str, object], parsed).get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, list):
        raise SourceChangedError("OpenRouter models API answer has no 'data' list")
    prices: dict[str, Price] = {}
    for item in cast(list[object], data):
        model = cast(dict[str, object], item) if isinstance(item, dict) else {}
        pricing = cast(dict[str, object], model.get("pricing", {}))
        try:
            price = Price(prompt=float(str(pricing.get("prompt", "0"))), completion=float(str(pricing.get("completion", "0"))))
        except ValueError:
            continue  # "-1" style placeholders for routers; not a price
        for key in (model.get("canonical_slug"), model.get("id")):
            if isinstance(key, str):
                prices.setdefault(key, price)
    return prices


def token_market(usage: list[ModelUsage], prices: dict[str, Price]) -> TokenMarket:
    tokens = spend = priced = 0.0
    for row in usage:
        volume = row.prompt_tokens + row.completion_tokens
        tokens += volume
        price = prices.get(row.model)
        if price is None:
            continue
        priced += volume
        spend += row.prompt_tokens * max(price.prompt, 0.0) + row.completion_tokens * max(price.completion, 0.0)
    return TokenMarket(day=usage[0].day, tokens=tokens, spend=spend, priced_share=priced / tokens if tokens else 0.0, models=len(usage))
