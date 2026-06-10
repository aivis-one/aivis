# =============================================================================
# CBSHOME Backend -- Per-Link Stats Tests (Task 1 Block D)
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

from tests.helpers import (
    auth_headers,
    create_agent_with_link,
    register_user,
)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _create_second_link(
    client: AsyncClient, session: AsyncSession, token: str
) -> ReferralLink:
    """Create one more link for the same agent via the real endpoint."""
    resp = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    link_id = resp.json()["id"]
    return (
        await session.execute(
            select(ReferralLink).where(ReferralLink.id == link_id)
        )
    ).scalar_one()


async def _seed_registrations(
    client: AsyncClient, code: str, count: int
) -> list[str]:
    """Register `count` users through the real flow with `code`.

    Returns their user ids -- handy as investor_ids for purchases.
    """
    user_ids: list[str] = []
    for _ in range(count):
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
    link2 = await _create_second_link(client, db_session, token)

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
    link2 = await _create_second_link(client, db_session, token)

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
    """POST /links response carries the Block D fields, zeroed."""
    _agent, token, _link = await create_agent_with_link(client, db_session)

    resp = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["is_active"] is True
    assert body["click_count"] == 0
    assert body["registration_count"] == 0
    assert body["purchase_count"] == 0
