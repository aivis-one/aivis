# =============================================================================
# CBSHOME Backend -- Pool Service (Sprint 4.3 + Sprint 4.4)
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
#                                Sprint 4.4: returns (pool, consumed) so the
#                                caller (router) does not have to re-SELECT
#                                consumed for the response.
#   get_active_pool()         -- load the single active pool for a company.
#                                Used by products/service.py at create time and
#                                by purchases/service.py at purchase time.
#   get_pool_consumed()       -- SUM(Purchase.units) for active purchases of
#                                the company (gifts included).
#   get_pool_remaining()      -- pool.total_options - consumed. Sprint 4.4:
#                                replaces purchases.service._get_pool_remaining
#                                so the read path lives in one place.
#   with_consumed_remaining() -- decorate a pool ORM row with computed
#                                consumed + remaining for PoolResponse. Sprint
#                                4.4: consumed is now a REQUIRED argument --
#                                the helper is a pure transformation, never
#                                runs an implicit SELECT. Callers compute
#                                consumed once and pass it.
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
#
# Sprint 4.4 CHANGES:
#   - POOL_STATUS_ACTIVE moved to pools/constants.py (was a private
#     `_POOL_STATUS_ACTIVE` here, duplicated in two other modules).
#   - update_pool() now returns (OptionPool, int). The int is `consumed`
#     -- already computed for the "new_total < consumed" guard. Closes
#     the duplicated SELECT on PATCH /pool path.
#   - with_consumed_remaining() now takes consumed as a required arg --
#     no implicit SELECT. Callers (pool router, company dashboard) pass
#     the value they already have.
#   - +get_pool_remaining(pool, session) public helper, replaces the
#     local copy in purchases/service.py. Encapsulates "remaining =
#     total - consumed".
#   - _compute_equity_percent() now guards against total_supply <= 0 so
#     the contract is explicit; previously the call site was the only
#     thing keeping it safe.
#   - PoolResponseDict alias removed; with_consumed_remaining now
#     declares its return type as dict[str, Any] directly.
# =============================================================================

from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.service import get_company
from app.modules.pools.constants import POOL_STATUS_ACTIVE
from app.modules.pools.models import OptionPool
from app.modules.pools.schemas import CreatePoolRequest, UpdatePoolRequest
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User

logger = structlog.get_logger()


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

    Used by products/service.py (at product creation), purchases/service.py
    (at purchase time), and the staff router (POST/PATCH /pool).

    Raises:
        BadRequestError: If the company has no active pool yet.
        RuntimeError: If multiple active pools exist (data integrity).
    """
    stmt = select(OptionPool).where(
        OptionPool.company_id == company_id,
        OptionPool.status == POOL_STATUS_ACTIVE,
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


async def get_pool_reserved(
    company_id: UUID,
    session: AsyncSession,
) -> int:
    """Units reserved by ACTIVE installment plans, net of paid tranches.

    R51 (boss decision (a)): an installment plan RESERVES all its units
    at creation. A paid tranche turns its units into a Purchase row --
    which get_pool_consumed already counts -- so the reservation
    formula subtracts paid tranches to avoid double counting:

        reserved = SUM(plan.total_units      | plan ACTIVE)
                 - SUM(tranche.units_unlocked | tranche PAID, plan ACTIVE)

    Lifecycle for free, via plan.status alone:
      * tranche paid: +units in consumed, -units here -> net 0;
      * plan COMPLETED: drops out of the sum; its Purchases remain
        counted once in consumed;
      * plan DEFAULTED: drops out -> the unpaid remainder returns to
        the pool automatically (no code in default_plan needed).
    """
    plans_stmt = (
        select(func.coalesce(func.sum(InstallmentPlan.total_units), 0))
        .where(
            InstallmentPlan.company_id == company_id,
            InstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
        )
    )
    reserved_total = int((await session.execute(plans_stmt)).scalar_one())

    paid_stmt = (
        select(func.coalesce(func.sum(InstallmentTranche.units_unlocked), 0))
        .select_from(InstallmentTranche)
        .join(
            InstallmentPlan,
            InstallmentTranche.plan_id == InstallmentPlan.id,
        )
        .where(
            InstallmentPlan.company_id == company_id,
            InstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
            InstallmentTranche.status == InstallmentTrancheStatus.PAID,
        )
    )
    paid_units = int((await session.execute(paid_stmt)).scalar_one())

    return reserved_total - paid_units


async def lock_pool(
    company_id: UUID,
    session: AsyncSession,
) -> None:
    """Serialize pool consumption for a company (R51).

    pg_advisory_xact_lock keyed by company_id.int masked to a signed
    64-bit value -- the exact derivation the engine uses for the
    investor lock. Deterministic across processes and restarts (unlike
    hash(), which is randomized per process by PYTHONHASHSEED and must
    never key a cross-process lock). Held until transaction end, so a
    caller that locks, checks capacity and writes does all three
    atomically with respect to other pool consumers.

    Call sites (R51): execute_purchase step 4, create_plan step 4b.
    pay_tranche intentionally does NOT lock -- the plan's capacity was
    reserved at creation, paying a tranche consumes no new capacity.

    Raw SQL via text() follows the engine precedent: advisory locks
    have no ORM API.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": company_id.int & 0x7FFFFFFFFFFFFFFF},
    )


