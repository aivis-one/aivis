# =============================================================================
# CBSHOME Backend -- Admin Service (Sprint 3.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   list_users()          -- unified user list with pagination + role filter
#   get_user_detail()     -- full user detail for staff view
#   block_user()          -- deactivate user + kill all sessions
#   dashboard_stats()     -- platform-wide statistics
#   kyc_queue()           -- pending KYC applications with user info
#   kyc_approve()         -- approve KYC application (delegates to process_webhook)
#   kyc_reject()          -- reject KYC application (delegates to process_webhook)
#
# PLATFORM EXCLUSION:
#   Platform user (role=platform) is excluded from all user lists and
#   cannot be blocked.
#
# BLOCK RULES:
#   Only non-staff users can be blocked. Staff are trusted.
#   Block sets is_active=false + kills all Redis sessions.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.auth.service import delete_all_sessions
from app.modules.kyc.models import KYCApplication, KYCApplicationStatus
from app.modules.kyc.service import process_webhook
from app.modules.staff.admin_schemas import (
    DashboardStatsResponse,
    KYCQueueItem,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
)
from app.modules.staff.models import AvatarSession, AvatarSessionStatus, StaffProfile
from app.modules.staff.schemas import StaffProfileResponse
from app.modules.staff.service import get_effective_permissions
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_user_email(user: User) -> str | None:
    """Extract email from User.credentials JSONB."""
    if user.credentials and "email" in user.credentials:
        return user.credentials["email"].get("email")
    return None


def _extract_user_name(user: User) -> tuple[str | None, str | None]:
    """Extract first_name, last_name from User.profile JSONB."""
    if user.profile:
        return user.profile.get("first_name"), user.profile.get("last_name")
    return None, None


def _build_staff_profile_response(
    profile: StaffProfile,
) -> StaffProfileResponse:
    """Build StaffProfileResponse with effective permissions."""
    response = StaffProfileResponse.model_validate(profile)
    response.permissions = get_effective_permissions(profile)
    return response


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


