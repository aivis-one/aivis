# =============================================================================
# CBSHOME Backend -- Company Tests (Sprint 4.1)
# =============================================================================
#
# Tests cover:
#   1:  Admin creates company -> 201
#   2:  Non-admin (staff without company_manage) -> 403
#   3:  Staff without financial_operations cannot create company -> 403
#   4:  Invalid distribution_config -> 400
#   5:  Update company profile -> 200
#   6:  Update price -> 200, price history created
#   7:  Create roadmap item -> 201
#   8:  Reorder roadmap items -> 200
#   9:  Delete (soft) roadmap item -> 204
#   10: Public list shows only active companies
#
# Email prefix: "s41_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import CompanyPriceHistory, CompanyProfile
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    create_staff_user,
    register_user,
)

EMAIL_PREFIX = "s41_"

# Reusable valid distribution config.
VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


def _company_payload(suffix: str = "acme") -> dict:
    """Helper: build a valid CreateCompanyRequest body."""
    return {
        "email": f"{EMAIL_PREFIX}{suffix}@example.com",
        "password": "companypass123",
        "name": f"Test Company {suffix}",
        "description": "A test company",
        "price_per_unit_cents": 10000,
        "distribution_config": VALID_DIST_CONFIG,
    }


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "acme",
) -> dict:
    """Helper: create a company and return response body."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json=_company_payload(suffix),
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1: Admin creates company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admin creates company -> 201, status=hidden."""
    token = await _admin_token(client, db_session)
    body = await _create_company(client, token)

    assert body["name"] == "Test Company acme"
    assert body["status"] == "hidden"
    assert body["price_per_unit_cents"] == 10000
    assert body["distribution_config"] == VALID_DIST_CONFIG


# ---------------------------------------------------------------------------
# Test 2: Staff without company_manage -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_company_no_company_manage(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff without company_manage permission -> 403."""
    from app.modules.staff.constants import VALID_PERMISSION_KEYS
    from app.modules.staff.models import StaffProfile
    from app.modules.users.models import User, UserRole
    from uuid import UUID

    # Create staff with company_manage=False.
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}nocompany@example.com"
    )
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.STAFF

    perms = {key: True for key in VALID_PERMISSION_KEYS}
    perms["company_manage"] = False

    profile = StaffProfile(
        user_id=user_id,
        permissions=perms,
        is_active=True,
    )
    db_session.add(profile)
    await db_session.commit()

    from tests.helpers import login_user
    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}nocompany@example.com"
    )
    token = login_data["session_token"]

    resp = await client.post(
        "/api/v1/staff/companies",
        json=_company_payload("blocked"),
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 3: Staff without financial_operations cannot create company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_company_no_financial_ops(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff with company_manage but without financial_operations -> 403."""
    from app.modules.staff.constants import VALID_PERMISSION_KEYS
    from app.modules.staff.models import StaffProfile
    from app.modules.users.models import User, UserRole
    from uuid import UUID

    data = await register_user(
        client, email=f"{EMAIL_PREFIX}nofin@example.com"
    )
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.STAFF

    perms = {key: True for key in VALID_PERMISSION_KEYS}
    perms["financial_operations"] = False

    profile = StaffProfile(
        user_id=user_id,
        permissions=perms,
        is_active=True,
    )
    db_session.add(profile)
    await db_session.commit()

    from tests.helpers import login_user
    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}nofin@example.com"
    )
    token = login_data["session_token"]

    resp = await client.post(
        "/api/v1/staff/companies",
        json=_company_payload("nofin"),
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 4: Invalid distribution_config -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_company_invalid_distribution(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """distribution_config exceeding 1.0 -> 400."""
    token = await _admin_token(client, db_session)
    payload = _company_payload("bad")
    payload["distribution_config"] = {
        "company_pct": 0.80,
        "agent_levels": [0.15, 0.10],  # total = 1.05 > 1.0
    }

    resp = await client.post(
        "/api/v1/staff/companies",
        json=payload,
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "exceeds 1.0" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Test 5: Update company profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_company_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Update company name and description -> 200."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token)

    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"name": "Updated Name", "description": "New description"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"
    assert resp.json()["description"] == "New description"


# ---------------------------------------------------------------------------
# Test 6: Update price -> history created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_price_creates_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Price update -> 200, CompanyPriceHistory record created."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="price")

    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/price",
        json={"price_per_unit_cents": 15000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["price_per_unit_cents"] == 15000

    # Verify history record exists.
    from uuid import UUID
    stmt = select(CompanyPriceHistory).where(
        CompanyPriceHistory.company_id == UUID(company["id"])
    )
    result = await db_session.execute(stmt)
    history = result.scalars().all()
    assert len(history) == 1
    assert history[0].price_per_unit_cents == 15000


# ---------------------------------------------------------------------------
# Test 7: Create roadmap item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_roadmap_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Add roadmap item -> 201, order auto-assigned."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="road")

    resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/roadmap",
        json={"title": "Phase 1 Launch", "description": "Initial release"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    item = resp.json()
    assert item["title"] == "Phase 1 Launch"
    assert item["status"] == "planned"
    assert item["order"] == 0


# ---------------------------------------------------------------------------
# Test 8: Reorder roadmap items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_roadmap(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Create 3 items, reorder them -> new order applied."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="reord")

    # Create 3 items.
    items = []
    for title in ["Alpha", "Beta", "Gamma"]:
        resp = await client.post(
            f"/api/v1/staff/companies/{company['id']}/roadmap",
            json={"title": title},
            headers=auth_headers(token),
        )
        assert resp.status_code == 201
        items.append(resp.json())

    # Reverse order.
    reversed_ids = [items[2]["id"], items[1]["id"], items[0]["id"]]
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/roadmap/reorder",
        json={"item_ids": reversed_ids},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    reordered = resp.json()
    assert reordered[0]["title"] == "Gamma"
    assert reordered[0]["order"] == 0
    assert reordered[2]["title"] == "Alpha"
    assert reordered[2]["order"] == 2


# ---------------------------------------------------------------------------
# Test 9: Soft-delete roadmap item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_roadmap_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Delete roadmap item -> 204, not visible in detail."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="del")

    # Create item.
    resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/roadmap",
        json={"title": "To Be Deleted"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    item = resp.json()

    # Delete.
    resp2 = await client.delete(
        f"/api/v1/staff/companies/{company['id']}/roadmap/{item['id']}",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 204

    # Verify not in detail.
    resp3 = await client.get(f"/api/v1/companies/{company['id']}")
    assert resp3.status_code == 200
    assert len(resp3.json()["roadmap"]) == 0


# ---------------------------------------------------------------------------
# Test 10: Public list shows only active companies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_active_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public GET /companies returns only active companies."""
    token = await _admin_token(client, db_session)

    # Create two companies (both start as hidden).
    c1 = await _create_company(client, token, suffix="pub1")
    c2 = await _create_company(client, token, suffix="pub2")

    # Publish c1: hidden -> active.
    resp = await client.patch(
        f"/api/v1/staff/companies/{c1['id']}",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200

    # Public list should show only c1.
    resp2 = await client.get("/api/v1/companies")
    assert resp2.status_code == 200
    body = resp2.json()
    ids = [c["id"] for c in body["items"]]
    assert c1["id"] in ids
    assert c2["id"] not in ids
