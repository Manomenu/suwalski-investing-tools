"""News headlines from Google News RSS — for the signals no filing carries (lab revenue,
funding rounds, IPOs, cancelled capacity).

Only what the feed itself says is used: title, outlet and the short description. The article
links are Google redirects, and many outlets sit behind a paywall anyway, so a quote the
language model returns must come from these words. The feed's terms allow personal,
non-commercial use, which is what a homelab notifier is.
"""

import re
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from suwinvtools_library.marketdata.edgar import html_to_text
from suwinvtools_server.signals.sources.http import SourceChangedError

SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


@dataclass(frozen=True)
class Headline:
    id: str  # what the language model cites: "n1", "n2", …
    title: str
    outlet: str
    outlet_url: str
    link: str
    published: datetime
    description: str

    @property
    def text(self) -> str:
        return f"{self.title}. {self.description}".strip()

    @property
    def domain(self) -> str:
        """The outlet's domain — what "two independent sources" counts."""
        host = urllib.parse.urlparse(self.outlet_url).hostname or self.outlet
        return re.sub(r"^www\.", "", host.lower())


def search_url(query: str, *, days: int = 35) -> str:
    return SEARCH_URL.format(query=urllib.parse.quote(f"{query} when:{days}d"))


def headlines(feed: bytes, *, prefix: str = "n") -> list[Headline]:
    try:
        root = ElementTree.fromstring(feed)  # noqa: S314 — Google's feed, parsed without entity expansion by default
    except ElementTree.ParseError as exc:
        raise SourceChangedError("Google News answered something other than RSS") from exc
    channel = root.find("channel")
    if channel is None:
        raise SourceChangedError("Google News RSS without a channel")
    found: list[Headline] = []
    for index, item in enumerate(channel.findall("item"), start=1):
        source = item.find("source")
        raw_date = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(raw_date)
        except (TypeError, ValueError):
            published = datetime.now(UTC)
        title = (item.findtext("title") or "").strip()
        outlet = (source.text or "").strip() if source is not None else ""
        # Google appends " - Outlet" to every title; the outlet is its own field.
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3]
        found.append(
            Headline(
                id=f"{prefix}{index}",
                title=title,
                outlet=outlet,
                outlet_url=source.get("url", "") if source is not None else "",
                link=(item.findtext("link") or "").strip(),
                published=published,
                description=_description(item.findtext("description") or "", title, outlet),
            )
        )
    return found


def _description(raw: str, title: str, outlet: str) -> str:
    """The description is HTML that mostly repeats the title and the outlet; keep what is new."""
    text = html_to_text(raw).replace("\n", " ")
    for repeated in (title, outlet):
        text = text.replace(repeated, " ")
    return re.sub(r"\s+", " ", text).strip()
