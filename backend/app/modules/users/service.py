# =============================================================================
# AIVIS.ONE Backend -- Users Service (Sprint 1.3, fix TD-024, Sprint 6.3, F2.3, F4.4 B5)
# =============================================================================
#
# RESPONSIBILITIES:
#   update_user()           -- partial profile update via PATCH /users/me
#   select_role()           -- onboarding role selection (F2.3)
#   update_payout_details() -- set withdrawal payment methods (Sprint 6.3)
#   build_user_response()   -- iter 2.6c B6: assemble UserResponse with
#                              staff_profile hydrated for staff users
#
# PARTIAL UPDATE STRATEGY:
#   Uses Pydantic model_dump(exclude_unset=True) to distinguish between
#   "field not sent" (absent from dict) and "field set to null" (present
#   with None value). This allows:
#     - Omitted fields: untouched
#     - Explicit null: rejected for NOT NULL columns (language)
#     - Explicit value: applied
#
# JSONB MUTATION:
#   profile is updated via set_jsonb() (JSONBMixin) which calls
#   flag_modified() internally. Direct assignment would silently
#   skip the DB write.
#
# REFRESH AFTER FLUSH:
#   After set_jsonb + flush, SQLAlchemy marks updated_at as expired.
#   session.refresh() reloads it to prevent MissingGreenlet when
#   Pydantic model_validate reads the attribute synchronously.
#
# PROFILE KEY WHITELIST (TD-024):
#   Only allowed keys are accepted in profile JSONB. Prevents mass
#   assignment of arbitrary keys (e.g. "is_admin", "role", "__proto__").
#
# F4.4 B5:
#   Added "marketing_consent" to the whitelist. Stores the investor's
#   opt-in for marketing communications as a boolean under
#   profile.marketing_consent. GDPR-style opt-in -- default absent
#   (treated as false); the UI toggle in InvestorSettingsView flips
#   it via PATCH /users/me. Not part of _REQUIRED_PROFILE_FIELDS, so
#   it does not affect onboarding step progression.
#
# AUDIT:
#   Profile changes are recorded in audit_log for compliance.
#   Country and phone changes are especially significant for
#   financial platform AML/KYC requirements.
# =============================================================================

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import structlog
from cryptography.fernet import InvalidToken
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.modules.auth.service import (
    delete_all_sessions,
    hash_password,
    verify_password,
    verify_totp_or_backup_code,
)
from app.modules.staff.schemas import StaffProfileResponse
from app.modules.staff.service import (
    get_effective_permissions,
    get_staff_profile,
)
from app.modules.users.models import OnboardingStep, User, UserRole
from app.modules.users.schemas import UserResponse, UserUpdate

logger = structlog.get_logger()

# Whitelist of allowed keys in profile JSONB (TD-024).
# Any key not in this set is rejected with 400.
_ALLOWED_PROFILE_KEYS = frozenset({
    "first_name",
    "last_name",
    "country",
    "phone",
    "avatar_url",
    "marketing_consent",
})

# Profile fields required to advance to profile_complete step.
_REQUIRED_PROFILE_FIELDS = frozenset({"first_name", "last_name", "country"})

# Email-change verification constants (TASK-38). Same shape as
# auth/service.py's onboarding email verification (10 min TTL, 5
# attempts) -- deliberately duplicated rather than imported so the two
# flows (initial signup verification vs. changing an existing,
# already-verified email) stay independently tunable.
_EMAIL_CHANGE_CODE_TTL_MINUTES = 10
_EMAIL_CHANGE_MAX_ATTEMPTS = 5

