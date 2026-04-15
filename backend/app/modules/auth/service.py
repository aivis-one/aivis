# =============================================================================
# CBSHOME Backend -- Auth Service (Sprint 7.2, G1 fix)
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
#
# FAILED LOGIN AUDIT (SEC-7):
#   login_email() records failed attempts in audit_log via a dedicated
#   session (_audit_login_failure). Required because the caller's session
#   is rolled back on exception (P-01), which would discard any audit
#   entries written to the same session.
#
# REFERRAL (Sprint 7.2):
#   referral_code is resolved FIRST at registration. Valid code ->
#   referred_by = agent_id. Invalid/missing -> referred_by = platform_id.
#   Silent fallback, never blocks registration.
#
# EMAIL VERIFICATION (G1):
#   6-digit numeric code, stored in credentials.onboarding.email_token.
#   TTL: 10 minutes. Max 5 attempts per code. Resend has rate limit.
#   Verification email sent via core/email.py (SMTP + Mailgun fallback).
#
# COMMIT RULE (P-01):
#   Service never commits or rolls back. Caller manages the transaction.
#   Exception: _audit_login_failure() uses its own session+commit.
# =============================================================================

import json
import secrets
from datetime import datetime, timedelta, UTC
from uuid import UUID

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.database import get_session_factory
from app.core.exceptions import BadRequestError, ConflictError, UnauthorizedError
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


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password using argon2."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its argon2 hash."""
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# Email verification helpers (G1)
# ---------------------------------------------------------------------------


def _generate_verification_code() -> str:
    """Generate a 6-digit numeric verification code."""
    return str(secrets.randbelow(900000) + 100000)


async def _send_verification_email(email: str, code: str) -> None:
    """Send verification code via email. Errors logged, not raised."""
    from app.core.config import settings

    if settings.app_env.lower() in ("development", "dev", "test"):
        logger.info("verification_email_skipped_dev", email=email[:3] + "***", code=code)
        return

    from app.core.email import send_email

    try:
        await send_email(
            recipient=email,
            subject="CBS HOME - Email Verification",
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
# Referral resolution helper (Sprint 7.2)
# ---------------------------------------------------------------------------


async def _resolve_referrer(
    referral_code: str | None,
    session: AsyncSession,
) -> UUID:
    """Resolve referral_code to a referrer UUID.

    Returns agent_id if code is valid, platform_id otherwise.
    Never raises -- silent fallback to Platform.
    """
    platform_id = await get_platform_user_id(session)

    if not referral_code:
        return platform_id

    # Lazy import to avoid circular dependency.
    from app.modules.referrals.service import resolve_referral_code

    agent_id = await resolve_referral_code(referral_code, session)

    if agent_id is None:
        logger.debug(
            "referral_code_fallback_to_platform",
            code=referral_code,
        )
        return platform_id

    logger.info(
        "referral_code_resolved",
        code=referral_code,
        agent_id=str(agent_id),
    )
    return agent_id


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
    *,
    referral_code: str | None = None,
) -> User:
    """Register a new user via email + password.

    Creates a User with role=investor, stores hashed password and
    6-digit verification code in credentials JSONB. Sends verification
    email with the code.

    referral_code is resolved FIRST: valid code -> referred_by = agent_id,
    invalid/missing -> referred_by = platform_id. Never blocks registration.

    Does NOT commit or rollback -- caller (get_db_session) manages
    the transaction lifecycle (P-01).

    Raises:
        ConflictError: If email is already registered (ix_users_email).
    """
    email_lower = email.strip().lower()
    password_hashed = hash_password(password)
    verification_code = _generate_verification_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=_VERIFICATION_CODE_TTL_MINUTES)

    # Sprint 7.2: resolve referrer FIRST -- agents' bread and butter.
    referred_by = await _resolve_referrer(referral_code, session)

    user = User(
        role=UserRole.INVESTOR,
        referred_by=referred_by,
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
        },
    )

    logger.info(
        "user_registered",
        user_id=str(user.id),
        auth_method="email",
        referred_by=str(referred_by),
    )

    # Send verification email (fire-and-forget, errors logged).
    await _send_verification_email(email_lower, verification_code)

    return user


async def login_email(
    email: str,
    password: str,
    session: AsyncSession,
) -> User:
    """Authenticate a user by email + password.

    Timing-safe: if email is not found, a dummy argon2 hash is computed
    to prevent email enumeration via response time side-channel.

    Failed login attempts are recorded in audit_log via a dedicated
    session (SEC-7). Only recorded when a user exists -- unknown email
    attempts are logged to structlog only (no user entity to reference).

    Raises:
        UnauthorizedError: If email not found, password mismatch, or account deactivated.
    """
    email_lower = email.strip().lower()

    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email_lower
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        _ph.hash("dummy-password-timing-safe")
        raise UnauthorizedError("Invalid email or password")

    email_creds = user.credentials.get("email", {})
    stored_hash = email_creds.get("password_hash", "")

    if not verify_password(password, stored_hash):
        await _audit_login_failure(user.id, "wrong_password")
        raise UnauthorizedError("Invalid email or password")

    if user.role == UserRole.PLATFORM:
        await _audit_login_failure(user.id, "platform_login_blocked")
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        await _audit_login_failure(user.id, "account_deactivated")
        raise UnauthorizedError("Invalid email or password")

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
    stored_code = onboarding.get("email_token", "")
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
) -> None:
    """Regenerate 6-digit code, reset TTL and attempts, resend email.

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

    # Send email (fire-and-forget).
    await _send_verification_email(email_address, new_code)


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
    Existing users keep their original referred_by.

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
    stmt = select(User).where(
        User.credentials["telegram"]["id"].as_integer() == telegram_id
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
    referred_by = await _resolve_referrer(referral_code, session)

    lang = (telegram_user.get("language_code") or "en")[:2] or "en"
    new_user = User(
        role=UserRole.INVESTOR,
        referred_by=referred_by,
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
