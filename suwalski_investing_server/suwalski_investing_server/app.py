from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from suwalski_investing_library.marketdata.errors import MarketDataError, UnknownTickerError
from suwalski_investing_library.valuation.errors import ValuationError

from suwalski_investing_server.market.router import router as market_router
from suwalski_investing_server.settings import settings
from suwalski_investing_server.valuation.router import router as valuation_router

app = FastAPI(title="suwalski-investing-tools", version="0.1.0")

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