# Two-Factor Authentication (TOTP) constants (TASK-38).
_TOTP_ISSUER = "AIVIS.ONE"
# Backup codes: generated once, at confirm_totp_setup() success, hashed
# with the same argon2 wrappers passwords use (hash_password/
# verify_password imported above -- no second hashing scheme). 10 is
# enough that a user spending one every so often (a lost device, a
# reinstalled authenticator app) across years does not run out, without
# printing an unreasonably long list.
_TOTP_BACKUP_CODE_COUNT = 10
_TOTP_BACKUP_CODE_LENGTH = 10
# Excludes 0/O/1/I/L -- visually ambiguous in a printed/handwritten
# recovery-code context, where the whole point is that the user can
# still type one correctly weeks later from a piece of paper.
_TOTP_BACKUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------------------
# Response assembly (iter 2.6c B6)
# ---------------------------------------------------------------------------


async def build_user_response(
    user: User,
    session: AsyncSession,
) -> UserResponse:
    """Build a UserResponse, hydrating staff_profile for staff users.

    For users with `role == "staff"` this loads the StaffProfile row
    and surfaces the EFFECTIVE permission matrix -- DEFAULT permissions
    merged with per-staff overrides via get_effective_permissions(). The
    frontend Staff Platform tab keys off `staff_profile` to gate the
    whole surface, so the GET /me response is the single source of
    truth at session-bootstrap time.

    Non-staff users (investor, agent, company, etc.) get
    `staff_profile = None`.

    The 3 lines that mint the StaffProfileResponse mirror
    `staff.admin_service._build_staff_profile_response`. We deliberately
    re-implement them here rather than importing the underscored helper
    -- `users.service` only consumes public API surfaces of staff
    (`get_staff_profile`, `get_effective_permissions`, `StaffProfileResponse`),
    so a future refactor inside admin_service doesn't ripple here.

    The lookup is a no-op when role isn't staff -- one cheap branch,
    one SELECT in the staff case. Acceptable on GET /me which already
    sits behind an authenticated session lookup.

    Args:
        user: The authenticated user (any role).
        session: Read or write session -- this function only SELECTs.

    Returns:
        UserResponse with staff_profile populated for staff users.
    """
    response = UserResponse.model_validate(user)

    if user.role == UserRole.STAFF:
        profile = await get_staff_profile(user.id, session)
        if profile is not None:
            sp_response = StaffProfileResponse.model_validate(profile)
            sp_response.permissions = get_effective_permissions(profile)
            response.staff_profile = sp_response

    return response


async def update_user(
    user: User,
    body: UserUpdate,
    session: AsyncSession,
) -> User:
    """Partial update of user profile.

    Only fields present in the request body are updated.
    Does NOT commit -- caller manages transaction (P-01).

    Args:
        user: User object bound to the write session (TD-029).
        body: Pydantic model with optional fields.
        session: Write session (same as user is bound to).

    Returns:
        Updated User object with refreshed attributes.

    Raises:
        BadRequestError: If language is explicitly set to null,
            or if profile contains unknown keys.
    """
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        # Empty body -- nothing to update.
        return user

    # language: NOT NULL column -- reject explicit null.
    if "language" in updates and updates["language"] is None:
        raise BadRequestError("language cannot be set to null")

    # Apply language if provided.
    if "language" in updates:
        user.language = updates["language"]

    # Apply profile if provided (merge with existing JSONB).
    if "profile" in updates and updates["profile"] is not None:
        incoming = updates["profile"]

        # TD-024: reject unknown keys to prevent mass assignment.
        extra = set(incoming.keys()) - _ALLOWED_PROFILE_KEYS
        if extra:
            raise BadRequestError(
                f"Unknown profile keys: {sorted(extra)}"
            )

        merged = dict(user.profile)
        merged.update(incoming)
        user.set_jsonb("profile", merged)

    # Advance onboarding step if profile requirements are met.
    if user.onboarding_step == OnboardingStep.EMAIL_VERIFIED:
        profile = user.profile or {}
        if all(profile.get(f) for f in _REQUIRED_PROFILE_FIELDS):
            user.onboarding_step = OnboardingStep.PROFILE_COMPLETE

    await session.flush()
    # Reload expired attrs (updated_at) after potential set_jsonb + flush.
    await session.refresh(user)

    # Audit: profile changes are compliance-significant
    # (country, phone affect AML/KYC).
    await record_audit(
        session=session,
        event="user.profile_updated",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"fields": list(updates.keys())},
    )

    logger.info(
        "user_profile_updated",
        user_id=str(user.id),
        fields=list(updates.keys()),
    )

    return user


