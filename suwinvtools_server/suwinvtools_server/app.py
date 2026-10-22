import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from suwinvtools_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwinvtools_library.valuation.errors import ValuationError

from suwinvtools_server import db
from suwinvtools_server.market.api import router as market_router
from suwinvtools_server.mcp.server import mcp
from suwinvtools_server.settings import settings
from suwinvtools_server.signals.api import router as signals_router
from suwinvtools_server.valuation.api import router as valuation_router

# Routes are declared without an /api prefix. The prefix belongs to the edge — the vite
# proxy in development, nginx in the image — which strips it before the request lands here.
# uvicorn configures its own logger, so messages here show up next to its startup lines.
log = logging.getLogger("uvicorn.error")

# Built before the app: the session manager it creates is what the lifespan has to run.
# The host decides DNS-rebinding protection — on 0.0.0.0 the SDK leaves it off, which is
# what lets the cluster's own hostname through.
mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True, host=settings.host)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Without the database there is nothing to serve, so the server fails to start with a
    # clear error rather than failing every request later.
    db.pool.open(wait=True, timeout=10)
    with db.pool.connection() as conn:
        for name in db.migrate(conn):
            log.info("applied migration %s", name)
    async with mcp.session_manager.run():
        yield
    db.pool.close()


app = FastAPI(title="suwinvtools", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValuationError)
def valuation_error_handler(_request: Request, exc: ValuationError) -> JSONResponse:
    # The inputs parsed fine, the model just can't answer — same class of problem as a
    # validation error to the caller, so it gets the same status code.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(UnknownTickerError)
def unknown_ticker_handler(_request: Request, exc: UnknownTickerError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(MarketDataError)
def market_data_error_handler(_request: Request, exc: MarketDataError) -> JSONResponse:
    # The provider is upstream of us and unofficial — a failure there is not the caller's fault.
    return JSONResponse(status_code=502, content={"detail": str(exc)})


class Health(BaseModel):
    status: str


# Touches nothing outside the process, so it doubles as the cluster's liveness probe.
@app.get("/health")
def health() -> Health:
    return Health(status="ok")


app.include_router(valuation_router)
app.include_router(market_router)
app.include_router(signals_router)
# Last, and at the root: the MCP app serves only /mcp itself, and a mount is a catch-all,
# so anything registered after it would never be reached.
app.mount("/", mcp_app)
