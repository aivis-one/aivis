# =============================================================================
# CBSHOME Backend -- Pool Service (Sprint 4.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_pool()             -- create the active OptionPool for a company.
#                                Caller specifies equity_percent (the share of
#                                company.total_supply to allocate). total_options
#                                is derived: floor(total_supply * pct / 100).
#                                At most one active pool per company is enforced
#                                by a partial unique index on the column
#                                (uq_one_active_pool_per_company, migration 0027).
#                                Service does a pre-check SELECT for a clean
#                                400 message, plus a SAVEPOINT + IntegrityError
#                                catch as a race-condition safety net (P-05).
#   update_pool()             -- update an active pool's total_options
#                                (допэмиссия). equity_percent is recomputed.
#                                Cannot reduce below already-consumed options.
#   get_active_pool()         -- load the single active pool for a company.
#                                Used by products/service.py at create time and
#                                by purchases/service.py at purchase time.
#   get_pool_consumed()       -- SUM(Purchase.units) for active purchases of
#                                the company (gifts included).
#   with_consumed_remaining() -- decorate a pool ORM row with computed
#                                consumed + remaining for PoolResponse. Used
#                                by the staff pool router and (later) by the
#                                company dashboard module (B5).
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# CONSUMED:
#   "Consumed" = SUM(Purchase.units) for all active purchases of the
#   company, including gifts. Gifts consume the pool first; if pool
#   runs out, gifts overflow into owner supply (pool_remaining < 0).
#   See spec §3.5 - §3.7.
#
# DECIMAL precision:
#   equity_percent is stored Numeric(7, 4). We compute total_options as
#   integer floor of (total_supply * pct / 100) using Decimal arithmetic
#   to avoid float rounding on values near integer boundaries.
# =============================================================================

from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.service import get_company
from app.modules.pools.models import OptionPool
from app.modules.pools.schemas import CreatePoolRequest, UpdatePoolRequest
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User

logger = structlog.get_logger()


# Pool status values. Kept as strings (no enum module yet) to mirror
# the column type; OptionPool.status is String(20).
_POOL_STATUS_ACTIVE = "active"


# ---------------------------------------------------------------------------
# Public helpers (used by other modules)
# ---------------------------------------------------------------------------


async def get_active_pool(
    company_id: UUID,
    session: AsyncSession,
) -> OptionPool:
    """Load the single active pool for a company.

    The DB enforces at most one active pool via a partial unique index;
    this function still defensively rejects multi-active states so a
    bug in migrations / direct DB writes surfaces immediately.

    Raises:
        BadRequestError: If the company has no active pool yet.
        RuntimeError: If multiple active pools exist (data integrity).
    """
    stmt = select(OptionPool).where(
        OptionPool.company_id == company_id,
        OptionPool.status == _POOL_STATUS_ACTIVE,
    )
    result = await session.execute(stmt)
    pools = list(result.scalars().all())

    if len(pools) == 0:
        raise BadRequestError(
            f"Company {company_id} has no active pool. "
            f"Create one via POST /staff/companies/{{id}}/pool."
        )
    if len(pools) > 1:
        raise RuntimeError(
            f"Data integrity: multiple active pools for company {company_id}"
        )

    return pools[0]


