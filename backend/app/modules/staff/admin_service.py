# =============================================================================
# AIVIS.ONE Backend -- Admin Service (Sprint 3.3, G5 fix, iter 2.6c B1,
#                                    iter 2.7 A5 KYC-in-detail extension,
#                                    H17 P-85 queue removal)
# =============================================================================
#
# RESPONSIBILITIES:
#   list_users()          -- unified user list with pagination + role/kyc_status filter
#   get_user_detail()     -- full user detail for staff view (incl. KYC history)
#   block_user()          -- deactivate user + kill all sessions
#   unblock_user()        -- reactivate a previously blocked user
#   change_user_email()   -- support change of a user's email (admin only)
#   dashboard_stats()     -- platform-wide statistics
#   kyc_decide_application() -- staff decision on a queued application
#   kyc_decide_user()        -- staff decision on a person, with or
#                               without an application row
#
# H17 P-85: kyc_queue() is REMOVED, not paginated. It answered
# GET /staff/kyc/queue, which nothing in the frontend has called since
# iter 2.7 A2 -- the real queue view is list_users(kyc_status=
# 'submitted'), already paginated. See admin_schemas.py's header for
# the fuller account of why deleting rather than fixing was the right
# call here.
#
# PLATFORM EXCLUSION:
#   Platform user (role=platform) is excluded from all user lists and
#   cannot be blocked.
#
# BLOCK RULES:
#   Only non-staff users can be blocked. Staff are trusted.
#   Block sets is_active=false + kills all Redis sessions.
#   Unblock sets is_active=true unconditionally by id -- see
#   unblock_user()'s docstring for why it does not mirror block_user's
#   staff/platform role guards.
#
# iter 2.6c B1:
#   list_users() gains a kyc_status keyword argument. The router
#   validates the enum membership at the FastAPI boundary; the
#   service trusts the incoming string and appends one more clause
#   to base_filter when it is not None. Pagination, role filter,
#   and platform exclusion are unaffected.
#
# iter 2.7 A5 KYC-in-detail extension:
#   get_user_detail() now hydrates three new fields on the response:
#     - latest_application_id      (UUID | None)
#     - latest_application_status  (str | None)
#     - kyc_applications_history   (list[KYCApplicationSummary], up to
#                                    KYC_HISTORY_LIMIT rows, newest first)
#
#   The StaffUsersView detail modal needs the application id to fire
#   Approve / Reject without bouncing through the old StaffKYCView
#   queue page (which was deleted in iter 2.7 A2). The same fetch
#   feeds the "re-submit history" section requested by R1 §3.
#
#   Cost: one extra SELECT per detail view, bounded by
#   KYC_HISTORY_LIMIT (10 rows). No JOIN -- KYCApplication has all
#   we need for the summary schema; user identity is already in the
#   parent response.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms_sync import sync_recipient
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.auth.service import delete_all_sessions
from app.modules.kyc.models import KYCApplication
from app.modules.kyc.service import decide_by_application, decide_by_user
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import Payment
from app.modules.staff.admin_schemas import (
    KYC_HISTORY_LIMIT,
    DashboardStatsResponse,
    KYCApplicationSummary,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
)
from app.modules.staff.models import AvatarSession, AvatarSessionStatus, StaffProfile
from app.modules.staff.schemas import StaffProfileResponse
from app.modules.staff.service import get_effective_permissions
from app.modules.users.models import KYCStatus, User, UserRole

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


