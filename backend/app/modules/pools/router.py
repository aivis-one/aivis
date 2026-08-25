# =============================================================================
# AIVIS.ONE Backend -- Pool Staff Router (Sprint 4.3 + Sprint 4.4)
# =============================================================================
#
# ENDPOINTS:
#   POST  /api/v1/staff/companies/{company_id}/pool   -- create active pool
#   PATCH /api/v1/staff/companies/{company_id}/pool   -- update total_options
#                                                         (допэмиссия)
#
# PERMISSIONS:
#   Both endpoints require project_manage + financial_operations.
#   Mirrors POST /staff/companies and PATCH /staff/companies/{id}/price
#   from Phase 4 -- creating or resizing a pool is a financial operation.
#
# RESPONSE SHAPE:
#   PoolResponse with computed `consumed` and `remaining`. The
#   consumed/remaining derivation is centralised in
#   pools/service.with_consumed_remaining() so the company dashboard
#   module (B5) can reuse it without re-running this query through HTTP.
#
# Sprint 4.4 CHANGES:
#   - update_pool() now returns (pool, consumed). The router unpacks
#     the tuple and feeds the existing `consumed` value straight into
#     with_consumed_remaining(), saving the duplicated SELECT.
#   - create_pool path passes consumed=0 explicitly. A freshly-created
#     pool cannot have any active purchases against it (the only way
#     to consume options is to buy a product, which requires the pool
#     to exist first).
#   - with_consumed_remaining() now requires `consumed` as a positional
#     argument; callers compute it once and pass it.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.pools.schemas import (
    CreatePoolRequest,
    PoolResponse,
    UpdatePoolRequest,
)
from app.modules.pools.service import (
    create_pool,
    update_pool,
    with_consumed_remaining,
)
from app.modules.staff.permissions import require_financial_operations
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/companies",
    tags=["staff-pools"],
)


@router.post(
    "/{company_id}/pool",
    response_model=PoolResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pool_endpoint(
    company_id: UUID,
    body: CreatePoolRequest,
    staff: User = Depends(require_staff_permission("project_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> PoolResponse:
    """Create the active option pool for a company.

    Requires: project_manage + financial_operations.

    Body:
        equity_percent: percentage of company.total_supply to allocate.
                        Must be > 0 and <= 100. Decimal with up to 4
                        fractional digits.

    Returns the created pool with computed consumed=0, remaining=total_options.
    """
    await require_financial_operations(staff, session)

    pool = await create_pool(company_id, body, staff, session)
    # Sprint 4.4: with_consumed_remaining now requires `consumed` as an
    # argument. A freshly created pool has zero active purchases by
    # construction (you can't buy from a pool that didn't exist yet).
    payload = await with_consumed_remaining(pool, session, consumed=0)
    return PoolResponse.model_validate(payload)


@router.patch(
    "/{company_id}/pool",
    response_model=PoolResponse,
)
async def update_pool_endpoint(
    company_id: UUID,
    body: UpdatePoolRequest,
    staff: User = Depends(require_staff_permission("project_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> PoolResponse:
    """Update the active pool's total_options (допэмиссия).

    Requires: project_manage + financial_operations.

    Body:
        total_options: new absolute number of options in the pool.
                       Must be > 0, <= company.total_supply, and
                       >= already-consumed options.

    equity_percent is recomputed by the service from the new total_options.

    Returns the updated pool with current consumed and remaining.
    """
    await require_financial_operations(staff, session)

    # Sprint 4.4: update_pool returns (pool, consumed). The service
    # already had to SELECT consumed for its "below-consumed" guard,
    # so reuse that value here -- no second SELECT.
    pool, consumed = await update_pool(company_id, body, staff, session)
    payload = await with_consumed_remaining(pool, session, consumed=consumed)
    return PoolResponse.model_validate(payload)
