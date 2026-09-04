# =============================================================================
# AIVIS.ONE Backend -- KYC Schemas (Sprint 2.1, H10)
# =============================================================================
#
# Pydantic models for KYC endpoints.
#
# KYCSubmitResponse:  returned after POST /kyc/submit
# KYCStatusResponse:  returned by GET /kyc/status
#
# The webhook payload schema is gone with the webhook itself (H10 P-44).
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class KYCSubmitResponse(BaseModel):
    """Response after opening (and paying for) a verification session."""

    id: UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class KYCStatusResponse(BaseModel):
    """Current KYC status for the authenticated user.

    Carries the money as well as the status. This endpoint is in front
    of the gate and dashboard/summary -- the usual source of a balance
    -- is behind it, so without these two fields the screen that asks
    for ten dollars could not say how much the account actually holds.
    """

    kyc_status: str
    application_id: UUID | None = None
    application_status: str | None = None
    fee_cents: int
    available_cents: int
