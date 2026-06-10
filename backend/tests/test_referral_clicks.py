# =============================================================================
# CBSHOME Backend -- Referral Click Tests (Task 1 Block B)
# =============================================================================
#
# Covers POST /api/v1/public/referral-click:
#   - known code         -> 204, click_count incremented atomically
#   - unknown code       -> 204, no increment (existence not confirmed)
#   - deactivated link   -> 204, still incremented (boss-locked decision)
#   - oversized code     -> 422 (Pydantic edge, max_length=20)
#   - rate limit exceeded -> 429 (per-IP, Redis-backed)
#
# Test links are created directly via db_session (the endpoint does not
# validate the owning agent, only the code), with UUID-suffixed unique
# codes so runs on the shared dev DB never collide.
# =============================================================================

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.referrals.models import ReferralLink
from app.modules.users.models import User
from tests.helpers import register_user

CLICK_URL = "/api/v1/public/referral-click"

# Fixed rate-limit key: ASGITransport requests come from 127.0.0.1
# (same assumption as conftest's email_auth key).
_RATE_KEY = "public_referral_click:127.0.0.1"


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _unique_code() -> str:
    """13-char unique code, within ReferralLink.code String(20)."""
    return f"clk{uuid.uuid4().hex[:10]}"


async def _create_link(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    is_active: bool = True,
) -> ReferralLink:
    """Create a ReferralLink row directly.

    The click endpoint matches by code only (no agent validation), so
    any existing user works as the FK owner -- we register a throwaway
    investor instead of building a full agent.
    """
    body = await register_user(client)
    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == body["email"]
            )
        )
    ).scalar_one()

    link = ReferralLink(
        id=uuid.uuid4(),
        agent_id=user.id,
        code=_unique_code(),
        is_active=is_active,
    )
    db_session.add(link)
    await db_session.commit()
    await db_session.refresh(link)
    return link


@pytest.fixture(autouse=True)
async def _clear_click_rate_limit():
    """Drop the click rate-limit key before and after each test.

    conftest's clear_rate_limit fixture only covers the auth-flow keys;
    this module adds its own bucket so a click-heavy test never bleeds
    a 429 into the next one.
    """
    from app.core.redis import get_redis

    redis = get_redis()
    await redis.delete(_RATE_KEY)
    yield
    await redis.delete(_RATE_KEY)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_click_known_code_204_and_increment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    link = await _create_link(client, db_session)
    assert link.click_count == 0

    resp = await client.post(CLICK_URL, json={"code": link.code})
    assert resp.status_code == 204, resp.text
    assert resp.content == b""

    await db_session.refresh(link)
    assert link.click_count == 1

    # Second click keeps counting (raw counter, no dedup).
    resp = await client.post(CLICK_URL, json={"code": link.code})
    assert resp.status_code == 204
    await db_session.refresh(link)
    assert link.click_count == 2


async def test_click_unknown_code_204_no_increment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    link = await _create_link(client, db_session)

    resp = await client.post(CLICK_URL, json={"code": _unique_code()})
    assert resp.status_code == 204, resp.text

    # The existing link is untouched -- the miss did not increment
    # anything anywhere.
    await db_session.refresh(link)
    assert link.click_count == 0


async def test_click_inactive_link_still_increments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Boss-locked decision: clicks count regardless of is_active.
    link = await _create_link(client, db_session, is_active=False)

    resp = await client.post(CLICK_URL, json={"code": link.code})
    assert resp.status_code == 204, resp.text

    await db_session.refresh(link)
    assert link.click_count == 1


async def test_click_oversized_code_422(client: AsyncClient) -> None:
    # max_length=20 mirrors ReferralLink.code String(20). Anything
    # longer fails at the Pydantic edge -- it can never match a code,
    # and 422 is invisible to the fire-and-forget frontend anyway.
    resp = await client.post(CLICK_URL, json={"code": "x" * 21})
    assert resp.status_code == 422


async def test_click_rate_limit_429(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shrink the limit so the test stays fast; the router reads
    # settings at request time, so monkeypatching the singleton works.
    monkeypatch.setattr(
        settings, "referral_click_rate_limit_max_requests", 3
    )

    link = await _create_link(client, db_session)

    for _ in range(3):
        resp = await client.post(CLICK_URL, json={"code": link.code})
        assert resp.status_code == 204, resp.text

    resp = await client.post(CLICK_URL, json={"code": link.code})
    assert resp.status_code == 429, resp.text
    assert "Retry-After" in resp.headers

    # Exactly the allowed 3 clicks landed -- the 429 attempt did not.
    await db_session.refresh(link)
    assert link.click_count == 3
