# =============================================================================
# AIVIS.ONE Backend -- Payments Webhook Receiver (H8)
# =============================================================================
#
# The inbound half of the payments integration. The service publishes an
# event when an invoice reaches a terminal status and POSTs it here with
# retries; until this module existed the service got a 404 on every
# delivery and no payment ever reached a balance.
#
# AUTHENTICATION IS A SHARED SECRET, NOT A SIGNATURE. TOR section 8
# chose it deliberately for the MVP: the traffic runs over the internal
# docker network between the service and this product, and the header
# name (X-Payments-Secret, not X-Signature) says what it carries. See
# verify_payments_secret below for why the emptiness check comes first.
#
# WHAT THE ANSWER COSTS. A non-2xx makes the service retry, and after
# WEBHOOK_MAX_ATTEMPTS its outbox row goes `failed` -- irreversibly,
# because the service has no resend command. So the status code is a
# decision about money, not about tidiness:
#
#   2xx -- for everything a retry could never fix but that we CAN
#          record: an unknown product_ref, a repeat delivery, a
#          non-crediting status.
#   4xx -- for a body this receiver cannot honour: a bad secret, a body
#          that does not parse, a `confirmed` with no amount in it, an
#          event whose two identifiers disagree. These leave the
#          service's outbox row `failed` with its last error, which is
#          a trace somebody can FIND with a query. Answering 200 to
#          them would leave the failure visible only in our own logs
#          and `delivered` on the service's side -- one trace instead
#          of two, and the wrong one missing.
#   5xx -- only for our own failure to process something we should have
#          been able to process. A retry genuinely helps there.
#
# ORDER OF OPERATIONS. The deduplicating INSERT happens BEFORE any money
# is written and after everything that can refuse the event, so a second
# delivery loses the insert and never reaches the ledger. Check-then-act
# would not do: two deliveries can be in flight at once.
# =============================================================================

from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from uuid import UUID

import structlog
from fastapi import Header
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.constants import LedgerReason
from app.core.exceptions import AivisError, UnauthorizedError
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.payments.constants import (
    PaymentStatus,
    PaymentType,
    ServiceEventStatus,
    WebhookOutcome,
)
from app.modules.payments.models import CryptoInvoice, CryptoWebhookEvent, Payment
from app.modules.payments.schemas import WebhookEventRequest
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction

logger = structlog.get_logger()

# Cooling-off applied to a crypto deposit, in hours.
#
# RE-ESTABLISHED HERE RATHER THAN RESTORED AS A SETTING. H7 removed
# FREEZING_HOURS_CRYPTO along with its only reader and left the policy
# to whoever wrote this receiver. The value is the one that policy had.
#
# WHY A COOLING-OFF AT ALL, when the money is already irreversibly on a
# chain: the freeze is not about the transfer settling. A frozen ledger
# entry is what run_confirmation_batch later flips to confirmed, and
# that flip is the ONLY emitter of the deposit.confirmed notification
# and of the deposit:confirmed transaction row in this tree. Writing the
# entry as confirmed immediately would not merely skip a delay -- it
# would silently delete the notification that tells the user their money
# arrived, and get_active_balance would report the amount under a
# different key than every other deposit does.
CRYPTO_FREEZING_HOURS: int = 1


async def verify_payments_secret(
    x_payments_secret: str = Header(default=""),
) -> None:
    """Authenticate a delivery from the payments service.

    THE EMPTINESS CHECK IS FIRST AND THAT ORDER IS THE WHOLE POINT.
    compare_digest("", "") is TRUE, so a box whose configured secret is
    empty would accept a request carrying an empty header -- which is
    every request, since the header defaults to "". An unconfigured
    receiver would be an open one. Refusing outright while the secret is
    empty is fail-closed: TOR section 8 states it in those words.

    This is deliberately NOT delegated to the config validator. That
    validator does not run on a development box (it is gated on
    `not is_dev`), so a dev box can legitimately hold an empty secret --
    and must still refuse events rather than accept them all.

    Raises:
        UnauthorizedError: secret unset, header absent/empty, or
            mismatched. The three are one message on purpose: a
            response that distinguished them would tell an unauthorised
            caller which half they got right.
    """
    configured = settings.payments_webhook_secret
    if not configured or not compare_digest(x_payments_secret, configured):
        logger.warning(
            "payments_webhook_rejected",
            reason="secret_unset" if not configured else "secret_mismatch",
            header_present=bool(x_payments_secret),
        )
        raise UnauthorizedError("Invalid payments webhook secret")


