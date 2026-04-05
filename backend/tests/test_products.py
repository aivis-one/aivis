# =============================================================================
# CBSHOME Backend -- Product Tests (Sprint 4.2)
# =============================================================================
#
# Tests cover:
#   1:  Admin creates product -> 201
#   2:  Staff without financial_operations cannot create product -> 403
#   3:  Update product name -> 200
#   4:  Update gift_units without financial_operations -> 403
#   5:  Status transition hidden -> active -> archived
#   6:  Invalid status transition -> 400
#   7:  Create installment with valid plan_config -> 201
#   8:  Invalid plan_config (sum != 100) -> 400
#   9:  Delete installment (soft) -> 204, not visible in detail
#   10: Price cascade soft-deletes installments
#   11: Public list shows only active products
#   12: Public detail includes installments and sold_units stub
#
# Email prefix: "s42_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.models import ProductInstallment
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s42_"

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


async def _create_company(
    client: AsyncClient, admin_token: str, suffix: str = "co"
) -> dict:
    """Helper: create a company and return response."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    return resp.json()


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    suffix: str = "pkg",
    units: int = 100,
    gift_units: int = 0,
) -> dict:
    """Helper: create a product and return response."""
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Package {suffix}",
            "description": f"Test package {suffix}",
            "units": units,
            "gift_units": gift_units,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create product failed: {resp.text}"
    return resp.json()


def _valid_plan_config(units: int = 100, price: int = 10000) -> dict:
    """Build a valid plan_config for given product params."""
    total = units * price  # 1_000_000
    per_tranche = total // 6
    last_tranche = total - (per_tranche * 5)
    return {
        "tranches": [
            {"amount_cents": per_tranche, "units_percent": 10},
            {"amount_cents": per_tranche, "units_percent": 10},
            {"amount_cents": per_tranche, "units_percent": 10},
            {"amount_cents": per_tranche, "units_percent": 10},
            {"amount_cents": per_tranche, "units_percent": 10},
            {"amount_cents": last_tranche, "units_percent": 50},
        ],
        "bonus_units": 10,
        "agent_bonus_units": 5,
    }


# ---------------------------------------------------------------------------
# Test 1: Admin creates product
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admin creates product -> 201, status=hidden, price from company."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token)
    product = await _create_product(client, token, company["id"])

    assert product["name"] == "Package pkg"
    assert product["status"] == "hidden"
    assert product["units"] == 100
    assert product["price_per_unit_cents"] == 10000
    assert product["company_id"] == company["id"]


# ---------------------------------------------------------------------------
# Test 2: Staff without financial_operations -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product_no_financial_ops(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff with company_manage but no financial_operations -> 403."""
    from uuid import UUID

    from app.modules.staff.constants import VALID_PERMISSION_KEYS
    from app.modules.staff.models import StaffProfile
    from app.modules.users.models import User, UserRole
    from tests.helpers import login_user

    # Create admin to make a company first.
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, suffix="co2")

    # Create staff without financial_operations.
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
        user_id=user_id, permissions=perms, is_active=True
    )
    db_session.add(profile)
    await db_session.commit()

    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}nofin@example.com"
    )
    nofin_token = login_data["session_token"]

    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Blocked",
            "units": 50,
        },
        headers=auth_headers(nofin_token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 3: Update product name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_product_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Update product name -> 200."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co3")
    product = await _create_product(client, token, company["id"])

    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}",
        json={"name": "Renamed Package"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Package"


# ---------------------------------------------------------------------------
# Test 4: Update gift_units without financial_operations -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_gift_units_no_financial_ops(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff with company_manage but no financial_operations cannot update gift_units."""
    from uuid import UUID

    from app.modules.staff.constants import VALID_PERMISSION_KEYS
    from app.modules.staff.models import StaffProfile
    from app.modules.users.models import User, UserRole
    from tests.helpers import login_user

    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, suffix="co4")
    product = await _create_product(client, admin_token, company["id"])

    # Create staff without financial_operations.
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}nofin4@example.com"
    )
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.STAFF

    perms = {key: True for key in VALID_PERMISSION_KEYS}
    perms["financial_operations"] = False
    profile = StaffProfile(
        user_id=user_id, permissions=perms, is_active=True
    )
    db_session.add(profile)
    await db_session.commit()

    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}nofin4@example.com"
    )
    nofin_token = login_data["session_token"]

    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}",
        json={"gift_units": 10},
        headers=auth_headers(nofin_token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 5: Status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_transitions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """hidden -> active -> archived."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co5")
    product = await _create_product(client, token, company["id"])

    # hidden -> active
    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # active -> archived
    resp2 = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "archived"},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "archived"


# ---------------------------------------------------------------------------
# Test 6: Invalid status transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_status_transition(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """archived -> active -> 400."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co6")
    product = await _create_product(client, token, company["id"])

    # hidden -> archived
    await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "archived"},
        headers=auth_headers(token),
    )

    # archived -> active (invalid)
    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 7: Create installment with valid plan_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_installment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Create installment with valid plan_config -> 201."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co7")
    product = await _create_product(client, token, company["id"])

    config = _valid_plan_config()
    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "6-Month Plan", "plan_config": config},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    inst = resp.json()
    assert inst["name"] == "6-Month Plan"
    assert inst["plan_config"]["bonus_units"] == 10


