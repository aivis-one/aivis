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
#   POST  /api/v1/users/me/email-change         -- Request an email change
#                                                   (TASK-38, avatar-blocked)
#   POST  /api/v1/users/me/email-change/resend  -- Resend the change code
#   POST  /api/v1/users/me/email-change/confirm -- Confirm with the code
#   POST  /api/v1/users/me/deactivate     -- Self-deactivate (TASK-38,
#                                             avatar-blocked)
#
# TD-029 PATTERN:
#   PATCH/PUT/POST use get_current_user_write (write session). Both the
#   dependency and the router declare Depends(get_db_session), so FastAPI
#   reuses the same session instance -- one DB connection, no merge needed.
#
# GET uses get_current_user (read-only session) -- no extra DB query,
# user is already loaded by the dependency.
#
# AVATAR GUARD (TASK-38, R49):
#   change_email and delete_account were pre-declared in
#   avatar_guard.RESTRICTED_OPERATIONS with no live endpoint yet. Now
#   that they exist: forbid_avatar("change_email") guards the REQUEST
#   step only (POST /me/email-change), not resend/confirm -- mirrors
#   create_withdrawal being guarded at creation, not at any later step.
#   forbid_avatar("delete_account") guards the single deactivate
#   endpoint. Both also require the caller's current password
#   (_require_current_password in users/service.py) -- belt AND
#   suspenders, since avatar mode does not hand staff the target's real
#   password.
# =============================================================================

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.rate_limit import check_rate_limit
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.users.models import User
from app.modules.users.schemas import (
    ConfirmEmailChangeRequest,
    DeactivateAccountRequest,
    PayoutDetailsResponse,
    RequestEmailChangeRequest,
    ResendEmailChangeRequest,
    SelectRoleRequest,
    UpdatePayoutDetailsRequest,
    UserResponse,
    UserUpdate,
)
from app.modules.users.service import (
    build_user_response,
    confirm_email_change,
    deactivate_own_account,
    request_email_change,
    resend_email_change_code,
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


# ---------------------------------------------------------------------------
# Email change (TASK-38)
# ---------------------------------------------------------------------------


@router.post(
    "/me/email-change",
    status_code=status.HTTP_204_NO_CONTENT,
    # R49: an avatar must not be able to move the account onto an email
    # only it controls. See router header note for why only this step
    # (not resend/confirm) carries the guard.
    dependencies=[Depends(forbid_avatar("change_email"))],
)
async def request_email_change_endpoint(
    body: RequestEmailChangeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Request an email change. Rate-limited (auth_rate_limit_max_requests
    per auth_rate_limit_window_seconds, the same shared default every
    other check_rate_limit call in this codebase uses when not
    overridden -- 5 per 60s out of the box, not a bespoke 1-per-60s;
    stated as the setting name, not a hardcoded figure, so this
    docstring cannot go stale if the default is ever tuned).

    Requires the current password (re-auth) and sends a 6-digit code to
    the NEW address -- the active login email is untouched until the
    code is confirmed via POST /me/email-change/confirm.
    """
    await check_rate_limit(f"email_change_request:{user.id}")
    await request_email_change(
        user, body.current_password, body.new_email, session, background_tasks
    )


@router.post(
    "/me/email-change/resend",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def resend_email_change_endpoint(
    body: ResendEmailChangeRequest,  # empty body, kept for OpenAPI parity
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Resend the pending email-change code. Rate-limited via the same
    shared auth_rate_limit_max_requests/window_seconds default as the
    request step above (5 per 60s out of the box, not a bespoke 1)."""
    await check_rate_limit(f"email_change_resend:{user.id}")
    await resend_email_change_code(user, session, background_tasks)


@router.post(
    "/me/email-change/confirm",
    response_model=UserResponse,
)
async def confirm_email_change_endpoint(
    body: ConfirmEmailChangeRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Confirm the pending email change with its 6-digit code."""
    updated = await confirm_email_change(user, body.code, session)
    return await build_user_response(updated, session)


# ---------------------------------------------------------------------------
# Self-deactivation (TASK-38)
# ---------------------------------------------------------------------------


@router.post(
    "/me/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    # R49: an avatar must not be able to deactivate the account it is
    # impersonating.
    dependencies=[Depends(forbid_avatar("delete_account"))],
)
async def deactivate_account_endpoint(
    body: DeactivateAccountRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Self-deactivate the account. Requires the current password.

    Soft/reversible: is_active=False + credentials.account.deactivated_by
    ="self" (see users/service.py module note). Kills every session --
    the caller's own request included, since the token dies with it.
    """
    await deactivate_own_account(user, body.current_password, session)
