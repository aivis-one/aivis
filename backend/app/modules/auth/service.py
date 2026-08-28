# =============================================================================
# AIVIS.ONE Backend -- Auth Service (Sprint 7.2, G1 fix)
# =============================================================================
#
# RESPONSIBILITIES:
#   register_email()              -- create User via email + password
#   login_email()                 -- authenticate by email + password
#   create_session()              -- Redis session with ZSET index
#   delete_session()              -- single session logout
#   delete_all_sessions()         -- logout-all via Lua script
#   upsert_telegram_user()        -- Telegram WebApp auth (Sprint 1.2)
#   verify_email_code()           -- verify 6-digit email code (G1)
#   resend_verification_code()    -- regenerate + resend code (G1)
#   request_password_reset()      -- request a reset link (unauthenticated)
#   confirm_password_reset()      -- consume the reset token, set new password
#
# FAILED LOGIN AUDIT (SEC-7, timing fix TASK-6 4.1c):
#   login_email() records failed attempts in audit_log via a dedicated
#   session (_audit_login_failure). Required because the caller's session
#   is rolled back on exception (P-01), which would discard any audit
#   entries written to the same session. Scheduled via BackgroundTasks
#   instead of awaited: an audit INSERT+COMMIT before the response ran
#   only on the known-email branches, dwarfing the argon2-hash-duration
#   equalizer the unknown-email branch uses -- moving it off the request
#   path removes that gap instead of matching it on the other side.
#   ⚠ AND FOR THE WHOLE LIFE OF THAT DESIGN IT NEVER RAN (STAGE-III finding
#   20, fixed 2026-08-17). All three add_task calls below are followed
#   immediately by a `raise`, and FastAPI attaches BackgroundTasks to the
#   response built from the endpoint's RETURN -- so every one of them was
#   queued onto a response that was thrown away. Measured on the LIVE
#   database: `select count(*) from audit_log where event =
#   'user.login_failed'` -> 0, over the entire deployment. Repaired in
#   app/core/background.py, which is where the mechanism is explained;
#   DO NOT "simplify" these three calls into awaits -- that trades this
#   hole for the 4.1c timing oracle described above.
#
# REFERRAL (Sprint 7.2, extended Task 1 Block C):
#   referral_code is resolved FIRST at registration. Valid code ->
#   referred_by = agent_id AND referred_by_link_id = link.id. Invalid/
#   missing -> referred_by = platform_id, referred_by_link_id = NULL.
#   Silent fallback, never blocks registration. Existing users keep
#   their original referred_by / referred_by_link_id.
#
# EMAIL VERIFICATION (G1):
#   6-digit numeric code, stored in credentials.onboarding.email_token.
#   TTL: 10 minutes. Max 5 attempts per code. Resend has rate limit.
#   Verification email sent via core/email.py (SMTP + Mailgun fallback).
#
# PASSWORD RESET:
#   Deliberately NOT built as a copy of email verification -- that flow
#   runs behind get_current_user_write (verify_email_code/
#   resend_verification_code take `user: User` straight from a session
#   dependency). Password reset is requested by someone WITHOUT a
#   session -- that is the entire point of the feature -- so both
#   endpoints are unauthenticated, and the lookup problem is the
#   opposite of email verification's: given a bare token and nothing
#   else, find the one user it belongs to.
#
#   credentials JSONB (used for onboarding.* above) is a per-ROW column
#   reachable only once you already have a `user: User` in hand -- it
#   has no reverse index from token -> user, and email lookups only
#   work because ix_users_email exists; there is no equivalent index
#   over an arbitrary JSONB token field, so a bare-token lookup against
#   it would be a full sequential scan of every user row on every
#   confirm attempt, worse under load exactly when an attacker is
#   hammering the endpoint.
#
#   Instead the token lives in REDIS as the reverse index --
#   password_reset:{token} -> {"user_id": ...} -- the same mechanism
#   this file already uses for session tokens (create_session /
#   delete_session below), for the same reasons: O(1) lookup by a bare
#   opaque token, and TTL is native (EXPIRE) instead of a manually
#   checked expires_at column that would need its own cleanup job to
#   avoid growing forever. Single-use is enforced by GETDEL: the
#   read and the invalidation are one atomic Redis op, so two
#   concurrent confirm calls with the same token can never both
#   succeed -- exactly the replay window a DB "used" flag would have
#   to guard with its own row lock.
#
#   credentials.password_reset is STILL written (requested_at /
#   expires_at only, no token) purely so the request is visible on the
#   user row for support/audit -- mirroring the onboarding.* shape
#   cosmetically -- but it is never read back on confirm. Redis is the
#   only source of truth for validity; the JSONB copy could be deleted
#   entirely without breaking the flow.
#
#   Token: secrets.token_urlsafe(32) (~256 bits), NOT a 6-digit code --
#   an unauthenticated endpoint has no attempt cap protecting it the way
#   verify_email_code's 5-attempt limit does, so the token itself must
#   be infeasible to guess. TTL: 30 minutes (longer than the 10-minute
#   email-verification code -- that TTL assumes the user is already
#   mid-session watching for a code; a reset link assumes the user has
#   just been locked out and needs to go find their inbox first).
#
#   On successful confirm: new password hashed via hash_password()
#   (same argon2 path as everywhere else -- no second hashing scheme),
#   token GETDEL'd (single-use), and delete_all_sessions() invalidates
#   every session that existed before the user regained control -- a
#   session opened by whoever locked the real owner out must not
#   survive their own reset.
#
# COMMIT RULE (P-01):
#   Service never commits or rolls back. Caller manages the transaction.
#   Exception: _audit_login_failure() uses its own session+commit.
# =============================================================================

