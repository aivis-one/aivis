# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices: staff list and manual confirmation
# =============================================================================
#
# WHY THIS EXISTS. A client creates a crypto top-up invoice. When the money
# does not reach the product through the payments service (or arrives another
# way, for example by bank), an administrator opens that invoice and confirms
# it by hand: the client's balance receives the invoice's stated amount.
# Nothing else is built here -- no bank fee, no expiry rule, and no guard
# against a LATER service event for the same invoice.
#
# THE CONFIRMATION WRITES, IN THE CALLER'S TRANSACTION:
#   * a Payment (crypto, provider "manual", status CONFIRMED -- the admin's
#     act is the confirmation, so no cooling-off and no frozen_until);
#   * an ActiveLedger credit, status CONFIRMED, reason deposit:manual:<id>,
#     carrying origin_payment_id so a later reversal finds it;
#   * the two history rows the webhook path plus the confirmation batch
#     would have written for the same deposit (deposit:received and
#     deposit:confirmed) and the deposit.confirmed notification the batch
#     emits;
#   * an audit row, payment.manual_confirmed.
# The invoice's cached `status` column is NOT touched: it holds service
# statuses only (see CryptoInvoice.status).
#
# CREDITED-ALREADY CHECK (409). An invoice counts as credited when a Payment
# whose provider_data.service_invoice_id is the invoice's service id exists
# (the webhook writes it, so does this module), or a webhook event with
# outcome "credited" exists for it. Any status of such a Payment counts,
# a reversed one included: a reversed deposit is not credited again by an
# automatic act. The invoice row is locked (FOR UPDATE) for the check, so two
# manual confirmations of one invoice serialise and the second one is
# refused. A service event arriving AFTER a manual confirmation is NOT
# guarded against (the owner's word: not built now).
#
# COMMIT RULE (P-01): nothing here commits.
# =============================================================================

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms import comms_configured
from app.core.constants import LedgerReason
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.payments.constants import (
    PaymentStatus,
    PaymentType,
    WebhookOutcome,
)
from app.modules.payments.models import CryptoInvoice, CryptoWebhookEvent, Payment
from app.modules.payments.schemas import StaffCryptoInvoiceItem
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction
from app.modules.users.models import User

logger = structlog.get_logger()

PROVIDER_MANUAL = "manual"
CREDITED_BY_MANUAL = "manual"
CREDITED_BY_SERVICE = "service"


def page_offset(page: int, per_page: int) -> int:
    """Rows to skip for a 1-based page."""
    return (page - 1) * per_page


def build_invoice_filters(
    *,
    user_id: UUID | None = None,
    status: str | None = None,
) -> list[ColumnElement[bool]]:
    """The WHERE conditions of the list; an empty filter adds none."""
    conditions: list[ColumnElement[bool]] = []
    if user_id is not None:
        conditions.append(CryptoInvoice.user_id == user_id)
    if status is not None:
        conditions.append(CryptoInvoice.status == status)
    return conditions


def build_list_statement(
    conditions: list[ColumnElement[bool]],
    *,
    page: int,
    per_page: int,
) -> Select[Any]:
    """The page query: invoices with their owner, newest first."""
    return (
        select(CryptoInvoice, User)
        .join(User, User.id == CryptoInvoice.user_id)
        .where(*conditions)
        .order_by(CryptoInvoice.created_at.desc(), CryptoInvoice.id.desc())
        .offset(page_offset(page, per_page))
        .limit(per_page)
    )


def user_name(profile: dict[str, Any] | None) -> str | None:
    """First and last name from the user's profile JSON, or None."""
    data = profile or {}
    parts = [data.get("first_name"), data.get("last_name")]
    name = " ".join(str(part) for part in parts if part)
    return name or None


def is_manual(provider_data: dict[str, Any] | None) -> bool:
    """True when a Payment's provider_data marks a manual confirmation."""
    return bool((provider_data or {}).get("manual") is True)


async def credited_map(
    session: AsyncSession,
    service_invoice_ids: list[UUID],
) -> dict[UUID, tuple[str, UUID | None]]:
    """For each service invoice id already credited: (by whom, payment id).

    By whom is "manual" or "service". Absent from the result = not credited.
    """
    if not service_invoice_ids:
        return {}
    wanted = {str(i): i for i in service_invoice_ids}
    result: dict[UUID, tuple[str, UUID | None]] = {}

    payments = await session.execute(
        select(Payment.id, Payment.provider_data).where(
            Payment.provider_data["service_invoice_id"].astext.in_(list(wanted))
        )
    )
    for payment_id, data in payments.all():
        key = wanted.get(str((data or {}).get("service_invoice_id")))
        if key is None:
            continue
        who = CREDITED_BY_MANUAL if is_manual(data) else CREDITED_BY_SERVICE
        # A service credit outranks nothing: keep the first found.
        result.setdefault(key, (who, payment_id))

    events = await session.execute(
        select(CryptoWebhookEvent.invoice_id, CryptoWebhookEvent.payment_id).where(
            CryptoWebhookEvent.invoice_id.in_(service_invoice_ids),
            CryptoWebhookEvent.outcome == WebhookOutcome.CREDITED.value,
        )
    )
    for invoice_id, payment_id in events.all():
        result.setdefault(invoice_id, (CREDITED_BY_SERVICE, payment_id))
    return result


