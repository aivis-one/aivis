# =============================================================================
# AIVIS.ONE Backend -- Payment Service (Sprint 5.2, updated Sprint 6.4, G2, H7)
# =============================================================================
#
# RESPONSIBILITIES:
#   open_invoice()      -- write the local row, then ask the service for
#                          an invoice against it
#   read_invoice()      -- refresh one invoice from the service
#   submit_invoice_txid()-- forward one TXID to the service
#   current_invoice()   -- the user's open invoice on a network, if any
#   get_payment()       -- load Payment by id
#   list_payments()     -- paginated history for an investor
#   list_all_payments() -- paginated history for staff (all users, G2)
#
# THE SERVICE DECIDES, THIS MODULE RELAYS. No status machine lives here,
# no attempt budget, no network list, no expiry arithmetic. Every one of
# those is a fact of the payments service, and a copy of any of them
# here would be a second answer to a question that already has one
# (TOR section 11 p.12).
#
# WHY THE ROW IS WRITTEN FIRST. The service has no dedupe on product_ref
# (TOR section 11 p.11): two creating calls make two invoices, and a
# call that times out may have made one we never learn the id of.
# Writing the row before the call means such an invoice is always
# traceable back to a user, and holding the row means the second call is
# not made at all while an invoice is open. That narrows the window; it
# does not close it, and closing it is service-side work (P-23).
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import payments_client
from app.core.exceptions import NotFoundError
from app.modules.payments.models import CryptoInvoice, Payment
from app.modules.payments.schemas import InvoiceResponse, TxidResultResponse

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Payment lookup
# ---------------------------------------------------------------------------


async def get_payment(
    payment_id: UUID,
    session: AsyncSession,
) -> Payment:
    """Load Payment by id.

    Raises:
        NotFoundError: If payment not found.
    """
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()

    if payment is None:
        raise NotFoundError("Payment not found")

    return payment


# ---------------------------------------------------------------------------
# Payment history
# ---------------------------------------------------------------------------


