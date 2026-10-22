"""Every check the job runs, in the order the board shows them."""

from suwinvtools_server.signals.checks.base import Check
from suwinvtools_server.signals.checks.capital import CapitalVsValuation
from suwinvtools_server.signals.checks.funding import ComputeCuts, LabFunding, LabIpo
from suwinvtools_server.signals.checks.hardware import ComputeImpairment, DepreciationLife, GpuRentalPrices, NeocloudBacklog
from suwinvtools_server.signals.checks.jevons import HyperscalerTokens, TokenSpend
from suwinvtools_server.signals.checks.monetization import CloudVsCapex, LabRevenueStall

ALL_CHECKS: tuple[Check, ...] = (
    CloudVsCapex(),
    LabRevenueStall(),
    DepreciationLife(),
    ComputeImpairment(),
    NeocloudBacklog(),
    GpuRentalPrices(),
    TokenSpend(),
    HyperscalerTokens(),
    LabFunding(),
    LabIpo(),
    ComputeCuts(),
    CapitalVsValuation(),
)


def by_id(check_id: str) -> Check | None:
    return next((check for check in ALL_CHECKS if check.meta.id == check_id.upper()), None)