def _escape_like(needle: str) -> str:
    """Escape LIKE/ILIKE metacharacters so user input matches literally.

    Mirrors companies/service.py::_escape_like -- not shared cross-module
    (it is a 3-line pure function, and the two call sites filter unrelated
    columns). Order matters: backslash MUST be escaped first, otherwise
    the backslashes just added for % and _ get double-escaped.
    """
    return (
        needle.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _build_staff_profile_response(
    profile: StaffProfile,
) -> StaffProfileResponse:
    """Build StaffProfileResponse with effective permissions."""
    response = StaffProfileResponse.model_validate(profile)
    response.permissions = get_effective_permissions(profile)
    return response


async def _load_kyc_history(
    user_id: UUID,
    session: AsyncSession,
) -> list[KYCApplication]:
    """Load up to KYC_HISTORY_LIMIT newest applications for a user.

    Newest first. Empty list when the user has never submitted KYC
    (a clean investor at registration time, for example -- nothing
    inserts a row into kyc_applications until submit_kyc fires).

    Helper extracted from get_user_detail so the order, limit, and
    filter live in one place. Future callsites (e.g. a per-user KYC
    history endpoint) reuse the same query shape.
    """
    stmt = (
        select(KYCApplication)
        .where(KYCApplication.user_id == user_id)
        .order_by(KYCApplication.created_at.desc())
        .limit(KYC_HISTORY_LIMIT)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


async def list_users(
    session: AsyncSession,
    *,
    role: str | None = None,
    kyc_status: str | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> UserListResponse:
    """List users with pagination and optional role / kyc_status / search filters.

    Platform user is always excluded.
    For staff users, includes StaffProfile with effective permissions.

    iter 2.6c B1: kyc_status is validated to be a KYCStatus enum value
    at the router boundary, so the service accepts a plain string and
    appends it to the base filter when present.

    TASK-30 admin-capability gap: search is a case-insensitive substring
    match across email, first_name, last_name -- all three live in JSONB
    (credentials/profile), not plain columns, so this ORs three `.astext`
    ILIKE clauses rather than filtering one column. Needed by the staff
    user picker (assign-to-company, avatar mode): before this, there was
    no way to find a user's UUID through the product at all.
    """
    # Base filter: exclude platform.
    base_filter = User.role != UserRole.PLATFORM

    if role:
        base_filter = base_filter & (User.role == role)

    if kyc_status is not None:
        base_filter = base_filter & (User.kyc_status == kyc_status)

    if search is not None:
        needle = search.strip()
        if needle:
            pattern = f"%{_escape_like(needle)}%"
            base_filter = base_filter & or_(
                User.credentials["email"]["email"].astext.ilike(pattern, escape="\\"),
                User.profile["first_name"].astext.ilike(pattern, escape="\\"),
                User.profile["last_name"].astext.ilike(pattern, escape="\\"),
            )

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
    """Get full user detail for staff view, including KYC history.

    Platform user cannot be viewed.

    iter 2.7 A5: also surfaces the user's KYC application history
    (up to KYC_HISTORY_LIMIT newest rows, newest first) plus
    convenience fields for the latest application. Used by
    StaffUsersView's detail modal to render Approve / Reject buttons
    without an extra round-trip; the modal reads the id from
    latest_application_id.

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

    # Load staff profile if staff.
    staff_profile = None
    if user.role == UserRole.STAFF:
        sp_stmt = select(StaffProfile).where(StaffProfile.user_id == user.id)
        sp_result = await session.execute(sp_stmt)
        sp = sp_result.scalar_one_or_none()
        if sp:
            staff_profile = _build_staff_profile_response(sp)

    # iter 2.7 A5: hydrate KYC application history.
    #
    # Always materialise the list (never None) so the frontend can
    # iterate without a null check. The UserDetailResponse schema
    # declares this field as required (no default) as of iter 2.7 A5,
    # and we populate it explicitly here for every user.
    #
    # `latest_*` mirrors the head of the list for convenience --
    # the modal renders Approve / Reject from these two fields and
    # avoids re-implementing the "newest first" assumption on the
    # client.
    kyc_apps = await _load_kyc_history(user.id, session)
    history = [
        KYCApplicationSummary.model_validate(app) for app in kyc_apps
    ]
    latest = kyc_apps[0] if kyc_apps else None

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
        latest_application_id=latest.id if latest else None,
        latest_application_status=latest.status if latest else None,
        kyc_applications_history=history,
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

    # comms rechecks `active` before every send, against its own copy
    # (H23 P-113): a block it never hears of does not stop delivery.
    await sync_recipient(session, target)

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


async def unblock_user(
    user_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Unblock a user: set is_active=True. Reverses block_user().

    No session to kill -- a blocked user has none (block_user already
    killed every Redis session, and is_active=False has kept the user
    logged out ever since). Idempotent by the same precedent as
    block_user: neither function checks the current is_active value
    before writing, so unblocking an already-active user is a silent
    no-op success rather than an error.

    No `reason` field: block's reason justifies REVOKING access, a
    judgment call staff must document. Unblock only reverses that
    decision -- the original block's reason (still in its own audit
    row) remains the historical record of why it happened. There is
    nothing new to justify.

    Deliberately does NOT mirror block_user's staff/platform role
    guards ("Cannot block staff/platform user"). Those guards stop a
    block from ever being *placed* on a staff/platform user, so in
    principle an already-blocked user can never be either -- but that
    invariant does not actually hold: create_staff() promotes a user
    to staff without checking is_active, so a blocked investor can be
    promoted to staff while still blocked (and, being blocked, cannot
    log in to notice). For that user, unblocking is the ONLY way back
    to a working account. Rejecting staff/platform here would turn an
    edge case into a permanent lockout instead of preventing one, so
    this function unblocks by id unconditionally.

    Raises:
        NotFoundError: If user not found.
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        raise NotFoundError("User not found")

    target.is_active = True
    await session.flush()

    # The mirror of block_user: comms must see the person active again.
    await sync_recipient(session, target)

    # Audit.
    await record_audit(
        session=session,
        event="user.unblocked",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=target.id,
        data={},
    )

    logger.info(
        "user_unblocked",
        target_user_id=str(target.id),
        staff_id=str(staff.id),
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


# The onboarding keys of the registration verification code
# (auth/service.py::register_email writes them, verify_email_code reads
# them). A code still pending at a change was sent to the OLD address;
# it is removed with the address it belongs to.
_PENDING_EMAIL_CODE_KEYS = (
    "email_token",
    "email_token_expires_at",
    "email_verification_attempts",
)


async def change_user_email(
    user_id: UUID,
    staff: User,
    new_email: str,
    reason: str,
    session: AsyncSession,
) -> None:
    """Change a user's email address -- support only (H28 P-105).

    The caller is a staff admin (the router checks it). The user cannot
    change their own address anywhere in the product: self-service change
    was removed on purpose as account-takeover protection, so an admin
    changing THEIR OWN address is refused here as the same thing.

    The new address is stored lower-cased and stripped, exactly as
    registration stores it, and counts as verified: support sets it after
    establishing the person's identity, there is no confirmation code.
    Sessions are left alone -- the change is made at the user's own
    request -- and nothing is sent to the old address (owner's decision,
    closed with P-104).

    KNOWN CEILING -- a password-reset link sent to the OLD address keeps
    working after the change.
      1. Mechanism: the reset token lives in Redis as password_reset:
         {token} -> {"user_id": ...} (auth/service.py, module note) with
         a 30-minute TTL. The record names the user, not the address the
         link went to, and there is no user -> token index, so nothing
         here can find or void it. Whoever reads the old mailbox can set
         a new password for up to 30 minutes after the change.
      2. Status: acknowledged by design (H28).
      3. Task: none -- it is opened by the trigger below, not scheduled.
      4. Trigger: the first email change requested BECAUSE the old
         mailbox was taken over (the reason given here, in the
         user.email_changed audit row, says so).
      5. Agreed fix: write the address the link was sent to into the
         token record at request time, and refuse the confirm when it
         differs from the user's current address -- one condition in
         confirm_password_reset().
      6. Rejected: a Redis reverse index user -> token voided from here
         (a second structure to keep in step with the token's own TTL);
         killing the user's sessions (does not touch the token at all).

    Raises:
        BadRequestError: own address, platform user, no email to change
            (Telegram-only account -- giving it one would ADD a login
            method, not change one), or the address is the current one.
        NotFoundError: user not found.
        ConflictError: the address belongs to another account.
    """
    if user_id == staff.id:
        raise BadRequestError(
            "Cannot change your own email address -- another admin does it"
        )

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        raise NotFoundError("User not found")

    if target.role == UserRole.PLATFORM:
        raise BadRequestError("Cannot change the email of the platform user")

    old_email = target.email
    if not old_email:
        raise BadRequestError(
            "User has no email address to change (Telegram-only account)"
        )

    email_lower = new_email.strip().lower()
    if email_lower == old_email:
        raise BadRequestError("The new address is the current address")

    # Read first for a clean 409; the unique index ix_users_email below
    # is what actually holds under a concurrent change or registration.
    taken = await session.execute(
        select(User.id).where(
            User.credentials["email"]["email"].as_string() == email_lower,
            User.id != target.id,
        )
    )
    if taken.scalar_one_or_none() is not None:
        raise ConflictError("Email is already registered")

    creds = dict(target.credentials or {})
    email_creds = dict(creds.get("email") or {})
    email_creds["email"] = email_lower
    email_creds["verified"] = True
    email_creds["verified_at"] = datetime.now(UTC).isoformat()
    creds["email"] = email_creds
    if "onboarding" in creds:
        creds["onboarding"] = {
            key: value
            for key, value in dict(creds["onboarding"] or {}).items()
            if key not in _PENDING_EMAIL_CODE_KEYS
        }
    target.set_jsonb("credentials", creds)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "ix_users_email" in str(exc.orig):
            raise ConflictError("Email is already registered") from exc
        raise

    # comms delivers to its own copy of the address: the next letter
    # goes to the new one only after comms holds the new snapshot.
    await sync_recipient(session, target)

    await record_audit(
        session=session,
        event="user.email_changed",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=target.id,
        data={
            "old_email": old_email,
            "new_email": email_lower,
            "reason": reason,
        },
    )

    logger.info(
        "user_email_changed",
        target_user_id=str(target.id),
        staff_id=str(staff.id),
    )


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
        .where(KYCApplication.status == KYCStatus.SUBMITTED)
    )
    pending_kyc = (await session.execute(kyc_stmt)).scalar_one()

    # Active avatar sessions.
    avatar_stmt = (
        select(func.count())
        .select_from(AvatarSession)
        .where(AvatarSession.status == AvatarSessionStatus.ACTIVE)
    )
    active_avatars = (await session.execute(avatar_stmt)).scalar_one()

    # Frozen payments (money in flight, awaiting the confirmation daemon).
    frozen_payments_stmt = (
        select(func.count())
        .select_from(Payment)
        .where(Payment.status == PaymentStatus.FROZEN)
    )
    frozen_payments = (await session.execute(frozen_payments_stmt)).scalar_one()

    return DashboardStatsResponse(
        total_users=total,
        users_by_role=users_by_role,
        pending_kyc_count=pending_kyc,
        active_avatar_sessions=active_avatars,
        frozen_payments_count=frozen_payments,
    )


async def kyc_decide_application(
    application_id: UUID,
    new_status: str,
    staff: User,
    session: AsyncSession,
    *,
    reason: str,
) -> None:
    """Approve or reject a queued application. Reason is mandatory.

    Thin on purpose: the status write, the audit row carrying who and
    why, and the notification all live in kyc.service, so this path and
    the person-level path below cannot drift apart.

    Raises:
        NotFoundError: application or its user not found.
        ConflictError: the application already has a decision.
    """
    await decide_by_application(
        application_id=application_id,
        new_status=new_status,
        reason=reason,
        actor_id=staff.id,
        session=session,
    )

    logger.info(
        "kyc_decided_by_staff",
        application_id=str(application_id),
        new_status=new_status,
        staff_id=str(staff.id),
    )


async def kyc_decide_user(
    user_id: UUID,
    new_status: str,
    staff: User,
    session: AsyncSession,
    *,
    reason: str,
) -> None:
    """Approve or revoke for a PERSON, application row or not.

    The queue can only offer applications, and the two flows this
    serves have none: an old user arriving under a new address (no
    submission, and they cannot make one -- submitting costs money and
    this does not), and withdrawing an approval already given.

    Raises:
        NotFoundError: user not found.
        ConflictError: already approved, or revoking someone not approved.
    """
    await decide_by_user(
        user_id=user_id,
        new_status=new_status,
        reason=reason,
        actor_id=staff.id,
        session=session,
    )

    logger.info(
        "kyc_decided_by_staff_for_user",
        user_id=str(user_id),
        new_status=new_status,
        staff_id=str(staff.id),
    )

