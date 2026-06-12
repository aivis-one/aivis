# =============================================================================
# CBSHOME Backend -- Referral Downline Tests (Task 2b, Blocks A+B)
# =============================================================================
#
# Tests cover:
#   1: The spec example tree (prompt §4) + L4 exclusion: X -> Y,I1,I2;
#      Y -> I3,Z; Z -> I4,W(agent); W -> I5. Expect investors
#      I1,I2=L1, I3=L2, I4=L3, I5 EXCLUDED (L4); sub_agents Y=1, Z=2,
#      W=3; agents never appear in investors[].
#   2: Inactive sub-agent breaks the chain (decision #6) -- the agent
#      disappears from sub_agents and its whole subtree drops out.
#   3: Volumes + counters + decision #8: investor volume counts ACTIVE
#      only (REVERSED excluded), sub-agent own purchases surface in
#      own_purchase_volume_cents, recruited count + direct volume are
#      direct-investor only.
#   4: PII masking (decision #5): profile name -> "First L.", email
#      fallback -> 2-char masked local-part; no '@' ever on the wire.
#   5: Empty agent -> both collections empty.
#   6: Non-agent -> 403.
#
# Tree building: real registration flow (register_user with
# referral_code), agents promoted by flipping User.role in the DB and
# creating a link via the real endpoint.
# =============================================================================

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from app.modules.pools.models import OptionPool
from app.modules.products.models import Product, ProductStatus
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User, UserRole
from tests.helpers import auth_headers, register_user

_PRICE = 1000


