# =============================================================================
# CBSHOME Backend -- Shared Test Helpers
# =============================================================================
#
# Utility functions used across multiple test files.
# Not a conftest (no fixtures) -- just plain functions.
#
# EMAIL AUTH:
#   register_user() and login_user() call the email auth endpoints.
#   Each returns the full response dict (AuthResponse).
#
# CLEANUP:
#   cleanup_users_by_email() removes test users by email prefix.
#   Tests should use unique email prefixes to avoid collisions.
# =============================================================================

from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.users.models import User


def auth_headers(token: str) -> dict[str, str]:
    """Build Authorization header dict for test requests."""
    return {"Authorization": f"Bearer {token}"}


async def register_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpass123",
) -> dict:
    """Register a user via POST /api/v1/auth/email/register.

    Returns the parsed AuthResponse dict.
    Raises AssertionError if status != 201.
    """
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, f"Register failed: {resp.status_code} {resp.text}"
    return resp.json()


async def login_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpass123",
) -> dict:
    """Login a user via POST /api/v1/auth/email/login.

    Returns the parsed AuthResponse dict.
    Raises AssertionError if status != 200.
    """
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()


async def cleanup_test_users(
    session: AsyncSession,
    email_prefix: str,
) -> None:
    """Delete test users whose email starts with the given prefix.

    Also cleans up related audit_log entries.
    Uses ORM delete (no raw SQL).
    """
    # Find user IDs by email prefix in credentials JSONB.
    stmt = select(User.id).where(
        User.credentials["email"]["email"].as_string().startswith(email_prefix)
    )
    result = await session.execute(stmt)
    user_ids = [row[0] for row in result.all()]

    if not user_ids:
        return

    # Delete audit logs referencing these users (actor_id or target_id).
    await session.execute(
        delete(AuditLog).where(
            AuditLog.actor_id.in_(user_ids) | AuditLog.target_id.in_(user_ids)
        )
    )

    # Delete users.
    await session.execute(
        delete(User).where(User.id.in_(user_ids))
    )

    await session.commit()
