# =============================================================================
# CBSHOME Backend -- Transaction Schemas (Sprint 6.4)
# =============================================================================
#
# SCHEMAS:
#   TransactionResponse     -- single event in API responses
#   TransactionListResponse -- paginated list with filters applied
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TransactionResponse(BaseModel):
    """Single transaction event in API responses."""

    id: UUID
    user_id: UUID
    type: str
    amount_cents: int
    currency: str
    reference_id: UUID | None = None
    reference_type: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    """GET /api/v1/transactions -- paginated event log."""

    items: list[TransactionResponse]
    total: int
    page: int
    per_page: int