async def _make_agent(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    referral_code: str | None = None,
) -> tuple[UUID, str, str]:
    """Register a user, promote to agent, create a referral link.

    Returns (user_id, token, link_code).
    """
    data = await register_user(client, referral_code=referral_code)
    user_id = UUID(data["user"]["id"])
    token = data["session_token"]

    user = (await db_session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()

    resp = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return user_id, token, resp.json()["code"]


async def _make_investor(
    client: AsyncClient, referral_code: str
) -> UUID:
    """Register an investor under the given referral code."""
    data = await register_user(client, referral_code=referral_code)
    return UUID(data["user"]["id"])


async def _sale_target(
    db_session: AsyncSession, owner_id: UUID
) -> tuple[UUID, UUID]:
    """Minimal company + pool + product so Purchase FKs resolve.

    Returns (company_id, product_id). Row shapes mirror the seed script
    (same fixture pattern as test_pool_capacity).
    """
    tag = uuid4().hex[:8]
    company = CompanyProfile(
        user_id=owner_id,
        name=f"Downline Test Co {tag}",
        description="Task 2b downline test fixture.",
        logo_url=None,
        cover_url=None,
        promo_video_url=None,
        presentation_url=None,
        price_per_unit_cents=_PRICE,
        total_supply=1_000_000,
        shares_per_option=1,
        distribution_config={
            "company_pct": 0.80,
            "agent_levels": [0.10, 0.05, 0.05],
        },
        status=CompanyStatus.ACTIVE,
    )
    db_session.add(company)
    await db_session.flush()

    pool = OptionPool(
        company_id=company.id,
        equity_percent=Decimal("100.0000"),
        total_options=1_000_000,
        status="active",
    )
    db_session.add(pool)
    await db_session.flush()

    product = Product(
        company_id=company.id,
        pool_id=pool.id,
        name=f"Downline Product {tag}",
        description="Task 2b test product.",
        package_size=4,
        price_per_unit_cents=_PRICE,
        purchase_config={},
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()
    await db_session.commit()
    return company.id, product.id


def _purchase_row(
    buyer_id: UUID,
    company_id: UUID,
    product_id: UUID,
    *,
    paid_cents: int,
    status: str = PurchaseStatus.ACTIVE,
) -> Purchase:
    return Purchase(
        investor_id=buyer_id,
        product_id=product_id,
        company_id=company_id,
        legal_basis=PurchaseLegalBasis.SALE,
        units=max(1, paid_cents // _PRICE),
        paid_cents=paid_cents,
        price_per_unit_cents=_PRICE,
        status=status,
    )


async def _get_downline(
    client: AsyncClient, token: str
) -> dict:
    resp = await client.get(
        "/api/v1/referrals/downline/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_downline_example_tree_levels_and_l4_exclusion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The prompt §4 example, extended one hop to pin L4 exclusion."""
    x_id, x_token, code_x = await _make_agent(client, db_session)
    i1 = await _make_investor(client, code_x)
    i2 = await _make_investor(client, code_x)
    y_id, _, code_y = await _make_agent(
        client, db_session, referral_code=code_x
    )
    i3 = await _make_investor(client, code_y)
    z_id, _, code_z = await _make_agent(
        client, db_session, referral_code=code_y
    )
    i4 = await _make_investor(client, code_z)
    w_id, _, code_w = await _make_agent(
        client, db_session, referral_code=code_z
    )
    i5 = await _make_investor(client, code_w)  # would be L4 -> excluded

    body = await _get_downline(client, x_token)

    inv_levels = {e["user_id"]: e["level"] for e in body["investors"]}
    assert inv_levels == {
        str(i1): 1,
        str(i2): 1,
        str(i3): 2,
        str(i4): 3,
    }
    assert str(i5) not in inv_levels  # L4 excluded

    sub_levels = {e["user_id"]: e["level"] for e in body["sub_agents"]}
    assert sub_levels == {str(y_id): 1, str(z_id): 2, str(w_id): 3}

    # Agents never appear in investors[].
    assert str(y_id) not in inv_levels
    assert str(z_id) not in inv_levels


@pytest.mark.asyncio
async def test_downline_inactive_agent_breaks_chain(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Decision #6: deactivated sub-agent drops with its whole subtree."""
    x_id, x_token, code_x = await _make_agent(client, db_session)
    i1 = await _make_investor(client, code_x)
    y_id, _, code_y = await _make_agent(
        client, db_session, referral_code=code_x
    )
    i3 = await _make_investor(client, code_y)
    z_id, _, _ = await _make_agent(
        client, db_session, referral_code=code_y
    )

    y = (await db_session.execute(
        select(User).where(User.id == y_id)
    )).scalar_one()
    y.is_active = False
    await db_session.commit()

    body = await _get_downline(client, x_token)

    inv_ids = {e["user_id"] for e in body["investors"]}
    sub_ids = {e["user_id"] for e in body["sub_agents"]}
    assert inv_ids == {str(i1)}        # I3 dropped with Y's subtree
    assert sub_ids == set()            # Y inactive, Z unreachable
    assert str(z_id) not in sub_ids


@pytest.mark.asyncio
async def test_downline_volumes_counters_and_own_purchases(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Volumes: ACTIVE-only per investor; decision #8 own purchases of
    a sub-agent; recruited count + direct volume per sub-agent."""
    x_id, x_token, code_x = await _make_agent(client, db_session)
    i1 = await _make_investor(client, code_x)
    y_id, _, code_y = await _make_agent(
        client, db_session, referral_code=code_x
    )
    i3 = await _make_investor(client, code_y)

    company_id, product_id = await _sale_target(db_session, x_id)
    db_session.add_all([
        _purchase_row(i1, company_id, product_id, paid_cents=4_000),
        _purchase_row(i1, company_id, product_id, paid_cents=2_000),
        _purchase_row(
            i1, company_id, product_id,
            paid_cents=9_000, status=PurchaseStatus.REVERSED,
        ),
        # Decision #8: the sub-agent buys too.
        _purchase_row(y_id, company_id, product_id, paid_cents=5_000),
        _purchase_row(i3, company_id, product_id, paid_cents=3_000),
    ])
    await db_session.commit()

    body = await _get_downline(client, x_token)

    inv = {e["user_id"]: e for e in body["investors"]}
    assert inv[str(i1)]["purchase_volume_cents"] == 6_000  # reversed excluded
    assert inv[str(i3)]["purchase_volume_cents"] == 3_000

    sub = {e["user_id"]: e for e in body["sub_agents"]}
    y_entry = sub[str(y_id)]
    assert y_entry["recruited_investor_count"] == 1       # I3 only
    assert y_entry["direct_volume_cents"] == 3_000        # I3's purchases
    assert y_entry["own_purchase_volume_cents"] == 5_000  # decision #8


@pytest.mark.asyncio
async def test_downline_masks_pii(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Decision #5: masked names, uniform format, no email on the wire."""
    _, x_token, code_x = await _make_agent(client, db_session)
    i1 = await _make_investor(client, code_x)

    user = (await db_session.execute(
        select(User).where(User.id == i1)
    )).scalar_one()
    user.set_jsonb("profile", {"first_name": "Ivan", "last_name": "Petrov"})
    await db_session.commit()

    body = await _get_downline(client, x_token)
    inv = {e["user_id"]: e for e in body["investors"]}

    assert inv[str(i1)]["display_name"] == "Ivan P."
    for collection in (body["investors"], body["sub_agents"]):
        for entry in collection:
            assert "@" not in entry["display_name"]
            assert "Petrov" not in entry["display_name"]
            assert "email" not in entry and "phone" not in entry
            assert "kyc_status" not in entry


@pytest.mark.asyncio
async def test_downline_empty_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Agent with no referrals -> both collections empty."""
    _, x_token, _ = await _make_agent(client, db_session)
    body = await _get_downline(client, x_token)
    assert body == {"investors": [], "sub_agents": []}


@pytest.mark.asyncio
async def test_downline_non_agent_403(client: AsyncClient) -> None:
    """Plain investor -> 403."""
    data = await register_user(client)
    resp = await client.get(
        "/api/v1/referrals/downline/me",
        headers=auth_headers(data["session_token"]),
    )
    assert resp.status_code == 403