async def list_payments(
    user_id: UUID,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Payment], int]:
    """List payments for a user with pagination.

    Returns (payments, total_count).
    """
    # Count total.
    count_stmt = (
        select(func.count())
        .select_from(Payment)
        .where(Payment.user_id == user_id)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    payments = list(result.scalars().all())

    return payments, total


async def list_all_payments(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
    user_id: UUID | None = None,
) -> tuple[list[Payment], int]:
    """List all payments for staff view with optional filters.

    Args:
        session: Active DB session.
        page: Page number (1-based).
        per_page: Items per page.
        status: Optional status filter (frozen, confirmed, reversed, etc.).
        user_id: Optional user filter.

    Returns:
        (payments, total_count).
    """
    # Build filters.
    filters = []
    if status is not None:
        filters.append(Payment.status == status)
    if user_id is not None:
        filters.append(Payment.user_id == user_id)

    # Count total.
    count_stmt = select(func.count()).select_from(Payment)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(Payment)
        .order_by(Payment.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    if filters:
        stmt = stmt.where(*filters)

    result = await session.execute(stmt)
    payments = list(result.scalars().all())

    return payments, total


# ---------------------------------------------------------------------------
# Deposit invoices
# ---------------------------------------------------------------------------

#: Statuses the service never leaves on its own (TOR section 5).
#:
#: ``attempts_exhausted`` is NOT here, and the omission is the service's
#: rule rather than an oversight: such an invoice accepts no further
#: TXID but is still waiting for its TTL to turn it into ``expired``.
#: Treating it as terminal here would offer the user a new invoice while
#: the old one can still expire underneath them.
_TERMINAL_STATUSES = frozenset({"confirmed", "expired", "stalled"})


def _parse_timestamp(value: Any) -> datetime:
    """Parse one timestamptz the service sent.

    Raises rather than defaulting on anything unparseable. A deposit
    screen shows this as the deadline by which the transfer must be
    made; substituting "now" or None for a value we failed to read
    would put a wrong deadline in front of somebody about to move
    money, and a wrong deadline is worse than a refused screen.
    """
    if not isinstance(value, str):
        raise payments_client.PaymentsMalformedError()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise payments_client.PaymentsMalformedError() from None


def _to_response(
    invoice: CryptoInvoice,
    *,
    remote: dict[str, Any] | None = None,
) -> InvoiceResponse:
    """Render one invoice, preferring the service's answer to the row.

    ``remote`` is what the service just said. When it is present it wins
    every field it carries -- the row is a cache and the caller has the
    truth in hand. When it is absent the row is all there is.

    ``attempts_remaining`` is never filled from the row because the row
    does not hold it and must not: deriving it locally would mean
    hard-coding MAX_TXID_ATTEMPTS, which lives in the service's config
    and is exactly the kind of value TOR section 11 p.12 forbids the
    product to compute.
    """
    if remote is None:
        return InvoiceResponse(
            id=invoice.id,
            network=invoice.network,
            address=invoice.address,
            invoice_amount_cents=invoice.invoice_amount_cents,
            status=invoice.status,
            expires_at=invoice.expires_at,
        )

    return InvoiceResponse(
        id=invoice.id,
        network=remote.get("network") or invoice.network,
        address=remote.get("address") or invoice.address,
        invoice_amount_cents=remote.get("invoice_amount_cents")
        or invoice.invoice_amount_cents,
        status=str(remote["status"]),
        expires_at=invoice.expires_at,
        attempts_remaining=remote.get("attempts_remaining"),
        active_txid=remote.get("active_txid"),
        credited_amount_cents=remote.get("credited_amount_cents"),
        underpaid=remote.get("underpaid"),
    )


def _cache_status(invoice: CryptoInvoice, remote: dict[str, Any]) -> None:
    """Copy the service's status onto the row.

    A CACHE UPDATE AND NOTHING ELSE. No money moves from here, no other
    path reads the result to decide anything -- see the column docstring
    in models.py. It exists so a screen has something to draw when the
    service cannot be reached, and for no other reason.
    """
    status = remote.get("status")
    if isinstance(status, str) and status:
        invoice.status = status


async def _load_owned(
    invoice_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> CryptoInvoice:
    """Load one invoice, scoped to its owner.

    404 RATHER THAN 403 ON SOMEBODY ELSE'S INVOICE, and the ownership
    filter is in the WHERE clause rather than in a check afterwards.
    A 403 would confirm that the id exists, which is the whole prize
    for anyone walking the id space; filtering in SQL means the answer
    to "not yours" and "not a thing" is produced by the same query and
    cannot drift apart.
    """
    stmt = select(CryptoInvoice).where(
        CryptoInvoice.id == invoice_id,
        CryptoInvoice.user_id == user_id,
    )
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()

    if invoice is None:
        raise NotFoundError("Invoice not found")

    return invoice


async def current_invoice(
    user_id: UUID,
    network: str,
    session: AsyncSession,
) -> InvoiceResponse | None:
    """The user's open invoice on this network, refreshed, or None.

    THE ROW ALONE CANNOT ANSWER THIS. A row cached as ``created`` may
    have expired since it was last read: the service resolves expiry
    lazily on read, so its answer is current and ours is merely the last
    thing it said (TOR section 11 p.7). The newest non-terminal
    candidate is therefore re-read from the service before it is called
    open, and a candidate that comes back terminal is cached as such and
    reported as no open invoice.

    Only the newest candidate is checked. Older ones cannot be open
    while a newer exists, because a new invoice is only ever created
    when no open one was found.
    """
    stmt = (
        select(CryptoInvoice)
        .where(
            CryptoInvoice.user_id == user_id,
            CryptoInvoice.network == network,
            CryptoInvoice.status.not_in(_TERMINAL_STATUSES),
        )
        .order_by(CryptoInvoice.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()

    if invoice is None:
        return None

    remote = await payments_client.get_invoice(invoice.service_invoice_id)
    _cache_status(invoice, remote)

    if invoice.status in _TERMINAL_STATUSES:
        return None

    return _to_response(invoice, remote=remote)


async def open_invoice(
    user_id: UUID,
    network: str,
    amount_cents: int,
    session: AsyncSession,
) -> InvoiceResponse:
    """Return the user's open invoice, or ask the service for a new one.

    THE EXISTING-INVOICE CHECK IS THE IDEMPOTENCY NARROWING AND NOT A
    CONVENIENCE. The service creates a second invoice for a repeated
    product_ref without complaint (TOR section 11 p.11), and a user who
    then pays the first one leaves the product waiting on the second.
    Not making the second call is the only part of that a client can
    do; the part it cannot do is survive a call that timed out, because
    a timeout does not say whether the invoice was created. Closing
    that is service-side work (P-23).

    The amount is ignored when an invoice is already open -- an open
    invoice has an address and a deadline the user may already have
    acted on, and quietly replacing it with a differently-priced one
    would invalidate a payment in flight.
    """
    existing = await current_invoice(user_id, network, session)
    if existing is not None:
        return existing

    # Minted before the call so the service is given a reference that
    # becomes this row's key on success. See the model docstring on why
    # no row is written for a call that fails.
    product_ref = uuid4()

    logger.info(
        "crypto_invoice_requested",
        product_ref=str(product_ref),
        user_id=str(user_id),
        network=network,
        amount_cents=amount_cents,
    )

    remote = await payments_client.create_invoice(
        product_ref=str(product_ref),
        network=network,
        invoice_amount_cents=amount_cents,
    )

    invoice = CryptoInvoice(
        id=product_ref,
        user_id=user_id,
        service_invoice_id=UUID(str(remote["id"])),
        network=str(remote["network"]),
        address=str(remote["address"]),
        invoice_amount_cents=int(remote["invoice_amount_cents"]),
        status=str(remote["status"]),
        expires_at=_parse_timestamp(remote["expires_at"]),
    )
    session.add(invoice)
    await session.flush()

    logger.info(
        "crypto_invoice_opened",
        invoice_id=str(invoice.id),
        service_invoice_id=str(invoice.service_invoice_id),
        user_id=str(user_id),
        network=invoice.network,
    )

    return _to_response(invoice, remote=remote)


async def read_invoice(
    invoice_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> InvoiceResponse:
    """One invoice as the service currently sees it.

    A terminal status from here can arrive before any event for it
    does, and that is correct rather than a race: expiry is resolved on
    read and the matching event is emitted later by the service's
    sweeper (TOR section 8).
    """
    invoice = await _load_owned(invoice_id, user_id, session)
    remote = await payments_client.get_invoice(invoice.service_invoice_id)
    _cache_status(invoice, remote)
    return _to_response(invoice, remote=remote)


async def submit_invoice_txid(
    invoice_id: UUID,
    user_id: UUID,
    txid: str,
    session: AsyncSession,
) -> TxidResultResponse:
    """Forward one TXID and relay what the service made of it.

    THE COUNTERS COME BACK FROM THE SERVICE AND ARE NOT COMPUTED HERE.
    Two of the six outcomes -- ``invalid_format`` and ``api_error`` --
    never reach an explorer and spend no attempt, so any local
    "one submission, one attempt" arithmetic would report a budget the
    user has not actually spent.

    The TXID is whitespace-stripped and otherwise handed over
    untouched. Stripping is done because a hash pasted from a block
    explorer routinely arrives with a trailing newline and the service
    would rightly call that malformed; anything beyond stripping would
    be this product forming an opinion about a format the service owns.
    """
    invoice = await _load_owned(invoice_id, user_id, session)
    remote = await payments_client.submit_txid(
        invoice.service_invoice_id, txid.strip()
    )
    _cache_status(invoice, remote)

    logger.info(
        "crypto_invoice_txid_submitted",
        invoice_id=str(invoice.id),
        user_id=str(user_id),
        result_code=remote.get("result_code"),
        status=remote.get("status"),
    )

    return TxidResultResponse(
        status=str(remote["status"]),
        result_code=str(remote["result_code"]),
        attempts_used=int(remote["attempts_used"]),
        attempts_remaining=int(remote["attempts_remaining"]),
    )
