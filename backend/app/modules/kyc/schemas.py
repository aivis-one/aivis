# =============================================================================
# AIVIS.ONE Backend -- KYC Schemas (Sprint 2.1, H10, H12)
# =============================================================================
#
# Pydantic models for KYC endpoints.
#
# KYCSubmitResponse:    returned after POST /kyc/submit
# KYCStatusResponse:    returned by GET /kyc/status
# KYCDocumentResponse:  one stored document, for the staff panel
# KYCDocumentURLResponse: a presigned link and how long it lives
# VerificationModeResponse / VerificationModeUpdate: the staff switch
#
# The webhook payload schema is gone with the webhook itself (H10 P-44).
#
# NO STORAGE KEY LEAVES THE BACKEND. KYCDocumentResponse carries an id,
# a kind and a size; staff fetch the object through the presign
# endpoint, which is also what writes the audit row. Handing the key to
# the client would put the one identifier that reaches MinIO into a
# browser, and would let a screen render a document without the read
# ever being recorded.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.kyc.constants import VerificationMode


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


class KYCDocumentResponse(BaseModel):
    """One stored identity document, as the staff panel sees it."""

    id: UUID
    kind: str
    content_type: str
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class KYCDocumentURLResponse(BaseModel):
    """A short-lived link to one document, and how short.

    ttl_seconds is returned rather than assumed by the client: the
    screen has to be able to say when the link stops working, and a
    number the frontend hardcodes is a number that drifts from the
    backend's the first time the TTL is tuned.
    """

    url: str
    ttl_seconds: int


class VerificationModeResponse(BaseModel):
    """The platform's current verification mode."""

    mode: VerificationMode


class VerificationModeUpdate(BaseModel):
    """Request body for changing the verification mode.

    Bound to the enum, so a value outside the vocabulary is refused by
    FastAPI with a 422 before any service or the database sees it.
    """

    mode: VerificationMode
