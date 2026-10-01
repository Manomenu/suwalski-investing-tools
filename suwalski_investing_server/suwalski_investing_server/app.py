from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from suwalski_investing_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwalski_investing_library.valuation.errors import ValuationError

from suwalski_investing_server.market.router import router as market_router
from suwalski_investing_server.mcp.server import mcp
from suwalski_investing_server.settings import settings
from suwalski_investing_server.valuation.router import router as valuation_router

# Built before the app: the session manager it creates is what the lifespan has to run.
# The host decides DNS-rebinding protection — on 0.0.0.0 the SDK leaves it off, which is
# what lets the cluster's own hostname through.
mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True, host=settings.host)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="suwalski-investing-tools", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValuationError)
def valuation_error_handler(request: Request, exc: ValuationError) -> JSONResponse:
    # The inputs parsed fine, the model just can't answer — same class of problem as a
    # validation error to the caller, so it gets the same status code.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(UnknownTickerError)
def unknown_ticker_handler(request: Request, exc: UnknownTickerError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(MarketDataError)
def market_data_error_handler(request: Request, exc: MarketDataError) -> JSONResponse:
    # The provider is upstream of us and unofficial — a failure there is not the caller's fault.
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(valuation_router)
app.include_router(market_router)
# Last, and at the root: the MCP app serves only /mcp itself, and a mount is a catch-all,
# so anything registered after it would never be reached.
app.mount("/", mcp_app)