async def get_pool_remaining(
    pool: OptionPool,
    session: AsyncSession,
) -> int:
    """Options remaining in pool: total_options - consumed - reserved.

    Sprint 4.4: consolidated from the local copy in purchases/service.py
    (`_get_pool_remaining`). Single source of truth so future changes
    to the consumption query (logging, new statuses, etc.) land in one
    place.

    R51: subtracts ACTIVE-plan reservations (get_pool_reserved) so an
    installment plan holds its units from the moment of creation --
    instant buyers cannot purchase capacity already promised to a plan,
    and a plan cannot be created over capacity reserved by others.

    Can return a negative number when gifts have overflowed into owner
    supply (spec §3.7). Callers MUST treat negative as zero-or-less for
    any "can the user buy" decision.
    """
    consumed = await get_pool_consumed(pool.company_id, session)
    reserved = await get_pool_reserved(pool.company_id, session)
    return pool.total_options - consumed - reserved


async def with_consumed_remaining(
    pool: OptionPool,
    _session: AsyncSession,
    consumed: int,
) -> dict[str, Any]:
    """Render a pool ORM row to a dict that PoolResponse can validate.

    Sprint 4.4: `consumed` is a REQUIRED argument. The helper is now a
    pure transformation -- it never runs a SELECT. Callers compute
    consumed once (via get_pool_consumed) and pass it. This avoids the
    duplicated SELECT on the PATCH /pool path where update_pool already
    needed consumed for its "below-consumed" guard.

    `_session` is kept in the signature (with the underscore prefix
    that signals "intentionally unused" in Python) for forward-compat:
    a future schema field might need to look something up. Removing
    the parameter now would force every caller to update its kwargs
    when that day comes; keeping it is cheap.

    The router uses this helper before model_validate so the response
    carries the derived numbers. Kept in the service module so other
    consumers (company dashboard) can reuse the exact shape without
    going through the staff endpoint.
    """
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

    Sprint 4.4: explicit guard on total_supply <= 0. The original
    implementation relied on the call site (update_pool, which loads a
    company that previously passed CreateCompanyRequest.total_supply>0).
    A direct call from another module would silently throw
    decimal.DivisionByZero, which is harder to trace than a clean
    ValueError naming the bad input.
    """
    if total_supply <= 0:
        raise ValueError(
            f"total_supply must be positive, got {total_supply}"
        )
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
        OptionPool.status == POOL_STATUS_ACTIVE,
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
        status=POOL_STATUS_ACTIVE,
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
) -> tuple[OptionPool, int]:
    """Update the active pool's total_options (допэмиссия).

    equity_percent is recomputed from the new total_options.

    Cannot reduce total_options below already-consumed options. Consumed
    is SUM(Purchase.units) for active purchases of this company,
    including gifts.

    Sprint 4.4: returns (pool, consumed). consumed is computed once for
    the "new_total < consumed" guard and reused by the caller (router)
    for the response. Closes the duplicated SELECT on the PATCH path.

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

    return pool, consumed
