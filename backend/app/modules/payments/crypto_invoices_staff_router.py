# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices staff router
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/staff/crypto-invoices               -- list (administrator)
#   POST /api/v1/staff/crypto-invoices/{id}/confirm  -- credit by hand
#   POST /api/v1/staff/crypto-invoices/{id}/notes    -- an administrator's note
#
# PERMISSIONS:
#   financial_operations, plus the administrator mark checked inside each
#   endpoint (a member without every permission is refused with 403).
#
# COMMIT RULE (P-01): routers never commit; get_db_session does.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.payments.manual_confirm import (
    confirm_crypto_invoice,
    list_crypto_invoices,
)
from app.modules.payments.manual_requests import add_note
from app.modules.payments.schemas import (
    AddInvoiceNoteRequest,
    ConfirmCryptoInvoiceRequest,
    ConfirmCryptoInvoiceResponse,
    StaffCryptoInvoiceListResponse,
    StaffInvoiceNote,
)
from app.modules.staff.permissions import require_admin
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/crypto-invoices", tags=["staff-crypto-invoices"]
)


@router.get("", response_model=StaffCryptoInvoiceListResponse)
async def list_crypto_invoices_endpoint(
    user_id: UUID | None = Query(default=None),
    invoice_status: str | None = Query(
        default=None,
        alias="status",
        max_length=32,
        description="Filter by the cached service status.",
    ),
    open_request: bool = Query(
        default=False,
        description=(
            "Only invoices whose client asked for a manual confirmation "
            "and that are not credited yet."
        ),
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    staff: User = Depends(require_staff_permission("financial_operations")),
    session: AsyncSession = Depends(get_db_reader),
) -> StaffCryptoInvoiceListResponse:
    """List crypto invoices, newest first. Administrator only."""
    await require_admin(staff, session)
    items, total = await list_crypto_invoices(
        session,
        user_id=user_id,
        status=invoice_status,
        open_request=open_request,
        page=page,
        per_page=per_page,
    )
    return StaffCryptoInvoiceListResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@router.post(
    "/{invoice_id}/confirm",
    response_model=ConfirmCryptoInvoiceResponse,
)
async def confirm_crypto_invoice_endpoint(
    invoice_id: UUID,
    body: ConfirmCryptoInvoiceRequest,
    staff: User = Depends(require_staff_permission("financial_operations")),
    session: AsyncSession = Depends(get_db_session),
) -> ConfirmCryptoInvoiceResponse:
    """Credit the invoice's stated amount to its client by hand.

    Administrator only. 409 when the invoice is already credited, by hand
    or by the payments service.
    """
    await require_admin(staff, session)
    payment = await confirm_crypto_invoice(invoice_id, staff.id, body.reason, session)
    return ConfirmCryptoInvoiceResponse(
        invoice_id=invoice_id,
        payment_id=payment.id,
        user_id=payment.user_id,
        amount_cents=payment.amount_cents,
    )


@router.post(
    "/{invoice_id}/notes",
    response_model=StaffInvoiceNote,
)
async def add_crypto_invoice_note_endpoint(
    invoice_id: UUID,
    body: AddInvoiceNoteRequest,
    staff: User = Depends(require_staff_permission("financial_operations")),
    session: AsyncSession = Depends(get_db_session),
) -> StaffInvoiceNote:
    """Write an administrator's note on the invoice, before or after Confirm.

    Administrator only, the same right as the confirmation. Stored as an
    audit event; staff read the notes in the list, a client never does.
    """
    await require_admin(staff, session)
    return await add_note(invoice_id, staff, body.text, session)
