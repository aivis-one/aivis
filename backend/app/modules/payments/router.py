# =============================================================================
# AIVIS.ONE Backend -- Payment Router (Sprint 5.2, fix Sprint 6.1)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/payments/invoices             -- open a deposit invoice
#   GET  /api/v1/payments/invoices/current     -- the open invoice, if any
#   GET  /api/v1/payments/invoices/{id}        -- one invoice, refreshed
#   POST /api/v1/payments/invoices/{id}/txid   -- submit a transaction hash
#   GET  /api/v1/payments/history              -- payment history (investor)
#   POST /api/v1/payments/webhook              -- inbound event from the
#                                                 payments service (H8)
#
# AUTH:
#   Every USER-FACING endpoint requires authentication. Invoice creation
#   is blocked in avatar mode (R49, forbid_avatar) -- see create_invoice
#   below.
#
#   POST /webhook is the exception and is not a user-facing endpoint at
#   all: its caller is the payments service. It authenticates with the
#   shared X-Payments-Secret header and declares no user dependency,
#   because there is no user in that request to resolve.
#
# ROUTE ORDER MATTERS HERE: /invoices/current is declared BEFORE
# /invoices/{invoice_id}. FastAPI matches in declaration order, and the
# reverse order would send every request for "current" into the
# parameterised route, where it fails UUID parsing as a 422 -- a working
# endpoint made unreachable by a line's position.
#
# Sprint 6.1 FIX (TD-029), still load-bearing:
#   the write-session endpoints use get_current_user_write (not
#   get_current_user) so auth dependency and endpoint share the same
#   write session. FastAPI caches Depends within a request -- one DB
#   connection, no merge.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.payments.schemas import (
    CreateInvoiceRequest,
    InvoiceResponse,
    PaymentHistoryResponse,
    PaymentResponse,
    SubmitTxidRequest,
    TxidResultResponse,
    WebhookEventRequest,
)
from app.modules.payments.service import (
    current_invoice,
    list_payments,
    open_invoice,
    read_invoice,
    submit_invoice_txid,
)
from app.modules.payments.webhook import (
    process_webhook_event,
    verify_payments_secret,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.post(
    "/invoices",
    response_model=InvoiceResponse,
    # R49: the user-facing payment-creation surface -- staff in avatar
    # mode must not initiate deposits for the user.
    #
    # INHERITED FROM POST /crypto-address, WHICH THIS REPLACES. That
    # route was the only carrier of this guard for deposits; removing it
    # without moving the guard would have left the tree with no
    # crypto-address endpoint and no avatar protection either, and only
    # the first half of that is visible in a diff.
    dependencies=[Depends(forbid_avatar("create_payment"))],
)
async def create_invoice(
    body: CreateInvoiceRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """Open a deposit invoice, or return the one already open.

    Not idempotent at the service, narrowed to near-idempotent here:
    see open_invoice() on what that narrowing covers and what it does
    not.
    """
    return await open_invoice(user.id, body.network, body.amount_cents, session)


@router.get(
    "/invoices/current",
    response_model=InvoiceResponse | None,
)
async def get_current_invoice(
    network: str = Query(..., min_length=1, max_length=32),
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse | None:
    """The user's open invoice on this network, or nothing.

    A WRITE SESSION FOR WHAT LOOKS LIKE A READ. Answering this requires
    asking the service, and the answer refreshes the cached status --
    including resolving a row cached as `created` into `expired`. A
    reader session would discard that and the next call would ask again.
    """
    return await current_invoice(user.id, network, session)


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse,
)
async def get_invoice(
    invoice_id: UUID,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> InvoiceResponse:
    """One invoice as the payments service currently sees it.

    An invoice belonging to somebody else answers 404, not 403: see
    _load_owned() on why the ownership test is a WHERE clause.
    """
    return await read_invoice(invoice_id, user.id, session)


@router.post(
    "/invoices/{invoice_id}/txid",
    response_model=TxidResultResponse,
    # Same guard and same reason as invoice creation: submitting a hash
    # is how a deposit is claimed, and staff in avatar mode must not do
    # it on somebody's behalf.
    dependencies=[Depends(forbid_avatar("create_payment"))],
)
async def submit_txid(
    invoice_id: UUID,
    body: SubmitTxidRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> TxidResultResponse:
    """Hand one transaction hash to the payments service.

    A 200 here is not a success: result_code carries the verdict, and
    invalid_format among others arrives with it.
    """
    return await submit_invoice_txid(invoice_id, user.id, body.txid, session)


@router.get(
    "/history",
    response_model=PaymentHistoryResponse,
)
async def get_payment_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> PaymentHistoryResponse:
    """List payment history for the authenticated user."""
    payments, total = await list_payments(
        user.id,
        session,
        page=page,
        per_page=per_page,
    )
    return PaymentHistoryResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        per_page=per_page,
    )


# =============================================================================
# Inbound: the payments service delivering an event (H8)
# =============================================================================
#
# THE ONE ENDPOINT ON THIS ROUTER WITH NO USER BEHIND IT. Its caller is
# the payments service, not a browser, so it declares neither
# get_current_user* nor forbid_avatar -- there is no session to read and
# no avatar to forbid. Authentication is the shared secret in
# X-Payments-Secret, checked by verify_payments_secret.
#
# The router itself carries no dependencies=[...] (see its declaration
# above), so this is a change of one endpoint's own guards rather than a
# hole opened in a router-wide one -- and no second router is needed.
@router.post(
    "/webhook",
    status_code=200,
    dependencies=[Depends(verify_payments_secret)],
)
async def receive_payments_event(
    body: WebhookEventRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Accept one event from the payments service.

    ALWAYS 200 ON A BODY THAT COULD BE ACTED ON, INCLUDING THE CASES
    WHERE NOTHING HAPPENED. A non-2xx makes the service retry, and after
    WEBHOOK_MAX_ATTEMPTS its outbox row goes `failed` with no resend
    command to undo it -- so answering non-2xx to a duplicate delivery,
    or to an event for an invoice this product never recorded, would
    burn a real payment's delivery budget over something no retry could
    ever fix.

    The refusals that DO answer 4xx are raised below this line, in
    process_webhook_event and verify_payments_secret, and each is a body
    this receiver cannot honour rather than a state it merely dislikes.

    `outcome` is echoed for the service's logs and for tests; the
    service does not branch on it.
    """
    outcome = await process_webhook_event(body, session)
    return {"outcome": outcome.value if outcome is not None else "duplicate"}
