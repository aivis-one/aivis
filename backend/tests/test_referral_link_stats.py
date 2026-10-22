# =============================================================================
# AIVIS.ONE Backend -- Per-Link Stats Tests (Task 1 Block D)
# =============================================================================
#
# Covers GET /api/v1/referrals/links/me and GET /api/v1/referrals/stats/me
# after the Block D extension:
#
#   - links/me returns per-link click_count / registration_count /
#     purchase_count + is_active, and the counters are attributed to
#     the RIGHT link (two links with different seeded numbers).
#   - stats/me returns total_clicks / total_registrations on top of the
#     pre-existing totals, summed across the agent's links only.
#   - a fresh agent/link reports zeroes everywhere.
#   - POST /links response carries the new contract fields (zeroed).
#
# SEEDING STRATEGY:
#   clicks        -> direct column set (the HTTP increment path is
#                    already covered by test_referral_clicks.py)
#   registrations -> real register flow with referral_code (the capture
#                    path from Block C, end-to-end)
#   purchases     -> direct Purchase + ReferralAttribution rows against
#                    a SEEDED product (the dev DB always carries the
#                    storefront seed; test_regression_guards relies on
#                    seeded rows the same way). Full purchase flow is
#                    out of scope here -- attribution counting is what
#                    Block D adds.
# =============================================================================

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.modules.products.models import Product
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.referrals.models import ReferralAttribution, ReferralLink
from app.modules.referrals.service import create_link
from app.modules.users.models import User

from tests.helpers import (
    auth_headers,
    create_agent_with_link,
    register_user,
)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _create_second_link(
    session: AsyncSession, agent: User
) -> ReferralLink:
    """A second link for the same agent, written by the service.

    POST /referrals/links now returns the agent's one link instead of
    issuing another, so data that holds several links (older agents)
    is built here directly."""
    link = await create_link(agent, session)
    await session.commit()
    return link


async def _clear_email_auth_rate_limit() -> None:
    """Drop the shared email-auth rate-limit key (5 req / 60s per IP).

    conftest.clear_rate_limit resets it BEFORE each test, but the
    stats test below performs 6 register calls WITHIN one test (two
    agents + four referred users) -- one over the budget. Mirroring
    the conftest approach mid-test keeps the seeding honest without
    weakening the production limit.
    """
    from app.core.redis import get_redis

    redis = get_redis()
    await redis.delete("email_auth:127.0.0.1")


async def _seed_registrations(
    client: AsyncClient, code: str, count: int
) -> list[str]:
    """Register `count` users through the real flow with `code`.

    Returns their user ids -- handy as investor_ids for purchases.
    Clears the per-IP auth rate limit before every call so multi-agent
    seeding inside a single test never trips the 5/60s budget.
    """
    user_ids: list[str] = []
    for _ in range(count):
        await _clear_email_auth_rate_limit()
        body = await register_user(client, referral_code=code)
        user_ids.append(body["user"]["id"])
    return user_ids


async def _seed_attributed_purchase(
    session: AsyncSession,
    investor_id: str,
    link_id: UUID,
) -> None:
    """Insert a minimal Purchase + ReferralAttribution pair.

    Uses any seeded storefront product (the dev DB seed guarantees
    one) -- attribution counting only needs valid FKs, not a real
    purchase flow.
    """
    product = (
        await session.execute(select(Product).limit(1))
    ).scalar_one_or_none()
    assert product is not None, (
        "No seeded products found. The storefront seed must run before "
        "tests (install/update scripts do this)."
    )

    purchase = Purchase(
        investor_id=investor_id,
        product_id=product.id,
        company_id=product.company_id,
        legal_basis=PurchaseLegalBasis.SALE,
        units=1,
        paid_cents=100,
        price_per_unit_cents=100,
        status=PurchaseStatus.ACTIVE,
    )
    session.add(purchase)
    await session.flush()

    session.add(
        ReferralAttribution(
            purchase_id=purchase.id,
            referral_link_id=link_id,
        )
    )
    await session.commit()


