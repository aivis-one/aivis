# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices: the client's request for a manual
# confirmation, and the administrator's notes on it
# =============================================================================
#
# WHY THIS EXISTS. A client who paid another way (by bank, or with a hash the
# service cannot find) asks the administrator to look at the payment from the
# deposit screen. The administrator sees the request in the crypto invoices
# list, may write notes on the invoice at any time, and confirms the invoice
# by hand (manual_confirm.py).
#
# NOTHING NEW IS STORED IN A TABLE OF ITS OWN. Both facts are rows of the
# audit log, which already holds an immutable record per event:
#   * deposit.manual_requested -- actor: the invoice's owner; target: the
#     crypto invoice; data: amount_cents, network, invoice_id,
#     service_invoice_id. At most one per invoice (the invoice row is locked
#     while the request is written, so two calls at once write one row).
#   * deposit.manual_note      -- actor: the administrator; target: the crypto
#     invoice; data: text. Any number per invoice, listed oldest first.
# Whether a request is OPEN is computed, never stored: a request exists and the
# invoice is not credited (by hand or by the service) -- the same two facts
# manual_confirm.credited_map reads.
#
# A REQUEST IS ALLOWED WHILE THE INVOICE IS NOT CREDITED, EXPIRED OR NOT: the
# money may reach the administrator after the invoice's deadline, and the
# deadline decides nothing here.
#
# WHAT THE CLIENT SEES: whether a request exists and whether the invoice was
# credited by hand (manual_state, read by the invoice renders in service.py).
# The notes and the confirmation's reason are staff-only and never reach a
# client response.
#
# COMMIT RULE (P-01): nothing here commits.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import ColumnElement, String, cast, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog, record_audit
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.payments.constants import WebhookOutcome
from app.modules.payments.models import CryptoInvoice, CryptoWebhookEvent, Payment
from app.modules.payments.schemas import ManualRequestResponse, StaffInvoiceNote
from app.modules.users.models import User

logger = structlog.get_logger()

EVENT_REQUESTED = "deposit.manual_requested"
EVENT_NOTE = "deposit.manual_note"
TARGET_INVOICE = "crypto_invoice"


# --- conditions shared by the list filter, the count and the rules ----------


def requested_condition() -> ColumnElement[bool]:
    """True for a crypto invoice that has a manual-confirmation request."""
    return exists().where(
        AuditLog.event == EVENT_REQUESTED,
        AuditLog.target_type == TARGET_INVOICE,
        AuditLog.target_id == CryptoInvoice.id,
    )


def credited_condition() -> ColumnElement[bool]:
    """True for a crypto invoice already credited, by hand or by the service.

    The same two facts as manual_confirm.credited_map: a Payment that names the
    service invoice in its provider_data, or a webhook event with outcome
    "credited" for it.
    """
    paid = exists().where(
        Payment.provider_data["service_invoice_id"].astext
        == cast(CryptoInvoice.service_invoice_id, String)
    )
    event = exists().where(
        CryptoWebhookEvent.invoice_id == CryptoInvoice.service_invoice_id,
        CryptoWebhookEvent.outcome == WebhookOutcome.CREDITED.value,
    )
    return paid | event


def open_request_condition() -> ColumnElement[bool]:
    """A request exists and the invoice is not credited."""
    return requested_condition() & ~credited_condition()


async def count_open_requests(session: AsyncSession) -> int:
    """How many crypto invoices carry an open manual-confirmation request."""
    return (
        await session.execute(
            select(func.count())
            .select_from(CryptoInvoice)
            .where(open_request_condition())
        )
    ).scalar_one()


# --- reads --------------------------------------------------------------------


async def requested_at_map(
    session: AsyncSession, invoice_ids: list[UUID]
) -> dict[UUID, datetime]:
    """For each invoice with a request: when it was made (the first one)."""
    if not invoice_ids:
        return {}
    rows = await session.execute(
        select(AuditLog.target_id, func.min(AuditLog.created_at))
        .where(
            AuditLog.event == EVENT_REQUESTED,
            AuditLog.target_type == TARGET_INVOICE,
            AuditLog.target_id.in_(invoice_ids),
        )
        .group_by(AuditLog.target_id)
    )
    return {target_id: at for target_id, at in rows.all()}


async def manual_state(
    session: AsyncSession, invoice: CryptoInvoice
) -> tuple[datetime | None, bool]:
    """For the client's invoice render: (requested at, credited by hand)."""
    requested_at = (await requested_at_map(session, [invoice.id])).get(invoice.id)
    rows = await session.execute(
        select(Payment.provider_data).where(
            Payment.provider_data["service_invoice_id"].astext
            == str(invoice.service_invoice_id)
        )
    )
    by_hand = any((data or {}).get("manual") is True for (data,) in rows.all())
    return requested_at, by_hand


