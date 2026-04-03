# =============================================================================
# CBSHOME Backend -- KYC Schemas (Sprint 2.1)
# =============================================================================
#
# Pydantic models for KYC endpoints.
#
# KYCSubmitResponse:  returned after POST /kyc/submit
# KYCStatusResponse:  returned by GET /kyc/status
# KYCWebhookRequest:  incoming webhook payload (stub)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KYCSubmitResponse(BaseModel):
    """Response after submitting a KYC application."""

    id: UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class KYCStatusResponse(BaseModel):
    """Current KYC status for the authenticated user."""

    kyc_status: str
    application_id: UUID | None = None
    application_status: str | None = None


class KYCWebhookRequest(BaseModel):
    """Webhook payload from KYC provider (stub).

    In production, this will be replaced with SumSub webhook format
    and signature validation. Current stub accepts user_id + status.
    """

    user_id: UUID
    status: str = Field(
        ...,
        pattern="^(approved|rejected)$",
        description="New KYC status: approved or rejected",
    )
