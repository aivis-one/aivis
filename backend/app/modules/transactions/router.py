# =============================================================================
# CBSHOME Backend -- Transaction Router (Sprint 6.4, Sprint 10.1)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/transactions        -- paginated event log with filters
#   GET /api/v1/transactions/export -- stub (501 Not Implemented) Sprint 10.1
#   GET /api/v1/transactions/{id}   -- single event details
#
# AUTH:
#   All endpoints require authenticated user. Each user sees only
#   their own transactions (user_id guard in service layer).
#
# FILTERS (query params):
#   type       -- exact match or prefix with ":" (e.g. "withdrawal:")
#   date_from  -- inclusive lower bound (ISO 8601)
#   date_to    -- inclusive upper bound (ISO 8601)
#   amount_min -- minimum absolute amount_cents
#   amount_max -- maximum absolute amount_cents
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). Read-only endpoints use
#   get_db_reader for replica routing.
# =============================================================================

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.auth.dependencies import get_current_user
from app.modules.transactions.schemas import (
    TransactionListResponse,
    TransactionResponse,
)
from app.modules.transactions.service import get_transaction, list_transactions
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get(
    "",
    response_model=TransactionListResponse,
)
async def list_user_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    type: str | None = Query(None, alias="type"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    amount_min: int | None = Query(None, ge=0),
    amount_max: int | None = Query(None, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> TransactionListResponse:
    """List authenticated user's transaction event log with filters."""
    items, total = await list_transactions(
        user.id,
        session,
        page=page,
        per_page=per_page,
        type_filter=type,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
    )
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# Export stub (Sprint 10.1) -- must be BEFORE /{transaction_id} to avoid
# FastAPI matching "export" as a UUID path parameter.
# ---------------------------------------------------------------------------


@router.get("/export", response_model=None)
async def export_transactions(
    user: User = Depends(get_current_user),
) -> None:
    """Export transaction history as CSV/XLSX (stub).

    Not implemented in MVP. See TD-009 for Phase 2 implementation.
    """
    raise HTTPException(status_code=501, detail="Not Implemented")


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse,
)
async def get_user_transaction(
    transaction_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> TransactionResponse:
    """Get a single transaction event by ID (user ownership enforced)."""
    txn = await get_transaction(transaction_id, user.id, session)
    return TransactionResponse.model_validate(txn)