# ---------------------------------------------------------------------------
# Role selection (F2.3 -- Onboarding)
# ---------------------------------------------------------------------------


async def select_role(
    user: User,
    role: str,
    session: AsyncSession,
) -> User:
    """Select a role during onboarding.

    Only allowed when onboarding_step == profile_complete.
    Changes user.role and advances to role_selected.

    Args:
        user: User object bound to write session.
        role: Target role. Only "investor" passes SelectRoleRequest
              validation (TASK-30 gap fix) -- agent/company are no
              longer self-selectable.
        session: Write session.

    Returns:
        Updated User with refreshed attributes.

    Raises:
        BadRequestError: If onboarding_step is not profile_complete.
    """
    if user.onboarding_step != OnboardingStep.PROFILE_COMPLETE:
        raise BadRequestError(
            f"Role selection requires onboarding_step=profile_complete "
            f"(current: {user.onboarding_step})"
        )

    old_role = user.role
    user.role = role
    user.onboarding_step = OnboardingStep.ROLE_SELECTED

    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="user.role_selected",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"old_role": old_role, "new_role": role},
    )

    logger.info(
        "user_role_selected",
        user_id=str(user.id),
        old_role=old_role,
        new_role=role,
    )

    return user


# ---------------------------------------------------------------------------
# Payout details (Sprint 6.3)
# ---------------------------------------------------------------------------


async def update_payout_details(
    user: User,
    payout_details: dict[str, Any],
    session: AsyncSession,
) -> User:
    """Replace user's payout details (withdrawal payment methods).

    Full replacement -- not merge. Previous value is overwritten.
    Does NOT commit -- caller manages transaction (P-01).

    Args:
        user: User object bound to write session.
        payout_details: New payout details dict.
        session: Write session.

    Returns:
        Updated User with refreshed attributes.
    """
    user.set_jsonb("payout_details", payout_details)
    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="user.payout_details_updated",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={},
    )

    logger.info(
        "payout_details_updated",
        user_id=str(user.id),
    )

    return user


# ---------------------------------------------------------------------------
# Shared re-authentication helper (TASK-38)
# ---------------------------------------------------------------------------


async def _require_current_password(user: User, password: str) -> None:
    """Re-verify the caller's current password before a sensitive action.

    Used by both request_email_change() and deactivate_own_account() --
    changing the login email and deactivating the account are both
    sensitive enough that a hijacked-but-not-yet-logged-out session
    should not be able to do them silently (see module notes on each
    caller for the specific threat).

    Deliberately raises ForbiddenError (403), NOT UnauthorizedError
    (401): api/client.ts's global 401 handler force-clears the local
    session on ANY 401 response (see frontend/src/api/client.ts's
    `_onUnauthorized?.()` on every 401). The caller's SESSION is still
    valid here -- only this one re-auth check failed -- so a 401 would
    incorrectly log the user out client-side over a mistyped password.
    403 with a distinct code lets the frontend show an inline "wrong
    password" error and keep the session intact, same reasoning as
    login_email()'s account_blocked branch using ForbiddenError instead
    of the generic 401 UnauthorizedError.

    Raises:
        ForbiddenError: Password does not match (code="incorrect_password").
    """
    email_creds = (user.credentials or {}).get("email", {})
    stored_hash = email_creds.get("password_hash", "")

    if not await verify_password(password, stored_hash):
        raise ForbiddenError("Incorrect password", code="incorrect_password")


