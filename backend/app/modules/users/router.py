# =============================================================================
# AIVIS.ONE Backend -- Users Router (Sprint 1.3, Sprint 6.3, F2.3)
# =============================================================================
#
# ENDPOINTS:
#   GET   /api/v1/users/me                -- Get current user profile
#   PATCH /api/v1/users/me                -- Update current user profile
#   POST  /api/v1/users/me/select-role    -- Select role during onboarding (F2.3)
#   GET   /api/v1/users/me/payout-details -- Get payout details (Sprint 6.3)
#   PUT   /api/v1/users/me/payout-details -- Set payout details (Sprint 6.3)
#
# TD-029 PATTERN:
#   PATCH/PUT/POST use get_current_user_write (write session). Both the
#   dependency and the router declare Depends(get_db_session), so FastAPI
#   reuses the same session instance -- one DB connection, no merge needed.
#
# GET uses get_current_user (read-only session) -- no extra DB query,
# user is already loaded by the dependency.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.users.models import User
from app.modules.users.schemas import (
    PayoutDetailsResponse,
    SelectRoleRequest,
    UpdatePayoutDetailsRequest,
    UserResponse,
    UserUpdate,
)
from app.modules.users.service import (
    build_user_response,
    select_role,
    update_payout_details,
    update_user,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> UserResponse:
    """Return the authenticated user's profile.

    User object is loaded by get_current_user dependency (read-only session).

    iter 2.6c B6: staff users get an additional `staff_profile` block
    with the effective permission matrix. The session is reused for the
    StaffProfile SELECT inside build_user_response -- one extra query
    for staff, none for everyone else.

    The session parameter is declared unconditionally even though
    non-staff calls never query through it. FastAPI's Depends caching
    reuses the SAME session instance already opened by
    get_current_user, so there is no second connection or pool hit;
    the line exists for the staff branch inside build_user_response,
    and for surface consistency with PATCH /me + POST /me/select-role
    which already needed the write session for their own writes.
    """
    return await build_user_response(user, session)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update the authenticated user's profile.

    TD-029: get_current_user_write and Depends(get_db_session) share
    the same session instance (FastAPI caches Depends within a request).
    The user is already bound to the write session -- no merge needed.

    Only fields present in the request body are updated (exclude_unset).

    iter 2.6c B6: response carries staff_profile for staff callers via
    build_user_response. Staff users PATCHing their own /me is rare but
    legal; the same session is reused for the StaffProfile SELECT.
    """
    updated = await update_user(user, body, session)
    return await build_user_response(updated, session)


# ---------------------------------------------------------------------------
# Role selection (F2.3 -- Onboarding)
# ---------------------------------------------------------------------------


@router.post("/me/select-role", response_model=UserResponse)
async def select_role_endpoint(
    body: SelectRoleRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Select a role during onboarding.

    Only allowed when onboarding_step == profile_complete.
    Changes user.role and advances onboarding to role_selected.

    iter 2.6c B6: response uses build_user_response. The target role
    is restricted to investor by SelectRoleRequest (TASK-30 gap fix --
    agent/company are no longer self-selectable, see admin capability
    gap note there), so staff_profile in this response will always be
    None in practice -- we pipe through build_user_response anyway for
    surface consistency.
    """
    updated = await select_role(user, body.role, session)
    return await build_user_response(updated, session)


# ---------------------------------------------------------------------------
# Payout details (Sprint 6.3)
# ---------------------------------------------------------------------------


@router.get("/me/payout-details", response_model=PayoutDetailsResponse)
async def get_payout_details(
    user: User = Depends(get_current_user),
) -> PayoutDetailsResponse:
    """Return the authenticated user's payout details."""
    return PayoutDetailsResponse(payout_details=user.payout_details)


@router.put("/me/payout-details", response_model=PayoutDetailsResponse)
async def set_payout_details(
    body: UpdatePayoutDetailsRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> PayoutDetailsResponse:
    """Set the authenticated user's payout details (full replacement)."""
    updated = await update_payout_details(user, body.payout_details, session)
    return PayoutDetailsResponse(payout_details=updated.payout_details)
