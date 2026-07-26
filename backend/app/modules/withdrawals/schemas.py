# =============================================================================
# AIVIS.ONE Backend -- Withdrawal Schemas (Sprint 6.3)
# =============================================================================
#
# SCHEMAS:
#   CreateWithdrawalRequest -- amount_cents for withdrawal
#   RejectWithdrawalRequest -- rejection_reason (required)
#   WithdrawalResponse      -- single withdrawal representation
#   WithdrawalListResponse  -- paginated list
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateWithdrawalRequest(BaseModel):
    """POST /api/v1/withdrawals -- request a withdrawal."""

    amount_cents: int = Field(..., gt=0)


class RejectWithdrawalRequest(BaseModel):
    """POST /api/v1/staff/withdrawals/{id}/reject -- reject with reason."""

    reason: str = Field(..., min_length=1, max_length=2000)


class WithdrawalResponse(BaseModel):
    """Single withdrawal in API responses."""

    id: UUID
    user_id: UUID
    amount_cents: int
    status: str
    payout_details_snapshot: dict[str, Any]
    rejection_reason: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    processing_at: datetime | None = None
    completed_at: datetime | None = None
    rejected_at: datetime | None = None
    failed_at: datetime | None = None

    model_config = {"from_attributes": True}


class WithdrawalListResponse(BaseModel):
    """GET /api/v1/withdrawals/me -- paginated list."""

    items: list[WithdrawalResponse]
    total: int
