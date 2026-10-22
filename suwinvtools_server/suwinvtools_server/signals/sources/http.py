import urllib.error
import urllib.request
from collections.abc import Callable
from typing import cast

# A body for a URL. The default goes to the network; the tests pass recorded answers.
type Fetch = Callable[[str], bytes]

USER_AGENT = "suwinvtools-signals/0.1 (homelab; monthly)"


class SourceError(RuntimeError):
    """An outside service did not answer."""


class SourceChangedError(SourceError):
    """An outside service answered in a shape this code does not know — the reading is not trusted."""


def http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})  # noqa: S310 — https URLs built in sources/
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 — same
            return cast(bytes, response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SourceError(f"{url}: {exc}") from exc