async def get_pool_consumed(
    company_id: UUID,
    session: AsyncSession,
) -> int:
    """Sum of Purchase.units for active purchases of the company.

    Includes gifts. See module docstring for rationale.
    """
    stmt = (
        select(func.coalesce(func.sum(Purchase.units), 0))
        .where(
            Purchase.company_id == company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def with_consumed_remaining(
    pool: OptionPool,
    session: AsyncSession,
) -> "PoolResponseDict":
    """Render a pool ORM row to a dict that PoolResponse can validate.

    Computes consumed (sum of active Purchase.units for the company) and
    remaining (total_options - consumed; can go negative when gifts have
    overflowed into owner supply).

    The router uses this helper before model_validate so the response
    carries those derived numbers. Kept here (not in the router) so the
    company dashboard module (B5) can reuse it without going through
    the staff endpoint.
    """
    consumed = await get_pool_consumed(pool.company_id, session)
    return {
        "id": pool.id,
        "company_id": pool.company_id,
        "equity_percent": pool.equity_percent,
        "total_options": pool.total_options,
        "status": pool.status,
        "created_at": pool.created_at,
        "updated_at": pool.updated_at,
        "consumed": consumed,
        "remaining": pool.total_options - consumed,
    }


# Lightweight typing alias: PoolResponse expects this shape.
# Defined as Any-typed dict to avoid a runtime import cycle with schemas.
PoolResponseDict = dict  # type: ignore[type-arg, misc]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_total_options(total_supply: int, equity_percent: Decimal) -> int:
    """Derive pool.total_options from company supply and equity percent.

    floor(total_supply * percent / 100). Decimal arithmetic, then int
    truncation. Caller must validate inputs (positive, percent <= 100).
    """
    raw = Decimal(total_supply) * equity_percent / Decimal(100)
    return int(raw)  # int() on Decimal truncates toward zero (= floor for >= 0)


def _compute_equity_percent(total_options: int, total_supply: int) -> Decimal:
    """Derive pool.equity_percent from total_options and total_supply.

    Quantized to 4 decimal places to match Numeric(7, 4) column type.
    """
    raw = Decimal(total_options) * Decimal(100) / Decimal(total_supply)
    # Quantize to 4 dp without rounding surprises: the column is Numeric(7,4),
    # so anything beyond is silently dropped at write. Explicit quantize
    # keeps the in-memory value identical to the persisted value.
    return raw.quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# Pool CRUD
# ---------------------------------------------------------------------------


async def create_pool(
    company_id: UUID,
    body: CreatePoolRequest,
    staff: User,
    session: AsyncSession,
) -> OptionPool:
    """Create the active pool for a company.

    Business rules:
      - Company must exist and have total_supply > 0.
      - At most one active pool per company. A pre-check makes the
        common case give a clean 400, and a SAVEPOINT + IntegrityError
        catch closes the race window.
      - Computed total_options = floor(total_supply * equity_percent / 100)
        must be > 0 (rejects e.g. 0.0001% on a 100-supply company).

    Raises:
        NotFoundError: Company not found.
        BadRequestError: Company already has an active pool, or computed
            total_options is zero.
    """
    company = await get_company(company_id, session)

    if company.total_supply <= 0:
        # Should be impossible: total_supply is NOT NULL > 0 by request
        # schema and (in seed data) we ensure positive. Defensive.
        raise BadRequestError(
            f"Company {company_id} has total_supply={company.total_supply}; "
            f"cannot create a pool"
        )

    # Pre-check: any active pool already?
    existing_stmt = select(OptionPool.id).where(
        OptionPool.company_id == company_id,
        OptionPool.status == _POOL_STATUS_ACTIVE,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        raise BadRequestError(
            f"Company {company_id} already has an active pool ({existing})"
        )

    total_options = _compute_total_options(company.total_supply, body.equity_percent)
    if total_options <= 0:
        raise BadRequestError(
            f"Computed total_options={total_options} for "
            f"equity_percent={body.equity_percent}% on total_supply="
            f"{company.total_supply}. Increase equity_percent."
        )

    pool = OptionPool(
        company_id=company.id,
        equity_percent=body.equity_percent,
        total_options=total_options,
        status=_POOL_STATUS_ACTIVE,
    )
    session.add(pool)

    # Race-condition safety net for concurrent create_pool calls.
    # The partial unique index uq_one_active_pool_per_company enforces
    # uniqueness even when our pre-check passes for two concurrent
    # transactions. begin_nested() = SAVEPOINT, only the INSERT rolls
    # back on conflict, outer transaction stays valid for the 400.
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        if "uq_one_active_pool_per_company" in str(exc.orig):
            raise BadRequestError(
                f"Company {company_id} already has an active pool"
            ) from exc
        raise

    await session.refresh(pool)

    await record_audit(
        session=session,
        event="pool.created",
        actor_id=staff.id,
        actor_type="staff",
        target_type="option_pool",
        target_id=pool.id,
        data={
            "company_id": str(company.id),
            "equity_percent": str(body.equity_percent),
            "total_options": total_options,
        },
    )

    logger.info(
        "pool_created",
        pool_id=str(pool.id),
        company_id=str(company.id),
        equity_percent=str(body.equity_percent),
        total_options=total_options,
        staff_id=str(staff.id),
    )

    return pool


async def update_pool(
    company_id: UUID,
    body: UpdatePoolRequest,
    staff: User,
    session: AsyncSession,
) -> OptionPool:
    """Update the active pool's total_options (допэмиссия).

    equity_percent is recomputed from the new total_options.

    Cannot reduce total_options below already-consumed options. Consumed
    is SUM(Purchase.units) for active purchases of this company,
    including gifts.

    Raises:
        NotFoundError: Company not found.
        BadRequestError: Company has no active pool, new total_options
            below already consumed, or new total_options exceeds
            company.total_supply.
    """
    company = await get_company(company_id, session)
    pool = await get_active_pool(company.id, session)

    new_total = body.total_options

    if new_total > company.total_supply:
        raise BadRequestError(
            f"new total_options ({new_total}) exceeds company.total_supply "
            f"({company.total_supply})"
        )

    consumed = await get_pool_consumed(company.id, session)
    if new_total < consumed:
        raise BadRequestError(
            f"Cannot reduce pool.total_options to {new_total}: "
            f"{consumed} options are already consumed by active purchases"
        )

    old_total = pool.total_options
    old_pct = pool.equity_percent

    pool.total_options = new_total
    pool.equity_percent = _compute_equity_percent(new_total, company.total_supply)

    await session.flush()
    await session.refresh(pool)

    await record_audit(
        session=session,
        event="pool.updated",
        actor_id=staff.id,
        actor_type="staff",
        target_type="option_pool",
        target_id=pool.id,
        data={
            "company_id": str(company.id),
            "old_total_options": old_total,
            "new_total_options": new_total,
            "old_equity_percent": str(old_pct),
            "new_equity_percent": str(pool.equity_percent),
        },
    )

    logger.info(
        "pool_updated",
        pool_id=str(pool.id),
        company_id=str(company.id),
        old_total_options=old_total,
        new_total_options=new_total,
        old_equity_percent=str(old_pct),
        new_equity_percent=str(pool.equity_percent),
        staff_id=str(staff.id),
    )

    return pool
