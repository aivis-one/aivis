# =============================================================================
# AIVIS.ONE Backend -- Ledger Service (Sprint 5.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   record_active_ledger()  -- write entry to active_ledger table
#   record_passive_ledger() -- write entry to passive_ledger table
#   get_active_balance()    -- frozen + confirmed balances (reversed excluded)
#   get_passive_balance()   -- frozen + confirmed balances (reversed excluded)
#
# PURE WRITE:
#   record_*() functions are pure DB writes. They do NOT validate AML
#   routes -- that responsibility belongs to the orchestrator layer
#   (transfer service, Phase 6+). See validators.py for validate_route().
#
# STATUS VALIDATION:
#   record_*() validates status against LedgerStatus enum. Only "frozen"
#   and "confirmed" are accepted for new entries. "reversed" is never
#   written directly -- it's set by the reversal process (Sprint 5.3).
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# IMMUTABLE ENTRIES:
#   Ledger entries are never deleted or updated (except status column).
#   Reversals create mirror entries with reason + ":reversal" suffix.
#
# AMOUNT CONVENTION:
#   Positive = credit (money coming in to this ledger)
#   Negative = debit  (money going out from this ledger)
#   Zero = valid for gift entries (semaphore COUNT works without exceptions)
# =============================================================================

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.modules.ledgers.models import (
    ActiveLedger,
    LedgerStatus,
    PassiveLedger,
)

logger = structlog.get_logger()

# Statuses allowed for new ledger entries.
# "reversed" is never written directly -- only by the reversal process.
_WRITABLE_STATUSES = frozenset({LedgerStatus.FROZEN, LedgerStatus.CONFIRMED})


def _validate_status(status: str) -> None:
    """Validate that status is allowed for new ledger entries.

    Raises:
        BadRequestError: If status is not frozen or confirmed.
    """
    if status not in _WRITABLE_STATUSES:
        raise BadRequestError(
            f"Invalid ledger status for new entry: {status!r}. "
            f"Allowed: {', '.join(sorted(_WRITABLE_STATUSES))}"
        )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


async def record_active_ledger(
    session: AsyncSession,
    *,
    user_id: UUID,
    amount_cents: int,
    status: str,
    reason: str,
    frozen_until: datetime | None = None,
    origin_payment_id: UUID | None = None,
) -> ActiveLedger:
    """Create an entry in active_ledger.

    Pure write -- no AML validation. Caller is responsible for
    route validation via validators.validate_route() if needed.

    Args:
        session: Active DB session. Caller manages commit (P-01).
        user_id: Owner of the ledger.
        amount_cents: Positive for credit, negative for debit, zero for gifts.
        status: "frozen" or "confirmed" (from LedgerStatus).
        reason: Canonical reason from LedgerReason.
        frozen_until: When the entry becomes confirmed (nullable).
        origin_payment_id: Link to originating Payment (for reversal chain).

    Returns:
        The created ActiveLedger entry (flushed, not committed).

    Raises:
        BadRequestError: If status is not a valid writable status.
    """
    _validate_status(status)

    entry = ActiveLedger(
        user_id=user_id,
        amount_cents=amount_cents,
        status=status,
        reason=reason,
        frozen_until=frozen_until,
        origin_payment_id=origin_payment_id,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "active_ledger_recorded",
        entry_id=str(entry.id),
        user_id=str(user_id),
        amount_cents=amount_cents,
        status=status,
        reason=reason,
    )

    return entry


async def record_passive_ledger(
    session: AsyncSession,
    *,
    user_id: UUID,
    amount_cents: int,
    status: str,
    reason: str,
    frozen_until: datetime | None = None,
    origin_payment_id: UUID | None = None,
) -> PassiveLedger:
    """Create an entry in passive_ledger.

    Pure write -- no AML validation. Caller is responsible for
    route validation via validators.validate_route() if needed.

    Args:
        session: Active DB session. Caller manages commit (P-01).
        user_id: Owner of the ledger.
        amount_cents: Positive for credit, negative for debit, zero for gifts.
        status: "frozen" or "confirmed" (from LedgerStatus).
        reason: Canonical reason from LedgerReason.
        frozen_until: When the entry becomes confirmed (nullable).
        origin_payment_id: Link to originating Payment (for reversal chain).

    Returns:
        The created PassiveLedger entry (flushed, not committed).

    Raises:
        BadRequestError: If status is not a valid writable status.
    """
    _validate_status(status)

    entry = PassiveLedger(
        user_id=user_id,
        amount_cents=amount_cents,
        status=status,
        reason=reason,
        frozen_until=frozen_until,
        origin_payment_id=origin_payment_id,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "passive_ledger_recorded",
        entry_id=str(entry.id),
        user_id=str(user_id),
        amount_cents=amount_cents,
        status=status,
        reason=reason,
    )

    return entry


# ---------------------------------------------------------------------------
# Balance queries
# ---------------------------------------------------------------------------


async def get_active_balance(
    session: AsyncSession,
    user_id: UUID,
) -> dict[str, int]:
    """Get active ledger balance split by status.

    Reversed entries are excluded from both totals.

    Returns:
        {"frozen": int, "confirmed": int} -- both in cents.
        Missing statuses default to 0.

    THE int() ON THE WAY OUT IS THE FIX, NOT TIDINESS (H12 P-46g).
    SUM() over a BigInteger column comes back from Postgres as numeric,
    which the driver hands us as Decimal, so this function returned
    Decimal under an int annotation from the day it was written. Every
    caller that only compared the value never noticed; the two that put
    it in a JSON body did, because JSONResponse raises TypeError on a
    Decimal -- the KYC gate would have answered 500 instead of 402 to
    any unverified user who had ever had a ledger row. Those call sites
    each carried their own int(), which meant the guarantee lived in
    the callers and the next caller inherited nothing. It lives here
    now and the casts there are gone.

    Lossless: amount_cents is BigInteger, so the sum has no fractional
    part to truncate.
    """
    stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (ActiveLedger.status == LedgerStatus.FROZEN, ActiveLedger.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("frozen"),
            func.coalesce(
                func.sum(
                    case(
                        (ActiveLedger.status == LedgerStatus.CONFIRMED, ActiveLedger.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("confirmed"),
        )
        .where(
            ActiveLedger.user_id == user_id,
            ActiveLedger.status != LedgerStatus.REVERSED,
        )
    )

    result = await session.execute(stmt)
    row = result.one()

    return {"frozen": int(row.frozen), "confirmed": int(row.confirmed)}


async def get_passive_balance(
    session: AsyncSession,
    user_id: UUID,
) -> dict[str, int]:
    """Get passive ledger balance split by status.

    Reversed entries are excluded from both totals.

    Returns:
        {"frozen": int, "confirmed": int} -- both in cents.
        Missing statuses default to 0.

    Carried the same false int annotation as get_active_balance and is
    fixed the same way -- see the note there for why the cast belongs
    at the source. Fixed together on purpose (H12 P-46g): only the
    active twin had produced a visible failure, and repairing that one
    alone would have left an identical trap for whoever first serialises
    a passive balance.
    """
    stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (PassiveLedger.status == LedgerStatus.FROZEN, PassiveLedger.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("frozen"),
            func.coalesce(
                func.sum(
                    case(
                        (PassiveLedger.status == LedgerStatus.CONFIRMED, PassiveLedger.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("confirmed"),
        )
        .where(
            PassiveLedger.user_id == user_id,
            PassiveLedger.status != LedgerStatus.REVERSED,
        )
    )

    result = await session.execute(stmt)
    row = result.one()

    return {"frozen": int(row.frozen), "confirmed": int(row.confirmed)}