# ---------------------------------------------------------------------------
# Email change (TASK-38)
# ---------------------------------------------------------------------------
#
# Deliberately NOT folded into UserUpdate/update_user: email lives at
# credentials.email.email, not a plain User column, and swapping the
# LOGIN identifier needs two things update_user has no equivalent for:
#   1. Re-authentication (current password) before the change can even
#      be REQUESTED -- see _require_current_password above.
#   2. Re-verification (a 6-digit code sent to the NEW address) before
#      the change takes effect -- mirrors auth/service.py's onboarding
#      email verification shape (_generate_verification_code, TTL,
#      attempts cap) but stores the pending new email in its OWN JSONB
#      slot, credentials.email_change = {new_email, token, expires_at,
#      attempts}, entirely separate from credentials.email and
#      credentials.onboarding. The active login email
#      (credentials.email.email) is untouched until confirm_email_change
#      succeeds -- a user who never finishes the code step keeps
#      logging in with their old address.
#
# UNIQUENESS: ix_users_email (migration 0002) is a unique index directly
# on credentials->'email'->>'email'. request_email_change() does a
# proactive SELECT for a fast, friendly 409 at request time; the actual
# swap in confirm_email_change() ALSO catches the IntegrityError the
# index raises on flush, same two-layer pattern as register_email() --
# the SELECT is a UX nicety, the index is the real race-safe guarantee
# (two people cannot both finish changing into the same email).


def _generate_email_change_code() -> str:
    """Generate a 6-digit numeric verification code.

    Same shape as auth/service.py's _generate_verification_code --
    duplicated rather than imported to keep the two verification flows
    independently evolvable (see module note above).
    """
    return str(secrets.randbelow(900000) + 100000)


async def _send_email_change_verification_email(email: str, code: str) -> None:
    """Send the email-change verification code. Errors logged, not raised.

    Same fire-and-forget contract as auth/service.py's
    _send_verification_email -- sent to the NEW address (the whole
    point: proving the user controls it before the swap happens).
    """
    from app.core.email import send_email

    try:
        await send_email(
            recipient=email,
            subject="AIVIS.ONE - Confirm Your New Email",
            body=(
                f"Your email change verification code is: {code}\n\n"
                f"This code expires in {_EMAIL_CHANGE_CODE_TTL_MINUTES} "
                "minutes.\n\n"
                "If you did not request this change, you can safely "
                "ignore this email -- your login email will not change."
            ),
        )
    except Exception:
        logger.error(
            "email_change_verification_email_send_failed",
            recipient=email[:3] + "***",
        )


