# =============================================================================
# AIVIS.ONE Backend -- Consistency Semaphore Schemas (Sprint 6.4)
# =============================================================================
#
# SCHEMAS:
#   SemaphoreResult     -- result of one semaphore check
#   ConsistencyResponse -- aggregated results from all semaphores
# =============================================================================

from typing import Any

from pydantic import BaseModel


class SemaphoreResult(BaseModel):
    """Result of a single consistency semaphore check."""

    name: str
    status: str  # "pass" | "fail"
    severity: str  # "critical" | "high"
    details: dict[str, Any] | None = None


class ConsistencyResponse(BaseModel):
    """GET /api/v1/staff/consistency -- all semaphore results."""

    overall_status: str  # "pass" | "fail"
    total: int
    passed: int
    failed: int
    results: list[SemaphoreResult]