# ---------------------------------------------------------------------------
# Test 8: Invalid plan_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_plan_config(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """plan_config with units_percent sum != 100 -> 400."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co8")
    product = await _create_product(client, token, company["id"])

    bad_config = _valid_plan_config()
    # Break units_percent sum (change last from 50 to 40 -> sum=90).
    bad_config["tranches"][-1]["units_percent"] = 40

    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "Bad Plan", "plan_config": bad_config},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "units_percent" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Test 9: Delete installment (soft)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_installment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Soft-delete installment -> 204, not in detail."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co9")
    product = await _create_product(client, token, company["id"])

    config = _valid_plan_config()
    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "To Delete", "plan_config": config},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    inst_id = resp.json()["id"]

    # Delete.
    resp2 = await client.delete(
        f"/api/v1/staff/products/{product['id']}/installments/{inst_id}",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 204

    # Not in public detail.
    # First publish: hidden -> active.
    await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    resp3 = await client.get(f"/api/v1/products/{product['id']}")
    assert resp3.status_code == 200
    assert len(resp3.json()["installments"]) == 0


# ---------------------------------------------------------------------------
# Test 10: Price cascade soft-deletes installments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_price_cascade_deletes_installments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Company price change -> product price updated, installments soft-deleted."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="casc")
    product = await _create_product(client, token, company["id"])

    # Create installment.
    config = _valid_plan_config()
    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "Will Be Deleted", "plan_config": config},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    # Change company price.
    resp2 = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/price",
        json={"price_per_unit_cents": 15000},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200

    # Verify: product price updated.
    from uuid import UUID
    from app.modules.products.models import Product

    stmt = select(Product).where(Product.id == UUID(product["id"]))
    result = await db_session.execute(stmt)
    p = result.scalar_one()
    assert p.price_per_unit_cents == 15000

    # Verify: installment soft-deleted.
    inst_stmt = select(ProductInstallment).where(
        ProductInstallment.product_id == UUID(product["id"]),
        ProductInstallment.is_deleted == False,  # noqa: E712
    )
    inst_result = await db_session.execute(inst_stmt)
    assert len(inst_result.scalars().all()) == 0


# ---------------------------------------------------------------------------
# Test 11: Public list shows only active products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_active_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public GET /products returns only active products."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="pub")

    p1 = await _create_product(client, token, company["id"], suffix="a")
    p2 = await _create_product(client, token, company["id"], suffix="b")

    # Publish p1: hidden -> active.
    await client.patch(
        f"/api/v1/staff/products/{p1['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )

    resp = await client.get("/api/v1/products")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["items"]]
    assert p1["id"] in ids
    assert p2["id"] not in ids


# ---------------------------------------------------------------------------
# Test 12: Public detail includes installments and sold_units stub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_with_installments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public detail includes installments and sold_units=0 stub."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="det")
    product = await _create_product(client, token, company["id"])

    # Create installment.
    config = _valid_plan_config()
    await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "Visible Plan", "plan_config": config},
        headers=auth_headers(token),
    )

    # Publish.
    await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )

    resp = await client.get(f"/api/v1/products/{product['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sold_units"] == 0
    assert len(body["installments"]) == 1
    assert body["installments"][0]["name"] == "Visible Plan"