async def request_email_change(
    user: User,
    current_password: str,
    new_email: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """Start an email change: re-auth, uniqueness check, code to the NEW email.

    Does NOT touch credentials.email.email -- see module note above.
    Does NOT commit -- caller (get_db_session) manages the transaction
    (P-01). background_tasks defers the send past that commit, same
    reasoning as register_email.

    Raises:
        ForbiddenError: Current password is wrong (code="incorrect_password").
        BadRequestError: new_email equals the current login email.
        ConflictError: new_email already belongs to another account.
    """
    await _require_current_password(user, current_password)

    new_email_lower = new_email.strip().lower()

    if new_email_lower == (user.email or ""):
        raise BadRequestError("New email must be different from the current email")

    # Proactive check -- see module note (UX nicety, not the race guard).
    existing = await session.execute(
        select(User.id).where(
            User.credentials["email"]["email"].as_string() == new_email_lower,
            User.id != user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Email is already registered")

    code = _generate_email_change_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_EMAIL_CHANGE_CODE_TTL_MINUTES)

    updated_creds = dict(user.credentials or {})
    updated_creds["email_change"] = {
        "new_email": new_email_lower,
        "token": code,
        "expires_at": expires_at.isoformat(),
        "attempts": 0,
    }
    user.set_jsonb("credentials", updated_creds)
    await session.flush()

    await record_audit(
        session=session,
        event="user.email_change_requested",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"new_email": new_email_lower},
    )

    logger.info("email_change_requested", user_id=str(user.id))

    background_tasks.add_task(
        _send_email_change_verification_email, new_email_lower, code
    )


async def resend_email_change_code(
    user: User,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """Regenerate the code, reset TTL and attempts, resend to the pending email.

    Does NOT commit -- caller manages the transaction (P-01).

    Raises:
        BadRequestError: No pending email change on this account.
    """
    email_change = (user.credentials or {}).get("email_change") or {}
    pending_email = email_change.get("new_email")

    if not pending_email:
        raise BadRequestError("No pending email change")

    code = _generate_email_change_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_EMAIL_CHANGE_CODE_TTL_MINUTES)

    updated_creds = dict(user.credentials or {})
    updated_creds["email_change"] = {
        "new_email": pending_email,
        "token": code,
        "expires_at": expires_at.isoformat(),
        "attempts": 0,
    }
    user.set_jsonb("credentials", updated_creds)
    await session.flush()

    logger.info("email_change_code_resent", user_id=str(user.id))

    background_tasks.add_task(
        _send_email_change_verification_email, pending_email, code
    )


async def confirm_email_change(
    user: User,
    code: str,
    session: AsyncSession,
) -> User:
    """Verify the 6-digit code and, on success, swap the login email.

    Checks: pending change exists, attempts limit, TTL, code match.
    On success: credentials.email.email <- pending new_email,
    credentials.email_change cleared. Does NOT commit -- caller manages
    the transaction (P-01).

    Raises:
        BadRequestError: No pending change, too many attempts, expired,
            or wrong code.
        ConflictError: The pending email was claimed by another account
            in the interim (ix_users_email raced -- see module note).
    """
    email_change = (user.credentials or {}).get("email_change") or {}
    pending_email = email_change.get("new_email")

    if not pending_email:
        raise BadRequestError("No pending email change")

    attempts = email_change.get("attempts", 0)
    if attempts >= _EMAIL_CHANGE_MAX_ATTEMPTS:
        raise BadRequestError("Too many attempts, please request a new code")

    expires_at_str = email_change.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(UTC) > expires_at:
            raise BadRequestError("Code expired, please request a new code")

    stored_code = email_change.get("token") or ""
    if not secrets.compare_digest(code, stored_code):
        updated_creds = dict(user.credentials or {})
        updated_creds["email_change"] = dict(email_change)
        updated_creds["email_change"]["attempts"] = attempts + 1
        user.set_jsonb("credentials", updated_creds)
        await session.flush()
        raise BadRequestError("Invalid verification code")

    # Success: swap the active email, clear the pending slot.
    old_email = user.email
    now = datetime.now(UTC)
    updated_creds = dict(user.credentials or {})
    email_creds = dict(updated_creds.get("email", {}))
    email_creds["email"] = pending_email
    email_creds["verified"] = True
    email_creds["verified_at"] = now.isoformat()
    updated_creds["email"] = email_creds
    updated_creds["email_change"] = None
    user.set_jsonb("credentials", updated_creds)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "ix_users_email" in str(exc.orig):
            raise ConflictError("Email is already registered") from exc
        raise

    await session.refresh(user)

    await record_audit(
        session=session,
        event="user.email_changed",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"old_email": old_email, "new_email": pending_email},
    )

    logger.info("email_changed", user_id=str(user.id))

    return user


