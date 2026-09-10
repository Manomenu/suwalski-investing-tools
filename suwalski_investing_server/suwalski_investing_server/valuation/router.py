from fastapi import APIRouter
from suwalski_investing_library.contracts.valuation import ReverseDcfRequest, ReverseDcfResult
from suwalski_investing_library.valuation.reverse import solve_implied_growth

router = APIRouter(prefix="/valuation", tags=["valuation"])


# Plain `def`: the projection is pure CPU work (microseconds), so FastAPI's threadpool
# keeps it off the event loop without any async plumbing.
@router.post("/reverse-dcf", response_model=ReverseDcfResult)
def reverse_dcf(request: ReverseDcfRequest) -> ReverseDcfResult:
    """Solve the growth today's price demands from the years you left open."""
    return solve_implied_growth(request)
