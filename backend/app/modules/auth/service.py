# =============================================================================
# CBSHOME Backend -- Auth Service
# =============================================================================
#
# RESPONSIBILITIES:
#   1. Email registration and login (argon2 password hashing)
#   2. Telegram user upsert (Sprint 1.2)
#   3. Manage sessions in Redis (create / get / delete / delete-all)
#
# SESSION FORMAT IN REDIS:
#   Key:   session:{token}
#   Value: JSON {"user_id": "uuid", "auth_method": "email|telegram", "created_at": "iso"}
#   TTL:   SESSION_TTL_DAYS (default 30 days)
#
# SESSION INDEX:
#   Key:   user_sessions:{user_id}
#   Type:  Redis ZSET (Sorted Set), score = creation timestamp
#   TTL:   Same as session TTL
#   Purpose: Reverse index for logout-all + concurrent session limit.
#
# KNOWN LIMITATION:
#   Redis session is created before DB commit in the router. If commit
#   fails, an orphan session key remains in Redis until TTL expires
#   (30 days). The next request with that token will get 401 (user not
#   found in DB). Acceptable for MVP -- same pattern as VELO.
# =============================================================================

import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.redis import get_redis
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

# Redis key prefixes.
_SESSION_PREFIX = "session:"
_USER_SESSIONS_PREFIX = "user_sessions:"

# Password hasher -- singleton, thread-safe.
_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Password hashing (argon2)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an argon2 hash.

    Returns True if match, False if mismatch.
    """
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# Email Auth
# ---------------------------------------------------------------------------


async def register_email(
    email: str,
    password: str,
    session: AsyncSession,
) -> User:
    """Register a new user via email + password.

    Creates a User with role=investor, stores hashed password and
    email verification token in credentials JSONB.

    Does NOT commit or rollback -- caller (get_db_session) manages
    the transaction lifecycle (P-01).

    Raises:
        ConflictError: If email is already registered (ix_users_email).
    """
    email_lower = email.strip().lower()
    password_hashed = hash_password(password)
    email_token = secrets.token_urlsafe(32)

    user = User(
        role=UserRole.INVESTOR,
        credentials={
            "email": {
                "email": email_lower,
                "password_hash": password_hashed,
                "verified": False,
                "verified_at": None,
            },
            "onboarding": {
                "email_token": email_token,
                "email_token_expires_at": None,
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
        data={"auth_method": "email"},
    )

    logger.info(
        "user_registered",
        user_id=str(user.id),
        auth_method="email",
    )

    return user


async def login_email(
    email: str,
    password: str,
    session: AsyncSession,
) -> User:
    """Authenticate a user by email + password.

    Timing-safe: if email is not found, a dummy argon2 hash is computed
    to prevent email enumeration via response time side-channel.

    Raises:
        UnauthorizedError: If email not found or password mismatch.
        ForbiddenError: If user account is deactivated.
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
        raise UnauthorizedError("Invalid email or password")

    if user.role == UserRole.PLATFORM:
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise ForbiddenError("Account is deactivated")

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
# Telegram Auth (Sprint 1.2)
# ---------------------------------------------------------------------------


async def upsert_telegram_user(
    telegram_user: dict,
    session: AsyncSession,
) -> tuple[User, bool]:
    """Create or update user on Telegram login.

    Lookup by credentials->'telegram'->>'id' via functional index.
    If found -- update credentials.telegram via set_jsonb().
    If not found -- create new User with role=investor.

    Race condition (two simultaneous first logins) is handled via
    begin_nested() (SAVEPOINT) + IntegrityError catch + retry SELECT.
    This follows P-05 pattern: savepoint rolls back only the INSERT,
    outer transaction remains valid for retry.

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
    lang = (telegram_user.get("language_code") or "en")[:2] or "en"
    new_user = User(
        role=UserRole.INVESTOR,
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

            logger.info(
                "telegram_user_race_resolved",
                user_id=str(user.id),
                telegram_id=telegram_id,
            )

            return user, False
        raise

    await record_audit(
        session=session,
        event="user.registered",
        actor_id=new_user.id,
        actor_type="user",
        target_type="user",
        target_id=new_user.id,
        data={"auth_method": "telegram"},
    )

    logger.info(
        "telegram_user_created",
        user_id=str(new_user.id),
        telegram_id=telegram_id,
    )

    return new_user, True


# ---------------------------------------------------------------------------
# Session management (Redis)
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
    """Delete all sessions for a user (logout-all). Atomic via Lua script."""
    redis = get_redis()
    index_key = f"{_USER_SESSIONS_PREFIX}{user_id}"
    session_prefix = _SESSION_PREFIX

    lua_script = """
local index_key = KEYS[1]
local session_prefix = ARGV[1]
local tokens = redis.call('ZRANGE', index_key, 0, -1)
if #tokens == 0 then
    return 0
end
local keys_to_delete = {index_key}
for _, token in ipairs(tokens) do
    table.insert(keys_to_delete, session_prefix .. token)
end
redis.call('DEL', unpack(keys_to_delete))
return #tokens
"""

    count = await redis.eval(lua_script, 1, index_key, session_prefix)

    if count:
        logger.info(
            "all_sessions_deleted",
            user_id=str(user_id),
            count=count,
        )

    return int(count)