def _unprocessable(message: str, code: str) -> AivisError:
    """A 422 for a body this receiver cannot honour.

    422 rather than 400 to sit in the same class as the schema errors
    FastAPI already raises for this endpoint: from the service's side
    both mean "the body you sent is not one I can act on", and one class
    of answer for one class of problem keeps its failed-row triage
    simple.
    """
    return AivisError(message=message, code=code, status_code=422)


async def process_webhook_event(
    body: WebhookEventRequest,
    session: AsyncSession,
) -> WebhookOutcome | None:
    """Process one delivered event.

    Returns the outcome, or None when this exact event was already
    processed (a duplicate delivery, which is normal traffic).

    Raises:
        AivisError(422): the event cannot be honoured -- see
            _unprocessable and the module header.
    """
    # A `confirmed` with no amount in it. THE KEY'S ABSENCE IS TESTED,
    # NOT ITS TRUTHINESS: credited_amount_cents = 0 is a real credit of
    # nothing (a dust transfer) and must go down the crediting path, so
    # `not body.credited_amount_cents` would send a legitimate zero into
    # this refusal.
    credited_sent = "credited_amount_cents" in body.model_fields_set
    if body.status is ServiceEventStatus.CONFIRMED and not credited_sent:
        logger.error(
            "payments_webhook_confirmed_without_amount",
            invoice_id=str(body.invoice_id),
            product_ref=str(body.product_ref),
        )
        raise _unprocessable(
            "A confirmed event carried no credited_amount_cents: there "
            "is no amount to credit and this receiver will not guess "
            "one.",
            "confirmed_without_amount",
        )

    invoice = await session.get(CryptoInvoice, body.product_ref)

    if invoice is None:
        # Accepted, not retried: no number of retries makes a row that
        # was never written appear. The most likely cause is an invoice
        # the service created on a call that then timed out here, in
        # which case the product never learned its id (see the
        # CryptoInvoice docstring).
        logger.warning(
            "payments_webhook_unknown_product_ref",
            invoice_id=str(body.invoice_id),
            product_ref=str(body.product_ref),
            status=body.status.value,
        )
        event = await _record_event(body, session, WebhookOutcome.NO_INVOICE)
        if event is None:
            return None
        return WebhookOutcome.NO_INVOICE

    if invoice.service_invoice_id != body.invoice_id:
        # The two identifiers in one body disagree: product_ref resolves
        # to a row that was issued for a DIFFERENT service invoice. One
        # of the two is wrong and there is no safe way to pick. Refusing
        # is what makes it findable -- crediting on the strength of
        # whichever field we trusted more would move money on a body we
        # know to be inconsistent.
        logger.error(
            "payments_webhook_invoice_mismatch",
            product_ref=str(body.product_ref),
            event_invoice_id=str(body.invoice_id),
            row_invoice_id=str(invoice.service_invoice_id),
        )
        raise _unprocessable(
            "invoice_id does not match the invoice this product_ref was "
            "issued for.",
            "invoice_mismatch",
        )

    if body.status is not ServiceEventStatus.CONFIRMED:
        # expired / attempts_exhausted / stalled. Processed rather than
        # ignored: an ignored event is retried until the service's
        # outbox row dies, and the cached status would stay stale for a
        # screen that reads it.
        event = await _record_event(body, session, WebhookOutcome.STATUS_CACHED)
        if event is None:
            return None
        invoice.status = body.status.value
        logger.info(
            "payments_webhook_status_cached",
            invoice_id=str(body.invoice_id),
            product_ref=str(body.product_ref),
            status=body.status.value,
        )
        return WebhookOutcome.STATUS_CACHED

    # ---- confirmed: this is the money path -------------------------
    #
    # NOTE WHAT IS *NOT* CONSULTED HERE: invoice.status. That column is
    # a cache of the service's own status and holds no authority (see
    # its docstring). Deciding on it would also get the ordering wrong
    # -- the service resolves expiry lazily, so a screen can have cached
    # `expired` for an invoice that then confirms, and refusing the
    # credit on that basis would drop a real payment. The amount in the
    # event is the only input to this decision.
    amount_cents = body.credited_amount_cents
    assert amount_cents is not None  # guaranteed by the credited_sent check

    event = await _record_event(body, session, WebhookOutcome.CREDITED)
    if event is None:
        return None

    now = datetime.now(UTC)
    frozen_until = now + timedelta(hours=CRYPTO_FREEZING_HOURS)

    payment = Payment(
        user_id=invoice.user_id,
        amount_cents=amount_cents,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        # Same shape the removed contour used: the network name is the
        # service's canonical one, lower-cased.
        provider=f"crypto_usdt_{invoice.network.lower()}",
        # Straight to FROZEN rather than through CREATED: the state
        # machine's created -> frozen edge means "the provider confirmed
        # receipt", and by the time this event exists it already has.
        # A row parked in CREATED would be waiting for a webhook that
        # has just arrived.
        status=PaymentStatus.FROZEN,
        frozen_until=frozen_until,
        provider_data={
            "network": invoice.network,
            "to_address": invoice.address,
            "service_invoice_id": str(body.invoice_id),
            "product_ref": str(body.product_ref),
            "invoice_amount_cents": invoice.invoice_amount_cents,
            "credited_amount_cents": amount_cents,
            # Sent only when it applies; recorded as the event framed it
            # rather than recomputed from the two amounts, because the
            # service owns that judgement (TOR section 11 p.12).
            "underpaid": (
                body.underpaid if "underpaid" in body.model_fields_set else None
            ),
            "occurred_at": body.occurred_at.isoformat(),
        },
    )
    session.add(payment)
    await session.flush()

    # NO tx_hash IN THE REASON, AND NO PLACE TO GET ONE. The service does
    # not put a transaction hash in its event and does not expose one
    # through its GET, so LedgerReason.DEPOSIT_CRYPTO (keyed by tx_hash)
    # cannot be filled here at all -- see the constant's own note.
    reason = LedgerReason.DEPOSIT_CRYPTO_INVOICE.format(invoice_id=body.invoice_id)

    await record_active_ledger(
        session,
        user_id=invoice.user_id,
        amount_cents=amount_cents,
        status=LedgerStatus.FROZEN,
        reason=reason,
        frozen_until=frozen_until,
        origin_payment_id=payment.id,
    )

    await record_audit(
        session=session,
        event="payment.crypto_received",
        actor_id=None,
        actor_type="system",
        target_type="payment",
        target_id=payment.id,
        data={
            "user_id": str(invoice.user_id),
            "amount_cents": amount_cents,
            "network": invoice.network,
            "service_invoice_id": str(body.invoice_id),
            "product_ref": str(body.product_ref),
        },
    )

    await record_transaction(
        session,
        user_id=invoice.user_id,
        type=TransactionType.DEPOSIT_RECEIVED,
        amount_cents=amount_cents,
        reference_id=payment.id,
        reference_type=ReferenceType.PAYMENT,
        details={
            "network": invoice.network,
            "service_invoice_id": str(body.invoice_id),
        },
    )

    event.payment_id = payment.id
    invoice.status = body.status.value

    logger.info(
        "payments_webhook_credited",
        invoice_id=str(body.invoice_id),
        product_ref=str(body.product_ref),
        user_id=str(invoice.user_id),
        payment_id=str(payment.id),
        amount_cents=amount_cents,
    )
    return WebhookOutcome.CREDITED