async def list_crypto_invoices(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[StaffCryptoInvoiceItem], int]:
    """One page of crypto invoices and the total matching the filters."""
    conditions = build_invoice_filters(user_id=user_id, status=status)
    total = (
        await session.execute(
            select(func.count()).select_from(CryptoInvoice).where(*conditions)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            build_list_statement(conditions, page=page, per_page=per_page)
        )
    ).all()
    credited = await credited_map(
        session, [invoice.service_invoice_id for invoice, _ in rows]
    )
    items = []
    for invoice, user in rows:
        who, payment_id = credited.get(invoice.service_invoice_id, (None, None))
        items.append(
            StaffCryptoInvoiceItem(
                id=invoice.id,
                user_id=invoice.user_id,
                user_email=user.email,
                user_name=user_name(user.profile),
                network=invoice.network,
                amount_cents=invoice.invoice_amount_cents,
                status=invoice.status,
                created_at=invoice.created_at,
                expires_at=invoice.expires_at,
                credited=who is not None,
                credited_by=who,
                payment_id=payment_id,
            )
        )
    return items, total


async def confirm_crypto_invoice(
    invoice_id: UUID,
    staff_id: UUID,
    reason: str,
    session: AsyncSession,
) -> Payment:
    """Credit a crypto invoice's stated amount by hand.

    Raises:
        NotFoundError: no such invoice.
        ConflictError: the invoice is already credited (by hand or by the
            service).
    """
    invoice = (
        await session.execute(
            select(CryptoInvoice)
            .where(CryptoInvoice.id == invoice_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Crypto invoice not found", code="invoice_not_found")

    existing = await credited_map(session, [invoice.service_invoice_id])
    if invoice.service_invoice_id in existing:
        who, payment_id = existing[invoice.service_invoice_id]
        raise ConflictError(
            f"This invoice is already credited ({who}, payment {payment_id}).",
            code="invoice_already_credited",
        )

    amount_cents = invoice.invoice_amount_cents
    payment = Payment(
        user_id=invoice.user_id,
        amount_cents=amount_cents,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider=PROVIDER_MANUAL,
        status=PaymentStatus.CONFIRMED,
        provider_data={
            "manual": True,
            "confirmed_by": str(staff_id),
            "reason": reason,
            "service_invoice_id": str(invoice.service_invoice_id),
            "invoice_id": str(invoice.id),
            "network": invoice.network,
            "invoice_amount_cents": amount_cents,
        },
    )
    session.add(payment)
    await session.flush()

    await record_active_ledger(
        session,
        user_id=invoice.user_id,
        amount_cents=amount_cents,
        status=LedgerStatus.CONFIRMED,
        reason=LedgerReason.DEPOSIT_MANUAL.format(payment_id=payment.id),
        origin_payment_id=payment.id,
    )

    details = {
        "network": invoice.network,
        "service_invoice_id": str(invoice.service_invoice_id),
        "manual": True,
    }
    for txn_type in (
        TransactionType.DEPOSIT_RECEIVED,
        TransactionType.DEPOSIT_CONFIRMED,
    ):
        await record_transaction(
            session,
            user_id=invoice.user_id,
            type=txn_type,
            amount_cents=amount_cents,
            reference_id=payment.id,
            reference_type=ReferenceType.PAYMENT,
            details=details,
        )

    await record_audit(
        session=session,
        event="payment.manual_confirmed",
        actor_id=staff_id,
        actor_type="staff",
        target_type="payment",
        target_id=payment.id,
        data={
            "user_id": str(invoice.user_id),
            "amount_cents": amount_cents,
            "network": invoice.network,
            "invoice_id": str(invoice.id),
            "service_invoice_id": str(invoice.service_invoice_id),
            "reason": reason,
        },
    )

    if comms_configured():
        amount = f"{amount_cents / 100:,.2f}"
        await emit_event(
            session,
            EVENT_NOTIFICATION_REQUEST,
            {
                "idempotency_key": f"deposit-confirmed:{payment.id}",
                "type": "deposit.confirmed",
                "target_type": "user",
                "target_value": str(invoice.user_id),
                "title": "Deposit confirmed",
                "body": f"Your deposit of ${amount} is confirmed and available.",
            },
        )

    logger.info(
        "payments_manual_confirmed",
        invoice_id=str(invoice.id),
        payment_id=str(payment.id),
        user_id=str(invoice.user_id),
        staff_id=str(staff_id),
        amount_cents=amount_cents,
    )
    return payment
