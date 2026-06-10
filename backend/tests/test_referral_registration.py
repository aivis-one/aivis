# =============================================================================
# CBSHOME Backend -- Registration Link Capture Tests (Task 1 Block C)
# =============================================================================
#
# Covers referred_by_link_id capture at registration (migration 0035):
#
#   email path (register_email):
#     - valid code         -> referred_by == agent_id AND
#                             referred_by_link_id == link.id
#     - invalid code       -> referred_by == platform_id, link_id NULL,
#                             registration NOT blocked (201)
#     - no code            -> same platform fallback
#     - deactivated link   -> resolve declines, platform fallback
#
#   telegram path (upsert_telegram_user):
#     - valid code         -> link_id captured on the new user
#     - no code            -> link_id NULL
#     - repeat login       -> existing user keeps original
#                             referred_by / referred_by_link_id even if
#                             a different code is sent (P7-02: referral
#                             applies to NEW users only)
#
# NOTE: the historical tests/test_referrals.py (Sprint 7.2, 15 tests)
# no longer exists after the conftest rewrite -- this file is net-new
# coverage for the registration branches, not a duplicate.
#
# Telegram ids are randomized per call (not the fixed 100001..100099
# pool) because the dev DB persists across runs: a reused tg_id would
# hit the is_new=False branch and skip referral capture entirely.
# =============================================================================

from __future__ import annotations

import secrets

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_platform_user_id
from app.modules.users.models import User

from tests.helpers import (
    create_agent_with_link,
    login_telegram,
    register_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_telegram_id() -> int:
    """Random telegram id in [1e8, 2.1e9), unique across runs on the
    shared dev DB (a reused id would hit the is_new=False branch and
    skip referral capture).

    Upper bound stays below int32 max (2_147_483_647): the telegram
    lookup in upsert_telegram_user casts the JSONB id via as_integer()
    (PG INTEGER), so larger values overflow at the asyncpg bind. Real
    Telegram ids already exceed int32 in the wild -- that latent app
    bug is flagged as a separate TD, not worked around here.
    """
    return 100_000_000 + secrets.randbelow(2_000_000_000)


async def _load_user_by_id(session: AsyncSession, user_id: str) -> User:
    """Load a User row by the id echoed in an AuthResponse body."""
    return (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Email path
# ---------------------------------------------------------------------------


async def test_email_register_valid_code_captures_agent_and_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Valid code -> referred_by = agent_id AND referred_by_link_id = link.id."""
    agent, _token, link = await create_agent_with_link(client, db_session)

    body = await register_user(client, referral_code=link.code)
    user = await _load_user_by_id(db_session, body["user"]["id"])

    assert user.referred_by == agent.id
    assert user.referred_by_link_id == link.id


async def test_email_register_invalid_code_platform_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Invalid code -> platform fallback, link_id NULL, registration OK."""
    platform_id = await get_platform_user_id(db_session)

    # register_user asserts 201 internally -- a bad code never blocks.
    body = await register_user(client, referral_code="no_such_code_x")
    user = await _load_user_by_id(db_session, body["user"]["id"])

    assert user.referred_by == platform_id
    assert user.referred_by_link_id is None


async def test_email_register_no_code_platform_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No code at all -> platform fallback, link_id NULL."""
    platform_id = await get_platform_user_id(db_session)

    body = await register_user(client)
    user = await _load_user_by_id(db_session, body["user"]["id"])

    assert user.referred_by == platform_id
    assert user.referred_by_link_id is None


async def test_email_register_deactivated_link_platform_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deactivated link -> resolve declines -> platform fallback.

    Contrast with clicks (test_referral_clicks): the click counter
    ignores is_active, but registration attribution respects it.
    """
    _agent, _token, link = await create_agent_with_link(client, db_session)
    link.is_active = False
    await db_session.commit()

    platform_id = await get_platform_user_id(db_session)

    body = await register_user(client, referral_code=link.code)
    user = await _load_user_by_id(db_session, body["user"]["id"])

    assert user.referred_by == platform_id
    assert user.referred_by_link_id is None


# ---------------------------------------------------------------------------
# Telegram path
# ---------------------------------------------------------------------------


async def test_telegram_register_valid_code_captures_agent_and_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """New telegram user with valid code -> agent + link captured."""
    agent, _token, link = await create_agent_with_link(client, db_session)

    body = await login_telegram(
        client,
        telegram_id=_fresh_telegram_id(),
        referral_code=link.code,
    )
    user = await _load_user_by_id(db_session, body["user"]["id"])

    assert user.referred_by == agent.id
    assert user.referred_by_link_id == link.id


async def test_telegram_register_no_code_platform_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """New telegram user without code -> platform fallback, link_id NULL."""
    platform_id = await get_platform_user_id(db_session)

    body = await login_telegram(client, telegram_id=_fresh_telegram_id())
    user = await _load_user_by_id(db_session, body["user"]["id"])

    assert user.referred_by == platform_id
    assert user.referred_by_link_id is None


async def test_telegram_repeat_login_keeps_original_attribution(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Existing user re-login with a DIFFERENT code keeps the original
    referred_by / referred_by_link_id (referral applies to new users only).
    """
    agent1, _t1, link1 = await create_agent_with_link(client, db_session)
    _agent2, _t2, link2 = await create_agent_with_link(client, db_session)

    tg_id = _fresh_telegram_id()

    body = await login_telegram(
        client, telegram_id=tg_id, referral_code=link1.code
    )
    user_id = body["user"]["id"]

    # Second login, same telegram id, different (also valid) code.
    await login_telegram(client, telegram_id=tg_id, referral_code=link2.code)

    user = await _load_user_by_id(db_session, user_id)
    await db_session.refresh(user)

    assert user.referred_by == agent1.id
    assert user.referred_by_link_id == link1.id