async def _record_event(
    body: WebhookEventRequest,
    session: AsyncSession,
    outcome: WebhookOutcome,
) -> CryptoWebhookEvent | None:
    """Claim this (invoice_id, status) pair, or report it already taken.

    Returns the new row, or None if this exact event was processed
    before.

    THE UNIQUE INDEX ARBITRATES, NOT A PRECEDING SELECT. Two deliveries
    of one event can overlap, and a check-then-act would let both find
    nothing and both credit. begin_nested() is a SAVEPOINT: only the
    losing INSERT rolls back, leaving the surrounding transaction usable
    so the endpoint can still answer 200 (P-05, the pattern the removed
    contour used against uq_payments_tx_hash).

    This is called BEFORE any money is written, so the loser of that
    race never reaches the ledger.
    """
    event = CryptoWebhookEvent(
        invoice_id=body.invoice_id,
        status=body.status.value,
        product_ref=body.product_ref,
        # Written only when the key was actually sent. NULL here means
        # "absent from the event"; 0 means "credited nothing".
        credited_amount_cents=(
            body.credited_amount_cents
            if "credited_amount_cents" in body.model_fields_set
            else None
        ),
        underpaid=(
            body.underpaid if "underpaid" in body.model_fields_set else None
        ),
        occurred_at=body.occurred_at,
        outcome=outcome.value,
    )
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError as exc:
        if "uq_crypto_webhook_events_invoice_status" not in str(exc.orig):
            raise
        logger.info(
            "payments_webhook_duplicate",
            invoice_id=str(body.invoice_id),
            status=body.status.value,
        )
        return None
    return event


async def latest_event_outcome(
    invoice_id: UUID,
    status: str,
    session: AsyncSession,
) -> str | None:
    """Outcome recorded for one (invoice_id, status) pair, if any.

    Exists for the tests and for operational triage -- the question
    "what did we do with that event" should be answerable without
    reading logs.
    """
    stmt = select(CryptoWebhookEvent.outcome).where(
        CryptoWebhookEvent.invoice_id == invoice_id,
        CryptoWebhookEvent.status == status,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