# ---------------------------------------------------------------------------
# Self-deactivation (TASK-38)
# ---------------------------------------------------------------------------
#
# Deliberately does NOT reuse is_active=False as a bare flag the way
# staff's block_user() (staff/admin_service.py) does -- login_email()
# distinguishes the two via credentials.account.deactivated_by ("self"
# here; absent/anything-else means staff-blocked, block_user() is
# unchanged) so a self-deactivated user gets an honest, distinct
# message instead of "Your account has been suspended" (see
# auth/service.py::login_email for the branch).
#
# SOFT/REVERSIBLE ONLY: is_active=False + the discriminator, full stop.
# No data purge, no row deletion -- "self account deactivate" is a
# UX-parity gap, deliberately separate from the jurisdiction-conditional
# GDPR erasure item tracked elsewhere.
#
# KNOWN EDGE CASE (not fixed here -- block_user/unblock_user are
# read-only reference per this task's scope): if a self-deactivated
# user is later unblocked (unblock_user, is_active=True) and then
# BLOCKED by staff (block_user, is_active=False again), the
# credentials.account.deactivated_by discriminator is still "self" --
# neither function touches it -- so login_email() would show the
# self-deactivated copy for what is actually a staff block. Rare
# (requires that exact sequence) but real; flagged rather than
# silently accepted.


async def deactivate_own_account(
    user: User,
    current_password: str,
    session: AsyncSession,
) -> None:
    """Self-deactivate: re-auth, is_active=False + discriminator, kill sessions.

    Mirrors staff's block_user() for the is_active + session-kill
    mechanics (session, delete_all_sessions, record_audit shape) but
    with actor_type="user" (self-service, not staff action) and a
    distinct event name (user.self_deactivated vs user.blocked).

    Does NOT commit -- caller (get_db_session) manages the transaction
    (P-01). delete_all_sessions() is Redis-only, safe to call before
    that commit lands (same reasoning as confirm_password_reset).

    Raises:
        ForbiddenError: Current password is wrong (code="incorrect_password").
        BadRequestError: Caller is staff or platform (code stays
            "bad_request" -- mirrors block_user()'s "Cannot block staff
            user" / "Cannot block platform user" guards; staff accounts
            are trusted operational accounts, not meant to be able to
            silently lock themselves out through the same self-service
            path an investor uses, and platform never has a live
            session to reach this endpoint from in the first place).
    """
    await _require_current_password(user, current_password)

    if user.role == UserRole.STAFF:
        raise BadRequestError("Staff accounts cannot be self-deactivated")
    if user.role == UserRole.PLATFORM:
        raise BadRequestError("Platform account cannot be self-deactivated")

    now = datetime.now(UTC)
    updated_creds = dict(user.credentials or {})
    updated_creds["account"] = {
        "deactivated_by": "self",
        "deactivated_at": now.isoformat(),
    }
    user.set_jsonb("credentials", updated_creds)
    user.is_active = False
    await session.flush()

    killed = await delete_all_sessions(user.id)

    await record_audit(
        session=session,
        event="user.self_deactivated",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"sessions_killed": killed},
    )

    logger.info(
        "user_self_deactivated",
        user_id=str(user.id),
        sessions_killed=killed,
    )


# ---------------------------------------------------------------------------
# Two-Factor Authentication (TOTP) -- TASK-38
# ---------------------------------------------------------------------------
#
# STORAGE SHAPE (credentials JSONB), mirroring the email_change pending-
# slot precedent above:
#   credentials.totp_pending = {secret_encrypted, created_at}
#     -- written by setup_totp(), cleared/replaced by confirm_totp_setup().
#        A setup abandoned partway (never confirmed) never enables
#        anything -- there is no `enabled` flag in this slot at all.
#   credentials.totp = {
#     secret_encrypted, enabled: true, enabled_at,
#     backup_codes: [{hash, used_at: null|iso}, ...],
#   }
#     -- the ACTIVE slot, written only by confirm_totp_setup(), read by
#        auth/service.py's verify_totp_or_backup_code() on every login
#        and by disable_totp() below. None (not a partial dict) when
#        2FA has never been enabled or was disabled -- callers check
#        `.get("totp") or {}` then `.get("enabled")`, same discipline
#        as credentials.email_change's `or {}` guards above.
#
# `secret_encrypted` is a Fernet token (app/core/crypto.py) -- reversible,
# because a TOTP secret must be usable to COMPUTE a fresh code on every
# login, unlike a password. Backup codes ARE one-way hashed (argon2,
# same hash_password/verify_password as everywhere else) because they
# are compared once and never need to be shown again.
#
# AVATAR GUARD: all three functions below are called from routes
# carrying forbid_avatar("manage_2fa") (auth/router.py + avatar_guard.py)
# -- an avatar setting up, confirming, or disabling 2FA on the real
# owner's account is at least as severe as the disruption-vector class
# already guarded (logout_all/revoke_session/mute_notifications): it
# either plants a second factor only the avatar knows, or strips one
# the real owner relies on, and either persists past the avatar session.


