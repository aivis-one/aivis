# =============================================================================
# AIVIS.ONE Backend -- Transaction Router (Sprint 6.4, Sprint 10.1, TASK-39)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/transactions        -- paginated event log with filters
#   GET /api/v1/transactions/export -- CSV statement export (TASK-39 item 2,
#                                       replaces the Sprint 10.1 501 stub)
#   GET /api/v1/transactions/{id}   -- single event details
#
# AUTH:
#   All endpoints require authenticated user. Each user sees only
#   their own transactions (user_id guard in service layer).
#
# FILTERS (query params, shared by the list AND export endpoints):
#   type       -- exact match or prefix with ":" (e.g. "withdrawal:")
#   date_from  -- inclusive lower bound (ISO 8601)
#   date_to    -- inclusive upper bound (ISO 8601)
#   amount_min -- minimum absolute amount_cents
#   amount_max -- maximum absolute amount_cents
#
# EXPORT (TASK-39 item 2):
#   Format is CSV -- the honest minimum a "statement export" needs, no
#   new dependency. Reuses list_transactions() (transactions/service.py)
#   with the exact same filters as the list endpoint above, so a
#   downloaded statement matches whatever the screen showed. Row cap,
#   column choice, and the formula-injection guard are documented on
#   export_transactions_csv() / _sanitize_csv_cell() in service.py --
#   not repeated here.
#
#   RATE LIMIT: check_rate_limit(f"transactions_export:{user.id}") is
#   called with NO max_requests/window_seconds override, so the actual
#   CAP is the SHARED default (settings.auth_rate_limit_max_requests /
#   settings.auth_rate_limit_window_seconds -- 5 requests per 60s out of
#   the box). Keyed by user.id, not IP, matching the totp_setup /
#   totp_confirm / totp_disable precedent in auth/router.py. The call
#   DOES override error_message (only that kwarg) -- purely cosmetic,
#   the default auth-flow wording ("Too many auth attempts...") reads
#   oddly for a CSV download; the numeric cap is untouched by this.
#
#   AVATAR GUARD: deliberately NOT applied. This is a read of the exact
#   same rows GET /transactions and GET /transactions/{id} already
#   expose to an avatar session with no forbid_avatar dependency on
#   either -- avatar_guard.py's own header calls that category
#   ("financials") already-granted read-only visibility, same class as
#   the unguarded GET /sessions and GET /preferences it cites as
#   precedent. RESTRICTED_OPERATIONS's "persists past the avatar
#   session" test (used to justify guarding logout_all/revoke_session/
#   mute_notifications/manage_2fa) targets a MUTATION with an ongoing
#   server-side effect on the platform -- a downloaded CSV is not a
#   platform-state change, it is the same already-readable data leaving
#   in a different, bulkier format. See the avatar_guard.py header
#   itself for the full reasoning this leans on.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). Read-only endpoints use
#   get_db_reader for replica routing.
# =============================================================================

from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.rate_limit import check_rate_limit
from app.modules.auth.dependencies import get_current_user
from app.modules.transactions.schemas import (
    TransactionListResponse,
    TransactionResponse,
)
from app.modules.transactions.service import (
    export_transactions_csv,
    get_transaction,
    list_transactions,
)
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
# Export (TASK-39 item 2) -- must stay BEFORE /{transaction_id}, or FastAPI
# matches "export" as a UUID path parameter and this route never fires.
# ---------------------------------------------------------------------------


@router.get("/export", response_model=None)
async def export_transactions(
    type: str | None = Query(None, alias="type"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    amount_min: int | None = Query(None, ge=0),
    amount_max: int | None = Query(None, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Response:
    """Export the authenticated user's transaction history as CSV.

    Same filters as GET /api/v1/transactions above (no page/per_page --
    an export is not paginated, see EXPORT_MAX_ROWS in
    transactions/constants.py for the row cap and its boundary
    behaviour). Rate limit and avatar-guard reasoning are documented in
    this file's header, not repeated per-endpoint.
    """
    await check_rate_limit(
        f"transactions_export:{user.id}",
        error_message="Too many export requests. Please try again shortly.",
    )

    csv_text = await export_transactions_csv(
        user.id,
        session,
        type_filter=type,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
    )

    filename = f"transactions_export_{datetime.now(UTC):%Y%m%d_%H%M%S}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