def _author_name(user: User | None) -> str | None:
    if user is None:
        return None
    profile = user.profile or {}
    parts = [profile.get("first_name"), profile.get("last_name")]
    name = " ".join(str(part) for part in parts if part)
    return name or user.email


def _note(entry: AuditLog, author: User | None) -> StaffInvoiceNote:
    return StaffInvoiceNote(
        id=entry.id,
        text=str((entry.data or {}).get("text", "")),
        author_id=entry.actor_id,
        author_name=_author_name(author),
        created_at=entry.created_at,
    )


async def notes_map(
    session: AsyncSession, invoice_ids: list[UUID]
) -> dict[UUID, list[StaffInvoiceNote]]:
    """For each invoice with notes: the notes, oldest first (newest last)."""
    if not invoice_ids:
        return {}
    rows = await session.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(
            AuditLog.event == EVENT_NOTE,
            AuditLog.target_type == TARGET_INVOICE,
            AuditLog.target_id.in_(invoice_ids),
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    )
    result: dict[UUID, list[StaffInvoiceNote]] = {}
    for entry, author in rows.all():
        result.setdefault(entry.target_id, []).append(_note(entry, author))
    return result


async def confirm_reason_map(
    session: AsyncSession, payment_ids: list[UUID]
) -> dict[UUID, str]:
    """For each manual Payment: the reason its confirmation stored."""
    if not payment_ids:
        return {}
    rows = await session.execute(
        select(Payment.id, Payment.provider_data).where(Payment.id.in_(payment_ids))
    )
    reasons: dict[UUID, str] = {}
    for payment_id, data in rows.all():
        data = data or {}
        if data.get("manual") is True and data.get("reason"):
            reasons[payment_id] = str(data["reason"])
    return reasons


# --- the client's request -------------------------------------------------------


async def request_manual_confirmation(
    invoice_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> ManualRequestResponse:
    """Record the owner's request that an administrator confirms the invoice.

    Raises:
        NotFoundError: no such invoice, or it is somebody else's (404 for both,
            as the other owner-scoped reads answer).
        ConflictError: the invoice is already credited (409).

    A second call while the request stands returns the first one, with
    ``already_requested`` true, and writes nothing.
    """
    invoice = (
        await session.execute(
            select(CryptoInvoice)
            .where(CryptoInvoice.id == invoice_id, CryptoInvoice.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found")

    credited = (
        await session.execute(
            select(credited_condition()).where(CryptoInvoice.id == invoice.id)
        )
    ).scalar_one()
    if credited:
        raise ConflictError(
            "This invoice is already credited.", code="invoice_already_credited"
        )

    existing = (await requested_at_map(session, [invoice.id])).get(invoice.id)
    if existing is not None:
        return ManualRequestResponse(
            invoice_id=invoice.id, requested_at=existing, already_requested=True
        )

    data: dict[str, Any] = {
        "amount_cents": invoice.invoice_amount_cents,
        "network": invoice.network,
        "invoice_id": str(invoice.id),
        "service_invoice_id": str(invoice.service_invoice_id),
    }
    entry = await record_audit(
        session=session,
        event=EVENT_REQUESTED,
        actor_id=user_id,
        actor_type="user",
        target_type=TARGET_INVOICE,
        target_id=invoice.id,
        data=data,
    )
    # created_at is a server default: read it back rather than lazy-load it.
    await session.refresh(entry, attribute_names=["created_at"])
    logger.info(
        "payments_manual_requested",
        invoice_id=str(invoice.id),
        user_id=str(user_id),
        amount_cents=invoice.invoice_amount_cents,
    )
    return ManualRequestResponse(
        invoice_id=invoice.id,
        requested_at=entry.created_at,
        already_requested=False,
    )


# --- the administrator's notes ----------------------------------------------------


async def add_note(
    invoice_id: UUID,
    staff: User,
    text: str,
    session: AsyncSession,
) -> StaffInvoiceNote:
    """Write one note on a crypto invoice (before or after its confirmation).

    Raises:
        NotFoundError: no such invoice.
    """
    found = (
        await session.execute(
            select(CryptoInvoice.id).where(CryptoInvoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError("Crypto invoice not found", code="invoice_not_found")
    entry = await record_audit(
        session=session,
        event=EVENT_NOTE,
        actor_id=staff.id,
        actor_type="staff",
        target_type=TARGET_INVOICE,
        target_id=invoice_id,
        data={"text": text},
    )
    await session.refresh(entry, attribute_names=["created_at"])
    return _note(entry, staff)