import asyncio
import json
import secrets
from datetime import datetime, timedelta, UTC
from uuid import UUID

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import BackgroundTasks
from sqlalchemy import BigInteger, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms_sync import ensure_recipient
from app.core.config import settings
from app.core.database import get_session_factory
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.redis import get_redis
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole

logger = structlog.get_logger()

_ph = PasswordHasher()

# Redis key prefixes.
_SESSION_PREFIX = "session:"
_USER_SESSIONS_PREFIX = "user_sessions:"

# Email verification constants.
_VERIFICATION_CODE_TTL_MINUTES = 10
_VERIFICATION_MAX_ATTEMPTS = 5

# Password reset constants. See "PASSWORD RESET" module note above for
# why this is a long URL-safe token in Redis rather than a 6-digit code
# in credentials JSONB.
_PASSWORD_RESET_TOKEN_TTL_MINUTES = 30
_PASSWORD_RESET_REDIS_PREFIX = "password_reset:"


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


async def hash_password(password: str) -> str:
    """Hash a password using argon2.

    Argon2 is deliberately slow. Run off the event loop (asyncio.to_thread)
    so one hash does not stall every other request on this worker for its
    duration -- TASK-6 4.1b.
    """
    return await asyncio.to_thread(_ph.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its argon2 hash.

    Off the event loop for the same reason as hash_password() -- TASK-6 4.1b.

    TASK-6 4.1c: an empty or otherwise malformed password_hash (e.g. a
    user record with an email but no password credential) is not a hash
    argon2 can parse at all -- _ph.verify raises InvalidHashError, a
    ValueError subclass, before it ever gets to compare anything. That is
    a DIFFERENT exception from a genuine mismatch (VerifyMismatchError),
    and if it escaped here it would surface as an unhandled 500 instead
    of the 401 a wrong password gets -- a status-code side-channel as
    real as a timing one. Both cases mean the same thing to a caller:
    this credential does not authenticate.

    THE RESPONSE IS IDENTICAL FOR BOTH; THE LOG IS NOT, DELIBERATELY. Returning
    False silently on an unparseable hash would make a corrupted credential
    store -- a botched migration, a partial restore, a bad import -- look
    exactly like every user suddenly typing the wrong password, with nothing
    anywhere to say otherwise. The 500 this replaced was a side-channel, but it
    was also the only alarm; removing it without replacing it trades a security
    defect for a blind spot. A log line is not an attacker-visible channel.
    """
    try:
        return await asyncio.to_thread(_ph.verify, password_hash, password)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        # Never log the hash or the password -- the FACT and its shape only.
        logger.warning(
            "password_hash_unparseable",
            stored_hash_empty=(password_hash == ""),
            stored_hash_len=len(password_hash or ""),
        )
        return False


# ---------------------------------------------------------------------------
# Email verification helpers (G1)
# ---------------------------------------------------------------------------


def _generate_verification_code() -> str:
    """Generate a 6-digit numeric verification code."""
    return str(secrets.randbelow(900000) + 100000)


async def _send_verification_email(email: str, code: str) -> None:
    """Send verification code via email. Errors logged, not raised."""
    from app.core.email import send_email

    try:
        await send_email(
            recipient=email,
            subject="AIVIS.ONE - Email Verification",
            body=(
                f"Your verification code is: {code}\n\n"
                f"This code expires in {_VERIFICATION_CODE_TTL_MINUTES} minutes.\n\n"
                "If you did not request this, please ignore this email."
            ),
        )
    except Exception:
        logger.error(
            "verification_email_send_failed",
            recipient=email[:3] + "***",
        )


async def _send_password_reset_email(email: str, token: str) -> None:
    """Send the password reset link via email. Errors logged, not raised.

    Same fire-and-forget contract as _send_verification_email -- this
    runs inside a BackgroundTasks call, after the request's transaction
    already committed, so there is nothing left to roll back if the
    send fails.
    """
    from app.core.email import send_email

    reset_link = (
        f"{settings.frontend_base_url}/password-reset/confirm?token={token}"
    )

    try:
        await send_email(
            recipient=email,
            subject="AIVIS.ONE - Password Reset",
            body=(
                "We received a request to reset your AIVIS.ONE password.\n\n"
                f"Reset your password: {reset_link}\n\n"
                f"This link expires in {_PASSWORD_RESET_TOKEN_TTL_MINUTES} "
                "minutes and can only be used once.\n\n"
                "If you did not request this, you can safely ignore this "
                "email -- your password will not be changed."
            ),
        )
    except Exception:
        logger.error(
            "password_reset_email_send_failed",
            recipient=email[:3] + "***",
        )


# ---------------------------------------------------------------------------
# Platform user helper (Sprint 7.2)
# ---------------------------------------------------------------------------


async def get_platform_user_id(session: AsyncSession) -> UUID:
    """Return the Platform user's UUID."""
    stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    result = await session.execute(stmt)
    platform_id = result.scalar_one()
    return platform_id


# ---------------------------------------------------------------------------
# Referral resolution helper (Sprint 7.2, extended Task 1 Block C)
# ---------------------------------------------------------------------------


async def _resolve_referrer(
    referral_code: str | None,
    session: AsyncSession,
) -> tuple[UUID, UUID | None]:
    """Resolve referral_code to (referred_by, referred_by_link_id).

    Valid code -> (agent_id, link_id). Invalid/missing -> (platform_id,
    None). Never raises -- silent fallback to Platform; registration is
    never blocked by a bad code (P7-02). Task 1 Block C: the specific
    link is captured alongside the agent for per-link registration
    stats; commission logic still uses only referred_by.
    """
    platform_id = await get_platform_user_id(session)

    if not referral_code:
        return platform_id, None

    # Lazy import to avoid circular dependency.
    from app.modules.referrals.service import resolve_referral_link

    link = await resolve_referral_link(referral_code, session)

    if link is None:
        logger.debug(
            "referral_code_fallback_to_platform",
            code=referral_code,
        )
        return platform_id, None

    logger.info(
        "referral_code_resolved",
        code=referral_code,
        agent_id=str(link.agent_id),
        link_id=str(link.id),
    )
    return link.agent_id, link.id


# ---------------------------------------------------------------------------
# Failed login audit (SEC-7)
# ---------------------------------------------------------------------------


async def _audit_login_failure(
    user_id: UUID,
    reason: str,
) -> None:
    """Record a failed login attempt in audit_log.

    Uses a dedicated session because the caller's session will be
    rolled back on exception (P-01). This is the only place in
    auth service that manages its own transaction.

    Errors are logged but do not block auth flow.
    """
    factory = get_session_factory()
    session = factory()
    try:
        await record_audit(
            session=session,
            event="user.login_failed",
            actor_id=user_id,
            actor_type="user",
            target_type="user",
            target_id=user_id,
            data={"reason": reason},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.error(
            "audit_login_failure_write_failed",
            user_id=str(user_id),
            reason=reason,
        )
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Email Auth
# ---------------------------------------------------------------------------


async def register_email(
    email: str,
    password: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    referral_code: str | None = None,
) -> User:
    """Register a new user via email + password.

    Creates a User with role=investor, stores hashed password and
    6-digit verification code in credentials JSONB. Schedules the
    verification email to send after the request's transaction commits.

    referral_code is resolved FIRST: valid code -> referred_by = agent_id
    AND referred_by_link_id = link.id; invalid/missing -> referred_by =
    platform_id, referred_by_link_id = NULL. Never blocks registration.

    Does NOT commit or rollback -- caller (get_db_session) manages
    the transaction lifecycle (P-01). background_tasks defers the email
    send past that commit -- TASK-6 4.1d: the old code awaited the send
    while the row was still uncommitted, so a later commit failure would
    leave someone holding a code for a user that does not exist.

    Raises:
        ConflictError: If email is already registered (ix_users_email).
    """
    email_lower = email.strip().lower()
    password_hashed = await hash_password(password)
    verification_code = _generate_verification_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_VERIFICATION_CODE_TTL_MINUTES)

    # Sprint 7.2: resolve referrer FIRST -- agents' bread and butter.
    # Task 1 Block C: the specific link is captured alongside the agent.
    referred_by, referred_by_link_id = await _resolve_referrer(
        referral_code, session
    )

    user = User(
        role=UserRole.INVESTOR,
        referred_by=referred_by,
        referred_by_link_id=referred_by_link_id,
        credentials={
            "email": {
                "email": email_lower,
                "password_hash": password_hashed,
                "verified": False,
                "verified_at": None,
            },
            "onboarding": {
                "email_token": verification_code,
                "email_token_expires_at": expires_at.isoformat(),
                "email_verification_attempts": 0,
            },
        },
    )

    session.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "ix_users_email" in str(exc.orig):
            raise ConflictError("Email is already registered")
        raise

    # The recipient must exist in comms before this product sends that
    # user anything -- the verification e-mail below is the first thing
    # in line. Never raises; a failure defers the recipient to the
    # outbox and registration continues either way (T-64).
    await ensure_recipient(session, user)

    await record_audit(
        session=session,
        event="user.registered",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={
            "auth_method": "email",
            "referral_code": referral_code,
            "referred_by": str(referred_by),
            "referred_by_link_id": (
                str(referred_by_link_id) if referred_by_link_id else None
            ),
        },
    )

    logger.info(
        "user_registered",
        user_id=str(user.id),
        auth_method="email",
        referred_by=str(referred_by),
    )

    # Schedule verification email for AFTER get_db_session commits this
    # transaction (FastAPI runs background tasks only once the response's
    # dependency exit stack -- including that commit -- has closed).
    background_tasks.add_task(
        _send_verification_email, email_lower, verification_code
    )

    return user


async def login_email(
    email: str,
    password: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> User:
    """Authenticate a user by email + password.

    Timing-safe: if email is not found, a dummy argon2 hash is computed
    to prevent email enumeration via response time side-channel.

    Failed login attempts are recorded in audit_log via a dedicated
    session (SEC-7), scheduled through background_tasks so the write
    happens after the response, not before it -- TASK-6 4.1c. Only
    recorded when a user exists -- unknown email attempts raise the same
    401 with no audit entry and no log call at all (no user entity to
    reference).

    Before this fix, the audit write on the known-email branches ran
    synchronously (open session, INSERT, COMMIT, close) before the 401
    was returned, while the unknown-email branch did nothing but hash a
    dummy password -- a DB round-trip dwarfs the hash-timing difference
    the dummy exists to erase. Deferring the write removes that cost from
    every branch's observable response time instead of adding matching
    cost to the branch that didn't have it.

    Raises:
        UnauthorizedError: If email not found or password mismatch.
        ForbiddenError: If the account is deactivated (blocked) -- a
            distinct 403/account_blocked, not the generic 401, since
            this branch is only reachable after the real password
            already verified (see the is_active check below).
    """
    email_lower = email.strip().lower()

    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email_lower
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        # Same function, same asyncio.to_thread path as the real verify
        # below -- TASK-6 4.1b. A dummy hash that stayed synchronous while
        # the real path moved off the event loop would reintroduce the
        # timing signal this call exists to erase, worse than before.
        await hash_password("dummy-password-timing-safe")
        raise UnauthorizedError("Invalid email or password")

    email_creds = user.credentials.get("email", {})
    stored_hash = email_creds.get("password_hash", "")

    if not await verify_password(password, stored_hash):
        background_tasks.add_task(_audit_login_failure, user.id, "wrong_password")
        raise UnauthorizedError("Invalid email or password")

    if user.role == UserRole.PLATFORM:
        background_tasks.add_task(
            _audit_login_failure, user.id, "platform_login_blocked"
        )
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        background_tasks.add_task(
            _audit_login_failure, user.id, "account_deactivated"
        )
        # Deliberately NOT the generic "Invalid email or password" the
        # two branches above use. This is reached only AFTER the correct
        # password has already been verified (see the verify_password
        # check above) -- so the only caller who can ever see this
        # message already knows the account's real credentials; a
        # password-guessing attacker without them can never distinguish
        # "wrong password" from "blocked account" via this branch, since
        # they never pass the check that gates entry to it. Given that,
        # confirming blocked status here (rather than hiding it behind
        # the generic message the way CABINET-BASELINE-GAPS.md's
        # original framing assumed was the only option) costs
        # essentially nothing and fixes a real product gap: block
        # kills every session immediately, so a blocked user almost
        # always meets THIS branch, never the live-session
        # ForbiddenError("Account is deactivated") in auth/dependencies.py
        # -- 403, not 401, so it does not fall into api/client.ts's
        # blanket "any 401 -> generic Unauthorized" handling, and
        # LoginView.vue's existing catch already shows the raw
        # backend message for anything that isn't a 401.
        raise ForbiddenError(
            "Your account has been suspended. Contact support for help.",
            code="account_blocked",
        )

    await record_audit(
        session=session,
        event="user.login",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"auth_method": "email"},
    )

    logger.info("user_login", user_id=str(user.id), auth_method="email")

    return user


# ---------------------------------------------------------------------------
# Email Verification (G1)
# ---------------------------------------------------------------------------


async def verify_email_code(
    user: User,
    code: str,
    session: AsyncSession,
) -> User:
    """Verify a 6-digit email code.

    Checks: already verified, attempts limit, TTL, code match.
    On success: sets credentials.email.verified=True, clears token.

    Raises:
        BadRequestError: On any verification failure.
    """
    email_creds = (user.credentials or {}).get("email", {})
    onboarding = (user.credentials or {}).get("onboarding", {})

    # Already verified.
    if email_creds.get("verified"):
        raise BadRequestError("Email is already verified")

    # Check attempts.
    attempts = onboarding.get("email_verification_attempts", 0)
    if attempts >= _VERIFICATION_MAX_ATTEMPTS:
        raise BadRequestError("Too many attempts, please request a new code")

    # Check TTL.
    expires_at_str = onboarding.get("email_token_expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(UTC) > expires_at:
            raise BadRequestError("Code expired, please request a new code")

    # Check code.
    # Round 4 (BUG-04): on a successful verification we write
    # email_token=None (line below at "Success: ..."). dict.get(key, "")
    # returns the actual stored value when the key exists -- so a None
    # would slip past the default and reach secrets.compare_digest, which
    # rejects None and throws TypeError. The `or ""` coerces the missing
    # / None case into an empty string, and compare_digest then returns
    # False against any non-empty user-supplied code.
    stored_code = onboarding.get("email_token") or ""
    if not secrets.compare_digest(code, stored_code):
        # Increment attempts.
        updated_creds = dict(user.credentials)
        updated_creds["onboarding"] = dict(onboarding)
        updated_creds["onboarding"]["email_verification_attempts"] = attempts + 1
        user.set_jsonb("credentials", updated_creds)
        await session.flush()
        raise BadRequestError("Invalid verification code")

    # Success: mark verified, clear token.
    now = datetime.now(UTC)
    updated_creds = dict(user.credentials)
    updated_creds["email"] = dict(email_creds)
    updated_creds["email"]["verified"] = True
    updated_creds["email"]["verified_at"] = now.isoformat()
    updated_creds["onboarding"] = dict(onboarding)
    updated_creds["onboarding"]["email_token"] = None
    updated_creds["onboarding"]["email_token_expires_at"] = None
    updated_creds["onboarding"]["email_verification_attempts"] = 0
    user.set_jsonb("credentials", updated_creds)

    # Advance onboarding step.
    if user.onboarding_step == OnboardingStep.REGISTERED:
        user.onboarding_step = OnboardingStep.EMAIL_VERIFIED

    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="user.email_verified",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={},
    )

    logger.info("email_verified", user_id=str(user.id))

    return user


async def resend_verification_code(
    user: User,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """Regenerate 6-digit code, reset TTL and attempts, resend email.

    Send is scheduled via background_tasks so it runs after the request's
    transaction commits -- TASK-6 4.1d, same reasoning as register_email.

    Raises:
        BadRequestError: If already verified or no email in credentials.
    """
    email_creds = (user.credentials or {}).get("email", {})
    onboarding = (user.credentials or {}).get("onboarding", {})

    if email_creds.get("verified"):
        raise BadRequestError("Email is already verified")

    email_address = email_creds.get("email")
    if not email_address:
        raise BadRequestError("No email address on this account")

    # Generate new code.
    new_code = _generate_verification_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_VERIFICATION_CODE_TTL_MINUTES)

    updated_creds = dict(user.credentials)
    updated_creds["onboarding"] = dict(onboarding)
    updated_creds["onboarding"]["email_token"] = new_code
    updated_creds["onboarding"]["email_token_expires_at"] = expires_at.isoformat()
    updated_creds["onboarding"]["email_verification_attempts"] = 0
    user.set_jsonb("credentials", updated_creds)
    await session.flush()

    logger.info("verification_code_resent", user_id=str(user.id))

    # Schedule for after commit -- see docstring.
    background_tasks.add_task(_send_verification_email, email_address, new_code)


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------


async def request_password_reset(
    email: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """Request a password reset link. Unauthenticated -- no `user` in hand.

    Anti-enumeration (mirrors login_email's dummy-hash discipline, see
    module note above): this function returns None whether or not the
    email matches a real account, and the router builds the exact same
    response either way -- the caller must not branch on this
    function's behaviour. A dummy Redis SET pays the same round-trip
    cost as the real branch's token write so response timing does not
    leak the match either.

    On a match: generates a token, stores it in Redis as the reverse
    index (token -> user_id, see module note for why Redis and not
    credentials JSONB), writes requested_at/expires_at onto
    credentials.password_reset for visibility, and schedules the email
    for after this transaction commits (P-01 -- same background_tasks
    pattern as register_email).

    Does NOT commit or rollback -- caller (get_db_session) manages the
    transaction (P-01).
    """
    email_lower = email.strip().lower()
    token = secrets.token_urlsafe(32)

    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email_lower
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    redis = get_redis()
    ttl_seconds = _PASSWORD_RESET_TOKEN_TTL_MINUTES * 60

    if user is None:
        # Timing-safe dummy: a throwaway key under a separate prefix so
        # it can never collide with (or be mistaken for) a real reset
        # token, expired quickly since nothing depends on it existing.
        await redis.set(f"password_reset_dummy:{token}", "1", ex=10)
        logger.debug("password_reset_requested_unknown_email")
        return

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_PASSWORD_RESET_TOKEN_TTL_MINUTES)

    await redis.set(
        f"{_PASSWORD_RESET_REDIS_PREFIX}{token}",
        json.dumps({"user_id": str(user.id)}),
        ex=ttl_seconds,
    )

    # Visible on the user row for support/audit only -- see module note,
    # Redis above is the only thing confirm_password_reset() reads. Wrapped
    # in a SAVEPOINT (begin_nested(), same pattern as
    # agent_applications/pools/posts/referrals/support/withdrawals
    # services): an unhandled exception here would otherwise abort the
    # WHOLE transaction at the DB level, so a bare try/except would not
    # be enough -- get_db_session()'s own `await session.commit()` after
    # this function returns would then fail too and the 500 would
    # propagate anyway, past the router's bare `await
    # request_password_reset(...)` call to FastAPI's default handler --
    # a status-code divergence from the not-found branch's fixed 200
    # that would itself be a (narrow, DB-fault-triggered, but real)
    # enumeration side-channel. The Redis token above already exists and
    # is independently sufficient for confirm_password_reset() (it looks
    # the user up by id, not via this JSONB field), so a failure here
    # degrades the audit trail only, never the reset itself.
    try:
        async with session.begin_nested():
            creds = dict(user.credentials or {})
            creds["password_reset"] = {
                "requested_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            user.set_jsonb("credentials", creds)
            await session.flush()

            await record_audit(
                session=session,
                event="user.password_reset_requested",
                actor_id=user.id,
                actor_type="user",
                target_type="user",
                target_id=user.id,
                data={},
            )
    except Exception:
        logger.error(
            "password_reset_audit_write_failed", user_id=str(user.id)
        )

    logger.info("password_reset_requested", user_id=str(user.id))

    # Schedule for after commit -- see register_email docstring for why.
    background_tasks.add_task(_send_password_reset_email, email_lower, token)


async def confirm_password_reset(
    token: str,
    new_password: str,
    session: AsyncSession,
) -> None:
    """Consume a password reset token and set a new password.

    Redis GETDEL is the single-use enforcement: the lookup and the
    invalidation are one atomic op, so a replayed or concurrently-raced
    token can never succeed twice (see module note above for why Redis
    is the source of truth here, not a DB "used" flag).

    On success: hashes the new password via hash_password() (same
    argon2 path as register_email -- no second hashing scheme),
    replaces credentials.email.password_hash, clears
    credentials.password_reset, and invalidates every session that
    existed before this reset via delete_all_sessions().

    Does NOT commit or rollback -- caller (get_db_session) manages the
    transaction (P-01). delete_all_sessions() is Redis-only so it is
    safe to call before that commit lands.

    Raises:
        BadRequestError: Token missing, expired, already used, or the
            user it pointed to no longer exists.
    """
    redis = get_redis()
    key = f"{_PASSWORD_RESET_REDIS_PREFIX}{token}"

    raw = await redis.getdel(key)
    if raw is None:
        raise BadRequestError("Invalid or expired reset token")

    try:
        user_id = UUID(json.loads(raw)["user_id"])
    except (KeyError, ValueError, TypeError) as exc:
        # Defensive only -- this process is the only writer of this key
        # shape. A malformed payload means data corruption, not user
        # error; still surfaces as the same generic 400 rather than 500.
        logger.error("password_reset_token_payload_corrupt")
        raise BadRequestError("Invalid or expired reset token") from exc

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise BadRequestError("Invalid or expired reset token")

    new_hash = await hash_password(new_password)

    creds = dict(user.credentials or {})
    email_creds = dict(creds.get("email", {}))
    email_creds["password_hash"] = new_hash
    creds["email"] = email_creds
    creds["password_reset"] = None
    user.set_jsonb("credentials", creds)
    await session.flush()

    await record_audit(
        session=session,
        event="user.password_reset_completed",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={},
    )

    # A session opened by whoever locked the real owner out must not
    # survive their own reset -- see module note above.
    await delete_all_sessions(user.id)

    logger.info("password_reset_completed", user_id=str(user.id))


# ---------------------------------------------------------------------------
# Telegram Auth (Sprint 1.2)
# ---------------------------------------------------------------------------


async def upsert_telegram_user(
    telegram_user: dict,
    session: AsyncSession,
    *,
    referral_code: str | None = None,
) -> tuple[User, bool]:
    """Create or update user on Telegram login.

    Lookup by credentials->'telegram'->>'id' via functional index.
    If found -- update credentials.telegram via set_jsonb().
    If not found -- create new User with role=investor.

    referral_code is only used for NEW users (is_new=True).
    Existing users keep their original referred_by / referred_by_link_id.

    Race condition (two simultaneous first logins) is handled via
    begin_nested() (SAVEPOINT) + IntegrityError catch + retry SELECT.
    This follows P-05 pattern: savepoint rolls back only the INSERT,
    outer transaction remains valid for retry.

    After set_jsonb + flush, session.refresh() reloads expired attrs
    (updated_at) to prevent MissingGreenlet when Pydantic reads them.

    Does NOT commit -- caller manages transaction (P-01).

    Returns:
        Tuple of (User, is_new) where is_new=True if user was just created.
    """
    telegram_id = telegram_user["id"]

    telegram_creds = {
        "id": telegram_id,
        "username": telegram_user.get("username"),
        "first_name": telegram_user.get("first_name"),
        "last_name": telegram_user.get("last_name"),
        "photo_url": telegram_user.get("photo_url"),
        "language_code": telegram_user.get("language_code"),
    }

    # Step 1: Lookup existing user by telegram_id in JSONB.
    # Drive-by fix (found during Task 1): the lookup used as_integer(),
    # i.e. CAST(... AS INTEGER). Real Telegram ids exceeded int32 long
    # ago, so any such user got an asyncpg int4 bind overflow -> 500 on
    # login. The functional index ix_users_telegram_id (migration 0002)
    # was ALWAYS ::bigint -- this BIGINT cast both fixes the overflow
    # and makes the expression actually match the index.
    stmt = select(User).where(
        cast(User.credentials["telegram"]["id"].astext, BigInteger)
        == telegram_id
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        # Existing user -- update credentials.telegram.
        # Merge with existing credentials to preserve email auth data.
        updated_creds = dict(user.credentials)
        updated_creds["telegram"] = telegram_creds
        user.set_jsonb("credentials", updated_creds)

        await session.flush()
        # Reload expired attrs (updated_at) after set_jsonb + flush.
        await session.refresh(user)

        await record_audit(
            session=session,
            event="user.login",
            actor_id=user.id,
            actor_type="user",
            target_type="user",
            target_id=user.id,
            data={"auth_method": "telegram"},
        )

        logger.info(
            "telegram_user_updated",
            user_id=str(user.id),
            telegram_id=telegram_id,
        )

        return user, False

    # Step 2: New user -- create with role=investor.
    # Use begin_nested() (SAVEPOINT) so that IntegrityError from race
    # condition only rolls back the INSERT, not the outer transaction (P-05).

    # Sprint 7.2: resolve referrer for new user.
    # Task 1 Block C: the specific link is captured alongside the agent.
    referred_by, referred_by_link_id = await _resolve_referrer(
        referral_code, session
    )

    lang = (telegram_user.get("language_code") or "en")[:2] or "en"
    new_user = User(
        role=UserRole.INVESTOR,
        referred_by=referred_by,
        referred_by_link_id=referred_by_link_id,
        credentials={"telegram": telegram_creds},
        language=lang,
    )

    try:
        async with session.begin_nested():
            session.add(new_user)
            await session.flush()
    except IntegrityError as exc:
        if "ix_users_telegram_id" in str(exc.orig):
            # Race condition: another request created this user first.
            # Savepoint rolled back, outer transaction still valid.
            result = await session.execute(stmt)
            user = result.scalar_one()

            updated_creds = dict(user.credentials)
            updated_creds["telegram"] = telegram_creds
            user.set_jsonb("credentials", updated_creds)
            await session.flush()
            await session.refresh(user)

            # Audit the race-resolved login -- every auth event must
            # be recorded for financial platform compliance.
            await record_audit(
                session=session,
                event="user.login",
                actor_id=user.id,
                actor_type="user",
                target_type="user",
                target_id=user.id,
                data={
                    "auth_method": "telegram",
                    "race_resolved": True,
                },
            )

            logger.info(
                "telegram_login_race_resolved",
                user_id=str(user.id),
                telegram_id=telegram_id,
            )

            return user, False
        raise

    await session.refresh(new_user)

    # Same rule as the e-mail path: comms learns the recipient before
    # the product has anything to say to them (T-64). Deliberately NOT
    # in the race branch above -- that branch resolved to an EXISTING
    # user, who already got their upsert when they were created.
    await ensure_recipient(session, new_user)

    await record_audit(
        session=session,
        event="user.registered",
        actor_id=new_user.id,
        actor_type="user",
        target_type="user",
        target_id=new_user.id,
        data={
            "auth_method": "telegram",
            "referral_code": referral_code,
            "referred_by": str(referred_by),
            "referred_by_link_id": (
                str(referred_by_link_id) if referred_by_link_id else None
            ),
        },
    )

    logger.info(
        "telegram_user_created",
        user_id=str(new_user.id),
        telegram_id=telegram_id,
        referred_by=str(referred_by),
    )

    return new_user, True


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def _get_session_ttl() -> int:
    """Return session TTL in seconds from config."""
    return settings.session_ttl_days * 86400


async def create_session(user: User, auth_method: str = "email") -> str:
    """Create a new session in Redis and return the token.

    All Redis writes (SET + ZADD + GC + EXPIRE) execute in a single
    MULTI/EXEC pipeline for atomicity.

    MAX_CONCURRENT_SESSIONS: if the user exceeds the limit, the oldest
    session is evicted via ZPOPMIN.
    """
    token = secrets.token_urlsafe(48)
    redis = get_redis()
    ttl = _get_session_ttl()
    now = datetime.now(UTC)
    now_ts = now.timestamp()

    session_data = json.dumps({
        "user_id": str(user.id),
        "auth_method": auth_method,
        "created_at": now.isoformat(),
    })

    session_key = f"{_SESSION_PREFIX}{token}"
    index_key = f"{_USER_SESSIONS_PREFIX}{user.id}"

    cutoff = now_ts - ttl

    pipe = redis.pipeline(transaction=True)
    pipe.set(session_key, session_data, ex=ttl)
    pipe.zadd(index_key, {token: now_ts})
    pipe.zremrangebyscore(index_key, "-inf", cutoff)
    pipe.expire(index_key, ttl)
    results = await pipe.execute()

    removed = results[2]
    if removed:
        logger.debug(
            "session_index_gc",
            user_id=str(user.id),
            removed=removed,
        )

    await _enforce_session_limit(user.id, index_key)

    logger.info(
        "session_created",
        user_id=str(user.id),
        auth_method=auth_method,
    )

    return token


async def _enforce_session_limit(user_id: UUID, index_key: str) -> None:
    """Evict oldest sessions if user exceeds MAX_CONCURRENT_SESSIONS."""
    redis = get_redis()
    max_sessions = settings.max_concurrent_sessions

    count = await redis.zcard(index_key)
    if count <= max_sessions:
        return

    to_evict = count - max_sessions
    evicted = await redis.zpopmin(index_key, to_evict)

    if evicted:
        session_keys = [
            f"{_SESSION_PREFIX}{token}" for token, _score in evicted
        ]
        await redis.delete(*session_keys)

        logger.info(
            "sessions_evicted",
            user_id=str(user_id),
            evicted=len(evicted),
        )


async def get_session(token: str) -> dict | None:
    """Retrieve session data from Redis by token."""
    redis = get_redis()
    data = await redis.get(f"{_SESSION_PREFIX}{token}")
    if data is None:
        return None
    return json.loads(data)


async def delete_session(token: str, user_id: UUID | None = None) -> None:
    """Delete a single session from Redis."""
    redis = get_redis()
    await redis.delete(f"{_SESSION_PREFIX}{token}")

    if user_id is not None:
        index_key = f"{_USER_SESSIONS_PREFIX}{user_id}"
        await redis.zrem(index_key, token)

    logger.info("session_deleted")


async def delete_all_sessions(user_id: UUID) -> int:
    """Delete all sessions for a user (logout-all). Atomic via Lua script.

    Returns the number of sessions invalidated.

    Lua script: atomically reads ZSET members, deletes all session keys,
    then deletes the index key. Runs in a single Redis round-trip.
    """
    redis = get_redis()
    index_key = f"{_USER_SESSIONS_PREFIX}{user_id}"

    lua = """
    local members = redis.call('ZRANGE', KEYS[1], 0, -1)
    local count = #members
    if count > 0 then
        local session_keys = {}
        for i, token in ipairs(members) do
            session_keys[i] = ARGV[1] .. token
        end
        redis.call('DEL', unpack(session_keys))
    end
    redis.call('DEL', KEYS[1])
    return count
    """

    count = await redis.eval(lua, 1, index_key, _SESSION_PREFIX)

    logger.info(
        "all_sessions_deleted",
        user_id=str(user_id),
        sessions_invalidated=int(count),
    )

    return int(count)
