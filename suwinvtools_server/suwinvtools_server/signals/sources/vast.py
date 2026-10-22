"""GPU rental prices from vast.ai's public offer search (no key needed).

vast.ai is a marketplace of smaller hosts and spot prices — a sample of what an hour of a
GPU costs, not the neoclouds' contract prices. Variants of one generation (SXM, NVL, PCIe)
are pooled, because each alone has only a handful of offers.
"""

import json
import statistics
import urllib.parse
from dataclasses import dataclass
from typing import cast

from suwinvtools_server.signals.sources.http import Fetch, SourceChangedError

OFFERS_URL = "https://console.vast.ai/api/v0/bundles/?q={query}"

# Generation -> the gpu_name values vast.ai uses for it.
FAMILIES: dict[str, tuple[str, ...]] = {
    "H100": ("H100 SXM", "H100 NVL", "H100 PCIE"),
    "H200": ("H200", "H200 NVL"),
    "B200": ("B200",),
}


@dataclass(frozen=True)
class GpuPrice:
    family: str
    median: float  # USD per GPU-hour
    p25: float
    offers: int


def offers_url(gpu_name: str) -> str:
    query = {"gpu_name": {"eq": gpu_name}, "rentable": {"eq": True}, "limit": 1000}
    return OFFERS_URL.format(query=urllib.parse.quote(json.dumps(query)))


def per_gpu_prices(body: bytes) -> list[float]:
    """USD per GPU-hour of every offer in one answer."""
    try:
        parsed: object = json.loads(body)
    except ValueError as exc:
        raise SourceChangedError("vast.ai answered something other than JSON") from exc
    offers = cast(dict[str, object], parsed).get("offers") if isinstance(parsed, dict) else None
    if not isinstance(offers, list):
        raise SourceChangedError("vast.ai answer has no 'offers' list")
    prices: list[float] = []
    for offer in cast(list[object], offers):
        fields = cast(dict[str, object], offer) if isinstance(offer, dict) else {}
        total, gpus = fields.get("dph_total"), fields.get("num_gpus")
        if not isinstance(total, int | float) or not isinstance(gpus, int) or gpus <= 0:
            raise SourceChangedError("vast.ai offer without dph_total / num_gpus")
        prices.append(float(total) / gpus)
    return prices


def family_price(family: str, fetch: Fetch) -> GpuPrice | None:
    """The pooled price of one generation, or None when nobody offers it."""
    prices = [price for name in FAMILIES[family] for price in per_gpu_prices(fetch(offers_url(name)))]
    if not prices:
        return None
    quartiles = statistics.quantiles(prices, n=4) if len(prices) > 1 else [prices[0]] * 3
    return GpuPrice(family=family, median=statistics.median(prices), p25=quartiles[0], offers=len(prices))