async def _set_clicks(
    session: AsyncSession, link: ReferralLink, clicks: int
) -> None:
    """Seed the raw click counter directly (HTTP path covered in B)."""
    link.click_count = clicks
    await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_links_me_counts_are_per_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two links with different seeded numbers -> each row carries
    exactly its own clicks / registrations / purchases.
    """
    agent, token, link1 = await create_agent_with_link(client, db_session)
    link2 = await _create_second_link(db_session, agent)

    # link1: 3 clicks, 2 registrations, 2 purchases.
    await _set_clicks(db_session, link1, 3)
    users1 = await _seed_registrations(client, link1.code, 2)
    await _seed_attributed_purchase(db_session, users1[0], link1.id)
    await _seed_attributed_purchase(db_session, users1[1], link1.id)

    # link2: 1 click, 1 registration, 0 purchases.
    await _set_clicks(db_session, link2, 1)
    await _seed_registrations(client, link2.code, 1)

    resp = await client.get(
        "/api/v1/referrals/links/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2

    by_id = {item["id"]: item for item in body["items"]}
    row1 = by_id[str(link1.id)]
    row2 = by_id[str(link2.id)]

    assert row1["click_count"] == 3
    assert row1["registration_count"] == 2
    assert row1["purchase_count"] == 2
    assert row1["is_active"] is True

    assert row2["click_count"] == 1
    assert row2["registration_count"] == 1
    assert row2["purchase_count"] == 0
    assert row2["is_active"] is True


async def test_stats_me_totals_summed_across_links(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """stats/me sums clicks/registrations/purchases over the agent's
    own links only (a second agent's activity must not leak in).
    """
    _agent, token, link1 = await create_agent_with_link(client, db_session)
    link2 = await _create_second_link(db_session, _agent)

    await _set_clicks(db_session, link1, 5)
    await _set_clicks(db_session, link2, 2)
    users1 = await _seed_registrations(client, link1.code, 2)
    await _seed_registrations(client, link2.code, 1)
    await _seed_attributed_purchase(db_session, users1[0], link1.id)

    # Noise: a different agent with its own activity.
    _other, _otoken, other_link = await create_agent_with_link(
        client, db_session
    )
    await _set_clicks(db_session, other_link, 100)
    other_users = await _seed_registrations(client, other_link.code, 1)
    await _seed_attributed_purchase(
        db_session, other_users[0], other_link.id
    )

    resp = await client.get(
        "/api/v1/referrals/stats/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    stats = resp.json()

    assert stats["total_links"] == 2
    assert stats["total_clicks"] == 7
    assert stats["total_registrations"] == 3
    assert stats["total_purchases"] == 1
    assert isinstance(stats["total_commission_cents"], int)


async def test_fresh_agent_reports_zeroes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A fresh agent with one untouched link -> zeroes everywhere."""
    _agent, token, link = await create_agent_with_link(client, db_session)

    resp = await client.get(
        "/api/v1/referrals/links/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    (item,) = resp.json()["items"]
    assert item["id"] == str(link.id)
    assert item["click_count"] == 0
    assert item["registration_count"] == 0
    assert item["purchase_count"] == 0

    resp = await client.get(
        "/api/v1/referrals/stats/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    assert stats["total_links"] == 1
    assert stats["total_clicks"] == 0
    assert stats["total_registrations"] == 0
    assert stats["total_purchases"] == 0


async def test_create_link_response_contract(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /links carries the Block D fields. The agent has one link
    already (create_agent_with_link issued it), so the call returns that
    link (200) and creates no second one."""
    _agent, token, link = await create_agent_with_link(client, db_session)

    resp = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(link.id)
    assert body["code"] == link.code

    assert body["is_active"] is True
    assert body["click_count"] == 0
    assert body["registration_count"] == 0
    assert body["purchase_count"] == 0


async def test_link_refused_until_the_integrator_agreement_is_signed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An agent who has not signed the integrator agreement (agent_integrator_agreement) gets
    403 agent_agreement_not_signed and no link; after signing, 201."""
    from tests.helpers import sign_agent_agreement

    # create_agent_with_link creates a link itself, so build the agent by hand.
    from app.modules.users.models import User, UserRole

    data = await register_user(client)
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])
    user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()

    refused = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"] == "agent_agreement_not_signed"
    links = (
        await db_session.execute(
            select(ReferralLink).where(ReferralLink.agent_id == user_id)
        )
    ).scalars().all()
    assert links == []

    await sign_agent_agreement(user_id)
    accepted = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert accepted.status_code == 201, accepted.text


async def test_an_agent_has_exactly_one_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The first POST issues the link (201); every later POST returns the
    same link with its counters (200); only one row exists."""
    agent, token, link = await create_agent_with_link(client, db_session)
    await _set_clicks(db_session, link, 4)

    for _ in range(2):
        resp = await client.post(
            "/api/v1/referrals/links", headers=auth_headers(token)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == str(link.id)
        assert body["click_count"] == 4

    rows = (
        await db_session.execute(
            select(ReferralLink).where(ReferralLink.agent_id == agent.id)
        )
    ).scalars().all()
    assert len(rows) == 1
