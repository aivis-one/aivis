# =============================================================================
# CBSHOME Backend -- Payment Service (Sprint 5.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   get_or_create_deposit_address() -- idempotent crypto address per user+network
#   get_payment()                   -- load Payment by id
#   process_crypto_webhook()        -- create Payment, write active_ledger
#   list_payments()                 -- paginated history for an investor
#
# CLOSED MODULE:
#   Internal logic (provider selection, retry, fallback) is hidden.
#   External modules use PaymentServiceProtocol only.
#
# WEBHOOK FLOW:
#   1. Validate tx_hash uniqueness (ConflictError on duplicate)
#   2. Look up CryptoAddress by (to_address, network)
#   3. Create Payment: status=frozen, frozen_until=now+FREEZING_HOURS_CRYPTO
#   4. Fill provider_data via set_jsonb()
#   5. Write active_ledger entry (frozen) via ledger service
#   6. Audit: payment.crypto_received
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
#
# STUB:
#   Address generation returns a deterministic placeholder.
#   Real integration will call blockchain provider API.
# =============================================================================

from datetime import datetime, timedelta, UTC
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.constants import LedgerReason
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.interface import DepositAddress
from app.modules.payments.models import CryptoAddress, Payment
from app.modules.payments.schemas import CryptoWebhookRequest

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Deposit addresses
# ---------------------------------------------------------------------------


async def get_or_create_deposit_address(
    user_id: UUID,
    network: str,
    session: AsyncSession,
) -> DepositAddress:
    """Get or create a crypto deposit address for a user + network.

    Idempotent: returns existing address if one exists.
    Stub: generates a placeholder address (real integration in Phase 2).

    Uses begin_nested() (SAVEPOINT) for race condition handling (P-05).

    Args:
        user_id: The investor's user ID.
        network: Crypto network (TRC20, ERC20, BEP20, PoS).
        session: Active DB session.

    Returns:
        DepositAddress with the assigned wallet address.

    Raises:
        BadRequestError: If network is not supported.
    """
    # Validate network against config.
    if network not in settings.crypto_network_list:
        raise BadRequestError(
            f"Unsupported network: {network!r}. "
            f"Supported: {settings.crypto_network_list}"
        )

    # Check for existing address.
    stmt = select(CryptoAddress).where(
        CryptoAddress.user_id == user_id,
        CryptoAddress.network == network,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        return DepositAddress(
            address=existing.address,
            network=existing.network,
            user_id=existing.user_id,
        )

    # Generate stub address (placeholder for real provider integration).
    stub_address = f"CBS_{network}_{uuid4().hex[:16]}"

    new_addr = CryptoAddress(
        user_id=user_id,
        network=network,
        address=stub_address,
    )

    try:
        async with session.begin_nested():
            session.add(new_addr)
            await session.flush()
    except IntegrityError as exc:
        # Race condition: another request created the address first (P-05).
        if "uq_crypto_addresses_user_network" in str(exc.orig):
            result = await session.execute(stmt)
            existing = result.scalar_one()
            return DepositAddress(
                address=existing.address,
                network=existing.network,
                user_id=existing.user_id,
            )
        raise

    logger.info(
        "crypto_address_created",
        user_id=str(user_id),
        network=network,
        address=stub_address,
    )

    return DepositAddress(
        address=new_addr.address,
        network=new_addr.network,
        user_id=new_addr.user_id,
    )


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


# ---------------------------------------------------------------------------
# Crypto webhook processing
# ---------------------------------------------------------------------------


async def process_crypto_webhook(
    body: CryptoWebhookRequest,
    session: AsyncSession,
) -> Payment:
    """Process an incoming crypto payment webhook.

    Creates a Payment (status=frozen) and writes an active_ledger entry.

    Flow:
      1. Validate tx_hash uniqueness
      2. Look up CryptoAddress by (to_address, network)
      3. Create Payment with status=frozen, frozen_until
      4. Fill provider_data
      5. Write active_ledger entry (frozen)
      6. Audit event

    Args:
        body: Parsed webhook payload.
        session: Active DB session.

    Returns:
        The created Payment.

    Raises:
        ConflictError: If tx_hash already processed (duplicate webhook).
        NotFoundError: If to_address/network not found in crypto_addresses.
    """
    # 1. Check for duplicate tx_hash in provider_data.
    # Use a raw-ish JSONB query to find existing payment with this tx_hash.
    dup_stmt = select(Payment.id).where(
        Payment.provider_data["tx_hash"].as_string() == body.tx_hash,
    )
    dup_result = await session.execute(dup_stmt)
    if dup_result.scalar_one_or_none() is not None:
        raise ConflictError(
            f"Payment with tx_hash {body.tx_hash!r} already exists"
        )

    # 2. Look up our deposit address.
    addr_stmt = select(CryptoAddress).where(
        CryptoAddress.address == body.to_address,
        CryptoAddress.network == body.network,
    )
    addr_result = await session.execute(addr_stmt)
    crypto_addr = addr_result.scalar_one_or_none()

    if crypto_addr is None:
        raise NotFoundError(
            f"Deposit address not found: {body.to_address!r} "
            f"on network {body.network!r}"
        )

    user_id = crypto_addr.user_id

    # 3. Create Payment.
    now = datetime.now(UTC)
    frozen_until = now + timedelta(hours=settings.freezing_hours_crypto)

    provider = f"crypto_usdt_{body.network.lower()}"

    payment = Payment(
        user_id=user_id,
        amount_cents=body.amount_usd_cents,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider=provider,
        status=PaymentStatus.FROZEN,
        frozen_until=frozen_until,
    )
    session.add(payment)
    await session.flush()

    # 4. Fill provider_data via set_jsonb().
    payment.set_jsonb("provider_data", {
        "network": body.network,
        "to_address": body.to_address,
        "from_address": body.from_address,
        "tx_hash": body.tx_hash,
        "confirmed_block": body.confirmed_block,
        "amount_crypto": body.amount_crypto,
        "exchange_rate": body.exchange_rate,
    })
    await session.flush()
    await session.refresh(payment)

    # 5. Write active_ledger entry.
    reason = LedgerReason.DEPOSIT_CRYPTO.format(tx_hash=body.tx_hash)

    await record_active_ledger(
        session,
        user_id=user_id,
        amount_cents=body.amount_usd_cents,
        status=LedgerStatus.FROZEN,
        reason=reason,
        frozen_until=frozen_until,
        origin_payment_id=payment.id,
    )

    # 6. Audit.
    await record_audit(
        session=session,
        event="payment.crypto_received",
        actor_id=None,
        actor_type="system",
        target_type="payment",
        target_id=payment.id,
        data={
            "user_id": str(user_id),
            "amount_cents": body.amount_usd_cents,
            "network": body.network,
            "tx_hash": body.tx_hash,
            "provider": provider,
        },
    )

    logger.info(
        "crypto_payment_received",
        payment_id=str(payment.id),
        user_id=str(user_id),
        amount_cents=body.amount_usd_cents,
        network=body.network,
        tx_hash=body.tx_hash,
    )

    return payment
