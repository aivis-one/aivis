# =============================================================================
# AIVIS.ONE Backend -- Referral Click Endpoint Tests (Task 1 Block B)
# =============================================================================
#
# Covers POST /api/v1/public/referral-click:
#   - valid code        -> 204 + click_count incremented (twice -> 2)
#   - unknown code      -> 204, no increment anywhere
#   - deactivated link  -> 204 + increment (clicks count regardless of
#                          is_active -- boss-locked decision)
#   - oversized code    -> 422 (Pydantic max_length=20 edge)
#   - rate limit        -> 429 after the per-IP budget is exhausted
#                          (limit lowered via settings monkeypatch so the
#                          test does not fire 60+ requests)
#
# The agent + link factory lives in tests/helpers.py
# (create_agent_with_link) -- shared with test_referral_registration.py
# since Task 1 Block C.
# =============================================================================

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from tests.helpers import create_agent_with_link

# ASGITransport requests always originate from 127.0.0.1.
_CLICK_RL_KEY = "public_referral_click:127.0.0.1"


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def clear_click_rate_limit() -> None:
    """Drop the referral-click rate-limit key before each test.

    Same rationale as conftest.clear_rate_limit: tests in this file
    fire multiple clicks from the single ASGITransport IP; leftovers
    from a previous test (or a fast repeated run) must not bleed in.
    """
    try:
        from app.core.redis import get_redis

        redis = get_redis()
        await redis.delete(_CLICK_RL_KEY)
    except RuntimeError:
        # Redis singleton not yet initialised (collection error path).
        pass


async def _click(client: AsyncClient, code: str) -> int:
    """POST a click for `code`, return the status code."""
    resp = await client.post(
        "/api/v1/public/referral-click", json={"code": code}
    )
    return resp.status_code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_click_valid_code_increments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Valid code -> 204, click_count goes 0 -> 1 -> 2."""
    _agent, _token, link = await create_agent_with_link(client, db_session)
    assert link.click_count == 0

    assert await _click(client, link.code) == 204
    await db_session.refresh(link)
    assert link.click_count == 1

    assert await _click(client, link.code) == 204
    await db_session.refresh(link)
    assert link.click_count == 2


async def test_click_unknown_code_204_no_increment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unknown code -> still 204 (no existence probe), nothing changes."""
    _agent, _token, link = await create_agent_with_link(client, db_session)

    assert await _click(client, "no_such_code_404") == 204

    await db_session.refresh(link)
    assert link.click_count == 0


async def test_click_deactivated_link_still_increments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """is_active=False does NOT stop the counter (locked decision)."""
    _agent, _token, link = await create_agent_with_link(client, db_session)
    link.is_active = False
    await db_session.commit()

    assert await _click(client, link.code) == 204

    await db_session.refresh(link)
    assert link.click_count == 1


async def test_click_out_of_bounds_code_422(client: AsyncClient) -> None:
    """Schema bounds: >20 chars and empty string both fail with 422.

    Empty-string rejection is STYLE-44-01 (min_length=1) -- previously
    it passed the schema and produced a no-op UPDATE.
    """
    assert await _click(client, "x" * 21) == 422
    assert await _click(client, "") == 422


async def test_click_rate_limit_429(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exceeding the per-IP budget -> 429; counts stop incrementing."""
    _agent, _token, link = await create_agent_with_link(client, db_session)

    # Lower the budget so the test stays fast. The router reads
    # settings per-request, so the patched value applies immediately.
    monkeypatch.setattr(
        settings, "referral_click_rate_limit_max_requests", 3
    )

    for _ in range(3):
        assert await _click(client, link.code) == 204

    assert await _click(client, link.code) == 429

    # The 429 request must not have incremented the counter.
    await db_session.refresh(link)
    assert link.click_count == 3