async def setup_totp(
    user: User,
    current_password: str,
    session: AsyncSession,
) -> tuple[str, str]:
    """Start (or restart) TOTP setup: re-auth, generate a secret, store it
    PENDING (not yet enabled), build the provisioning URI.

    Re-callable at any time, including when 2FA is already enabled
    (credentials.totp.enabled=True) -- this only ever writes the PENDING
    slot; the active slot is untouched until confirm_totp_setup()
    succeeds. That makes this endpoint double as a "rotate my secret"
    entry point with no separate rotation flow needed, at the cost of a
    caller being able to leave a stale, never-confirmed pending secret
    behind harmlessly (setup_totp() called again simply overwrites it).

    Does NOT commit -- caller (get_db_session) manages the transaction
    (P-01).

    Returns:
        (secret, provisioning_uri) -- secret is the raw base32 value,
        returned in plaintext ONCE (see TwoFactorSetupResponse's
        docstring) alongside the QR-encodable URI.

    Raises:
        ForbiddenError: current_password does not match
            (code="incorrect_password", via _require_current_password).
    """
    await _require_current_password(user, current_password)

    secret = pyotp.random_base32()
    now = datetime.now(UTC)

    updated_creds = dict(user.credentials or {})
    updated_creds["totp_pending"] = {
        "secret_encrypted": encrypt_secret(secret),
        "created_at": now.isoformat(),
    }
    user.set_jsonb("credentials", updated_creds)
    await session.flush()

    provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email or str(user.id),
        issuer_name=_TOTP_ISSUER,
    )

    await record_audit(
        session=session,
        event="user.2fa_setup_started",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={},
    )

    logger.info("totp_setup_started", user_id=str(user.id))

    return secret, provisioning_uri


def _generate_backup_codes() -> list[str]:
    """Generate _TOTP_BACKUP_CODE_COUNT random alphanumeric codes.

    secrets.choice over a restricted alphabet (see the module constants
    above) -- NOT the `random` module, which is not cryptographically
    secure and must never generate anything that gates account access.
    """
    return [
        "".join(
            secrets.choice(_TOTP_BACKUP_CODE_ALPHABET)
            for _ in range(_TOTP_BACKUP_CODE_LENGTH)
        )
        for _ in range(_TOTP_BACKUP_CODE_COUNT)
    ]


