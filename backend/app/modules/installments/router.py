# =============================================================================
# CBSHOME Backend -- Installment Router (Sprint 6.2, G4 fix)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/products/{id}/installment -- create installment plan
#   GET  /api/v1/installments/me           -- list my plans
#   GET  /api/v1/installments/{id}         -- plan detail with tranches
#
# AUTH:
#   All endpoints require authenticated buyer (role=investor or role=agent).
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session manages it.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.installments.schemas import (
    CreateInstallmentPlanRequest,
    InstallmentPlanDetailResponse,
    InstallmentPlanListResponse,
    InstallmentPlanResponse,
    InstallmentTrancheResponse,
)
from app.modules.installments.service import (
    create_plan,
    get_investor_plans,
    get_plan_detail,
)
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

# Two routers: one for plan creation (nested under products),
# one for plan queries (top-level /installments).
create_router = APIRouter(prefix="/api/v1/products", tags=["installments"])
query_router = APIRouter(prefix="/api/v1/installments", tags=["installments"])

# Roles allowed to create and manage installment plans.
_BUYER_ROLES = {UserRole.INVESTOR, UserRole.AGENT}


def _require_buyer(user: User) -> None:
    """Raise ForbiddenError if user is not a buyer (investor or agent)."""
    if user.role not in _BUYER_ROLES:
        raise ForbiddenError("Only investors and agents can manage installment plans")


# ---------------------------------------------------------------------------
# POST /api/v1/products/{id}/installment
# ---------------------------------------------------------------------------


@create_router.post(
    "/{product_id}/installment",
    response_model=InstallmentPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_installment_plan(
    product_id: UUID,
    body: CreateInstallmentPlanRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> InstallmentPlanResponse:
    """Create an installment plan for a product.

    Investor selects a ProductInstallment template. Plan_config is
    snapshot-copied, tranches are expanded. First tranche is paid
    by the daemon (not immediately).

    Requires: authenticated investor or agent.
    """
    _require_buyer(user)

    plan = await create_plan(
        product_id=product_id,
        product_installment_id=body.product_installment_id,
        investor=user,
        session=session,
        referral_link_id=body.referral_link_id,
    )

    return InstallmentPlanResponse.model_validate(plan)


# ---------------------------------------------------------------------------
# GET /api/v1/installments/me
# ---------------------------------------------------------------------------


@query_router.get(
    "/me",
    response_model=InstallmentPlanListResponse,
)
async def list_my_plans(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> InstallmentPlanListResponse:
    """List installment plans for the authenticated buyer."""
    _require_buyer(user)

    plans, total = await get_investor_plans(
        investor_id=user.id,
        session=session,
        page=page,
        per_page=per_page,
    )

    return InstallmentPlanListResponse(
        items=[InstallmentPlanResponse.model_validate(p) for p in plans],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/installments/{id}
# ---------------------------------------------------------------------------


@query_router.get(
    "/{plan_id}",
    response_model=InstallmentPlanDetailResponse,
)
async def get_plan_detail_endpoint(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> InstallmentPlanDetailResponse:
    """Get installment plan detail with tranches.

    Only accessible by the plan owner.
    """
    _require_buyer(user)

    plan, tranches = await get_plan_detail(
        plan_id=plan_id,
        investor_id=user.id,
        session=session,
    )

    resp = InstallmentPlanDetailResponse.model_validate(plan)
    resp.tranches = [
        InstallmentTrancheResponse.model_validate(t) for t in tranches
    ]
    return resp
