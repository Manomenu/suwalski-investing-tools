from fastapi import APIRouter, Query
from suwalski_investing_library.contracts.market import TickerSnapshot
from suwalski_investing_library.marketdata.provider import get_snapshot

from suwalski_investing_server.settings import settings

router = APIRouter(prefix="/market", tags=["market"])


# Plain `def`: the provider does blocking HTTP and disk I/O, so FastAPI runs it on the
# threadpool instead of stalling the event loop.
@router.get("/{ticker}", response_model=TickerSnapshot)
def snapshot(ticker: str, refresh: bool = Query(default=False, description="skip the cache")) -> TickerSnapshot:
    """Observable facts for a symbol — price, shares, TTM revenue and FCF, net debt.

    The dashboard calls this to prefill the form; the assumptions stay with the user.
    """
    return get_snapshot(ticker, ttl_seconds=settings.market_cache_ttl_seconds, refresh=refresh)