async def confirm_totp_setup(
    user: User,
    code: str,
    session: AsyncSession,
) -> list[str]:
    """Verify a live code against the PENDING secret; on success, generate
    backup codes and switch 2FA on.

    On a WRONG code: the pending secret is left untouched (BadRequestError
    only) so the user can simply retry entering the next code their
    authenticator app shows -- unlike email verification's attempt
    counter, there is no stored attempts field here; POST /2fa/confirm
    is rate-limited per-user instead (auth/router.py).

    On success: generates _TOTP_BACKUP_CODE_COUNT backup codes, hashes
    each via hash_password() (argon2 -- same path as everywhere else),
    writes the ACTIVE slot (secret_encrypted carried over unchanged from
    pending, enabled=true, enabled_at=now, backup_codes=[...]), clears
    the pending slot. Does NOT commit -- caller (get_db_session) manages
    the transaction (P-01).

    THE PLAINTEXT BACKUP CODES ARE RETURNED HERE ONLY. Nothing this
    module stores can reconstruct them afterward -- only their argon2
    hashes persist. The router must return them to the caller verbatim,
    and the frontend must treat that response as the one and only chance
    to save them (see TwoFactorConfirmResponse's docstring).

    Raises:
        BadRequestError: No pending setup, the pending secret is
            undecryptable (corrupted data), or the code does not verify.
    """
    totp_pending = (user.credentials or {}).get("totp_pending") or {}
    secret_encrypted = totp_pending.get("secret_encrypted")

    if not secret_encrypted:
        raise BadRequestError("No pending 2FA setup. Call /2fa/setup first.")

    try:
        secret = decrypt_secret(secret_encrypted)
    except InvalidToken as exc:
        # Corrupted pending secret -- cannot be the user's fault. Clear
        # it so a retry from /2fa/setup starts clean rather than
        # re-hitting the same undecryptable value forever.
        logger.error("totp_pending_secret_undecryptable", user_id=str(user.id))
        updated_creds = dict(user.credentials or {})
        updated_creds["totp_pending"] = None
        user.set_jsonb("credentials", updated_creds)
        await session.flush()
        raise BadRequestError(
            "Your pending 2FA setup is invalid. Please start setup again."
        ) from exc

    if not pyotp.totp.TOTP(secret).verify(code, valid_window=1):
        logger.warning("totp_confirm_wrong_code", user_id=str(user.id))
        raise BadRequestError("Invalid verification code")

    backup_codes = _generate_backup_codes()
    now = datetime.now(UTC)

    updated_creds = dict(user.credentials or {})
    updated_creds["totp"] = {
        "secret_encrypted": secret_encrypted,
        "enabled": True,
        "enabled_at": now.isoformat(),
        "backup_codes": [
            {"hash": await hash_password(plain), "used_at": None}
            for plain in backup_codes
        ],
    }
    updated_creds["totp_pending"] = None
    user.set_jsonb("credentials", updated_creds)
    await session.flush()

    await record_audit(
        session=session,
        event="user.2fa_enabled",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"backup_codes_issued": len(backup_codes)},
    )

    logger.info("totp_enabled", user_id=str(user.id))

    return backup_codes


async def disable_totp(
    user: User,
    current_password: str,
    code: str,
    session: AsyncSession,
) -> None:
    """Turn 2FA off: BOTH the current password AND a live code (or an
    unused backup code) are required -- see TwoFactorDisableRequest's
    docstring for why either/or is not enough.

    consume_backup_code=False when checking the code: the entire
    credentials.totp slot is cleared unconditionally on success a few
    lines below, so marking one backup code used_at first would be
    wasted work on a dict about to be discarded.

    Does NOT commit -- caller (get_db_session) manages the transaction
    (P-01).

    Raises:
        ForbiddenError: current_password does not match
            (code="incorrect_password").
        BadRequestError: 2FA is not enabled on this account, or `code`
            does not verify against the active secret or any unused
            backup code.
    """
    await _require_current_password(user, current_password)

    totp_creds = (user.credentials or {}).get("totp") or {}
    if not totp_creds.get("enabled"):
        raise BadRequestError("Two-factor authentication is not enabled")

    if not await verify_totp_or_backup_code(
        user, code, session, consume_backup_code=False
    ):
        logger.warning("totp_disable_wrong_code", user_id=str(user.id))
        raise BadRequestError("Invalid verification code")

    updated_creds = dict(user.credentials or {})
    updated_creds["totp"] = None
    updated_creds["totp_pending"] = None
    user.set_jsonb("credentials", updated_creds)
    await session.flush()

    await record_audit(
        session=session,
        event="user.2fa_disabled",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={},
    )

    logger.info("totp_disabled", user_id=str(user.id))