async def list_users(
    session: AsyncSession,
    *,
    role: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> UserListResponse:
    """List users with pagination and optional role filter.

    Platform user is always excluded.
    For staff users, includes StaffProfile with effective permissions.
    """
    # Base filter: exclude platform.
    base_filter = User.role != UserRole.PLATFORM

    if role:
        base_filter = base_filter & (User.role == role)

    # Count total.
    count_stmt = select(func.count()).select_from(User).where(base_filter)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(User)
        .where(base_filter)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    users = result.scalars().all()

    # Load staff profiles for staff users in this page.
    staff_user_ids = [u.id for u in users if u.role == UserRole.STAFF]
    staff_profiles: dict[UUID, StaffProfile] = {}

    if staff_user_ids:
        sp_stmt = select(StaffProfile).where(
            StaffProfile.user_id.in_(staff_user_ids)
        )
        sp_result = await session.execute(sp_stmt)
        for profile in sp_result.scalars().all():
            staff_profiles[profile.user_id] = profile

    # Build response items.
    items = []
    for user in users:
        email = _extract_user_email(user)
        first_name, last_name = _extract_user_name(user)

        staff_profile = None
        if user.id in staff_profiles:
            staff_profile = _build_staff_profile_response(staff_profiles[user.id])

        items.append(UserListItem(
            id=user.id,
            role=user.role,
            is_active=user.is_active,
            kyc_status=user.kyc_status,
            email=email,
            first_name=first_name,
            last_name=last_name,
            created_at=user.created_at,
            staff_profile=staff_profile,
        ))

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


async def get_user_detail(
    user_id: UUID,
    session: AsyncSession,
) -> UserDetailResponse:
    """Get full user detail for staff view.

    Platform user cannot be viewed.

    Raises:
        NotFoundError: If user not found or is platform.
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise NotFoundError("User not found")

    if user.role == UserRole.PLATFORM:
        raise NotFoundError("User not found")

    email = _extract_user_email(user)
    first_name, last_name = _extract_user_name(user)

    # Load staff profile if staff.
    staff_profile = None
    if user.role == UserRole.STAFF:
        sp_stmt = select(StaffProfile).where(StaffProfile.user_id == user.id)
        sp_result = await session.execute(sp_stmt)
        sp = sp_result.scalar_one_or_none()
        if sp:
            staff_profile = _build_staff_profile_response(sp)

    return UserDetailResponse(
        id=user.id,
        role=user.role,
        is_active=user.is_active,
        onboarding_step=user.onboarding_step,
        kyc_status=user.kyc_status,
        profile=user.profile,
        language=user.language,
        created_at=user.created_at,
        updated_at=user.updated_at,
        email=email,
        staff_profile=staff_profile,
    )


async def block_user(
    user_id: UUID,
    staff: User,
    reason: str | None,
    session: AsyncSession,
) -> None:
    """Block a user: set is_active=False + kill all Redis sessions.

    Only non-staff users can be blocked. Staff are trusted.

    Raises:
        NotFoundError: If user not found.
        BadRequestError: If user is staff or platform.
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        raise NotFoundError("User not found")

    if target.role == UserRole.STAFF:
        raise BadRequestError("Cannot block staff user")

    if target.role == UserRole.PLATFORM:
        raise BadRequestError("Cannot block platform user")

    target.is_active = False
    await session.flush()

    # Kill all Redis sessions.
    killed = await delete_all_sessions(target.id)

    # Audit.
    await record_audit(
        session=session,
        event="user.blocked",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=target.id,
        data={"reason": reason, "sessions_killed": killed},
    )

    logger.info(
        "user_blocked",
        target_user_id=str(target.id),
        staff_id=str(staff.id),
        sessions_killed=killed,
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


async def dashboard_stats(
    session: AsyncSession,
) -> DashboardStatsResponse:
    """Platform-wide statistics for staff dashboard."""
    # Total users (exclude platform).
    total_stmt = (
        select(func.count())
        .select_from(User)
        .where(User.role != UserRole.PLATFORM)
    )
    total = (await session.execute(total_stmt)).scalar_one()

    # Users by role (exclude platform).
    role_stmt = (
        select(User.role, func.count())
        .where(User.role != UserRole.PLATFORM)
        .group_by(User.role)
    )
    role_result = await session.execute(role_stmt)
    users_by_role = {row[0]: row[1] for row in role_result.all()}

    # Pending KYC count.
    kyc_stmt = (
        select(func.count())
        .select_from(KYCApplication)
        .where(KYCApplication.status == KYCApplicationStatus.SUBMITTED)
    )
    pending_kyc = (await session.execute(kyc_stmt)).scalar_one()

    # Active avatar sessions.
    avatar_stmt = (
        select(func.count())
        .select_from(AvatarSession)
        .where(AvatarSession.status == AvatarSessionStatus.ACTIVE)
    )
    active_avatars = (await session.execute(avatar_stmt)).scalar_one()

    return DashboardStatsResponse(
        total_users=total,
        users_by_role=users_by_role,
        pending_kyc_count=pending_kyc,
        active_avatar_sessions=active_avatars,
    )


# ---------------------------------------------------------------------------
# KYC queue
# ---------------------------------------------------------------------------


async def kyc_queue(
    session: AsyncSession,
) -> list[KYCQueueItem]:
    """List pending KYC applications with basic user info."""
    stmt = (
        select(KYCApplication, User)
        .join(User, KYCApplication.user_id == User.id)
        .where(KYCApplication.status == KYCApplicationStatus.SUBMITTED)
        .order_by(KYCApplication.created_at.asc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    items = []
    for application, user in rows:
        email = _extract_user_email(user)
        first_name, last_name = _extract_user_name(user)

        items.append(KYCQueueItem(
            id=application.id,
            user_id=application.user_id,
            status=application.status,
            created_at=application.created_at,
            email=email,
            first_name=first_name,
            last_name=last_name,
        ))

    return items


async def kyc_approve(
    application_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Approve a KYC application. Delegates to process_webhook.

    Raises:
        NotFoundError: If application not found.
    """
    # Load application to get user_id.
    stmt = select(KYCApplication).where(KYCApplication.id == application_id)
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    if application is None:
        raise NotFoundError("KYC application not found")

    await process_webhook(
        user_id=str(application.user_id),
        new_status=KYCApplicationStatus.APPROVED,
        session=session,
    )

    # Staff-specific audit (process_webhook writes system audit separately).
    await record_audit(
        session=session,
        event="kyc.approved_by_staff",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=application.user_id,
        data={"application_id": str(application_id)},
    )

    logger.info(
        "kyc_approved_by_staff",
        application_id=str(application_id),
        staff_id=str(staff.id),
    )


async def kyc_reject(
    application_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Reject a KYC application. Delegates to process_webhook.

    Raises:
        NotFoundError: If application not found.
    """
    # Load application to get user_id.
    stmt = select(KYCApplication).where(KYCApplication.id == application_id)
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    if application is None:
        raise NotFoundError("KYC application not found")

    await process_webhook(
        user_id=str(application.user_id),
        new_status=KYCApplicationStatus.REJECTED,
        session=session,
    )

    # Staff-specific audit (process_webhook writes system audit separately).
    await record_audit(
        session=session,
        event="kyc.rejected_by_staff",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=application.user_id,
        data={"application_id": str(application_id)},
    )

    logger.info(
        "kyc_rejected_by_staff",
        application_id=str(application_id),
        staff_id=str(staff.id),
    )
