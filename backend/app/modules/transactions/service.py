# =============================================================================
# AIVIS.ONE Backend -- Transaction Service (Sprint 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   record_transaction()  -- write immutable event log entry
#   list_transactions()   -- paginated + filtered history for a user
#   get_transaction()     -- single event by id with user_id guard
#
# RECORD:
#   Called from other services in the same DB session. Pure write,
#   no commit (P-01). Caller is responsible for providing correct
#   type, amount, reference, and details.
#
# FILTERS:
#   - type: exact match or prefix (e.g. "withdrawal:" for all withdrawal events)
#   - date_from / date_to: inclusive range on created_at
#   - amount_min / amount_max: absolute value filter on amount_cents
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.transactions.models import Transaction

logger = structlog.get_logger()


async def record_transaction(
    session: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    amount_cents: int,
    reference_id: UUID | None = None,
    reference_type: str | None = None,
    details: dict[str, Any] | None = None,
    currency: str = "USD",
) -> Transaction:
    """Write an immutable event log entry.

    Pure write -- called from other services in the same session.

    Args:
        session: Active DB session. Caller manages commit (P-01).
        user_id: User who owns this event in their history.
        type: Event type from TransactionType enum.
        amount_cents: Operation amount (positive=in, negative=out).
        reference_id: ID of the source entity (payment, purchase, etc.).
        reference_type: Type of the source entity.
        details: Type-specific metadata JSONB for frontend display.
        currency: Currency code (default USD).

    Returns:
        The created Transaction entry (flushed, not committed).
    """
    entry = Transaction(
        user_id=user_id,
        type=type,
        amount_cents=amount_cents,
        currency=currency,
        reference_id=reference_id,
        reference_type=reference_type,
        details=details,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "transaction_recorded",
        transaction_id=str(entry.id),
        user_id=str(user_id),
        type=type,
        amount_cents=amount_cents,
        reference_type=reference_type,
    )

    return entry


async def list_transactions(
    user_id: UUID,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    type_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
) -> tuple[list[Transaction], int]:
    """Get paginated and filtered transaction history for a user.

    Filters:
        type_filter: Exact match or prefix with ":" (e.g. "withdrawal:").
        date_from: Inclusive lower bound on created_at.
        date_to: Inclusive upper bound on created_at.
        amount_min: Minimum absolute amount_cents.
        amount_max: Maximum absolute amount_cents.

    Returns:
        (transactions, total_count) tuple.
    """
    # Base filter.
    conditions = [Transaction.user_id == user_id]

    # Type filter: prefix match if ends with ":", exact otherwise.
    if type_filter:
        if type_filter.endswith(":"):
            conditions.append(Transaction.type.startswith(type_filter))
        else:
            conditions.append(Transaction.type == type_filter)

    # Date range.
    if date_from:
        conditions.append(Transaction.created_at >= date_from)
    if date_to:
        conditions.append(Transaction.created_at <= date_to)

    # Amount range (absolute value).
    if amount_min is not None:
        conditions.append(func.abs(Transaction.amount_cents) >= amount_min)
    if amount_max is not None:
        conditions.append(func.abs(Transaction.amount_cents) <= amount_max)

    # Count.
    count_stmt = (
        select(func.count())
        .select_from(Transaction)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Items.
    stmt = (
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def get_transaction(
    transaction_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> Transaction:
    """Load a single transaction by ID with user ownership guard.

    Args:
        transaction_id: Transaction UUID.
        user_id: Authenticated user ID (ownership check).
        session: Active DB session.

    Returns:
        Transaction entry.

    Raises:
        NotFoundError: Transaction not found or belongs to another user.
    """
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    )
    result = await session.execute(stmt)
    txn = result.scalar_one_or_none()

    if txn is None:
        raise NotFoundError("Transaction not found")

    return txn
