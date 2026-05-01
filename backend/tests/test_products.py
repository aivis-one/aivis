# =============================================================================
# CBSHOME Backend -- Product Tests (Sprint 4.2 + Sprint 6.1 + Sprint F4.1)
# =============================================================================
#
# Tests cover:
#   1:  Admin creates product -> 201
#   2:  Staff without financial_operations cannot create product -> 403
#   3:  Update product name -> 200
#   4:  Update purchase_config without financial_operations -> 403
#   5:  Status transition hidden -> active -> archived
#   6:  Invalid status transition -> 400
#   7:  Create installment with valid plan_config -> 201
#   8:  Invalid plan_config (sum != 100) -> 400
#   9:  Delete installment (soft) -> 204, not visible in detail
#   10: Price cascade soft-deletes installments
#   11: Public list shows only active products
#   12: Public detail includes installments and available_packages
#   13: Product cover_url round-trip (create + update + staff response)
#   14: Public list denormalises company_name / company_logo_url /
#       company_cover_url + product cover_url
#   15: Public detail denormalises company fields
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
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co",
    *,
    logo_url: str | None = None,
    cover_url: str | None = None,
) -> dict:
    """Helper: create a company and return response.

    Sprint 4.3: also creates the active OptionPool with equity_percent=100,
    so subsequent _create_product() calls can attach to it.
    """
    body: dict = {
        "email": f"{EMAIL_PREFIX}{suffix}@example.com",
        "password": "companypass123",
        "name": f"Test Company {suffix}",
        "price_per_unit_cents": 10000,
        "distribution_config": VALID_DIST_CONFIG,
        # Sprint 4.3:
        "total_supply": 1_000_000,
        "shares_per_option": 1,
    }
    if logo_url is not None:
        body["logo_url"] = logo_url
    if cover_url is not None:
        body["cover_url"] = cover_url

    resp = await client.post(
        "/api/v1/staff/companies",
        json=body,
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    company = resp.json()

    # Sprint 4.3: products require an active pool. Create one with the
    # whole supply allocated (equity_percent=100) -- tests don't care
    # about a partial allocation, they only need product creation to
    # succeed.
    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, f"Create pool failed: {pool_resp.text}"

    return company


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    """Helper: set company status to active."""
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    suffix: str = "pkg",
    units: int = 100,
    *,
    cover_url: str | None = None,
) -> dict:
    """Helper: create a product and return response."""
    body: dict = {
        "company_id": company_id,
        "name": f"Package {suffix}",
        "description": f"Test package {suffix}",
        "package_size": units,  # Sprint 4.3: column renamed
    }
    if cover_url is not None:
        body["cover_url"] = cover_url

    resp = await client.post(
        "/api/v1/staff/products",
        json=body,
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
    assert product["package_size"] == 100  # Sprint 4.3: column renamed
    assert product["price_per_unit_cents"] == 10000
    assert product["company_id"] == company["id"]
    # Sprint 4.3: product carries the pool it was attached to.
    assert "pool_id" in product


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
            "package_size": 50,  # Sprint 4.3: column renamed
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
# Test 4: Update purchase_config without financial_operations -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_purchase_config_no_financial_ops(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff with company_manage but no financial_operations cannot update purchase_config."""
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
        json={"purchase_config": {"bonuses": []}},
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
# Test 7: Create installment
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
    body = resp.json()
    assert body["name"] == "6-Month Plan"
    assert body["product_id"] == product["id"]


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

    config = _valid_plan_config()
    config["tranches"][0]["units_percent"] = 99  # sum > 100

    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "Bad Plan", "plan_config": config},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 9: Delete installment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_installment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Soft-delete installment -> 204, not visible in detail."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co9")
    product = await _create_product(client, token, company["id"])

    config = _valid_plan_config()
    create_resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "To Delete", "plan_config": config},
        headers=auth_headers(token),
    )
    inst_id = create_resp.json()["id"]

    # Delete.
    del_resp = await client.delete(
        f"/api/v1/staff/products/{product['id']}/installments/{inst_id}",
        headers=auth_headers(token),
    )
    assert del_resp.status_code == 204

    # Verify not visible in DB (soft-deleted).
    stmt = select(ProductInstallment).where(
        ProductInstallment.id == inst_id
    )
    result = await db_session.execute(stmt)
    inst = result.scalar_one()
    assert inst.is_deleted is True


# ---------------------------------------------------------------------------
# Test 10: Price cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_price_cascade_deletes_installments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Price change soft-deletes installment templates."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co10")
    product = await _create_product(client, token, company["id"])

    # Create installment.
    config = _valid_plan_config()
    create_resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "Will Be Deleted", "plan_config": config},
        headers=auth_headers(token),
    )
    inst_id = create_resp.json()["id"]

    # Change price.
    await client.patch(
        f"/api/v1/staff/companies/{company['id']}/price",
        json={"price_per_unit_cents": 20000},
        headers=auth_headers(token),
    )

    # Verify installment is soft-deleted.
    stmt = select(ProductInstallment).where(
        ProductInstallment.id == inst_id
    )
    result = await db_session.execute(stmt)
    inst = result.scalar_one()
    assert inst.is_deleted is True


# ---------------------------------------------------------------------------
# Test 11: Public list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_active_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public product list shows only active products."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="co11")

    p1 = await _create_product(client, token, company["id"], suffix="a")
    p2 = await _create_product(client, token, company["id"], suffix="b")

    # Activate p1 only.
    await client.patch(
        f"/api/v1/staff/products/{p1['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )

    resp = await client.get(
        "/api/v1/products",
        params={"company_id": company["id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == p1["id"]


# ---------------------------------------------------------------------------
# Test 12: Public detail with installments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_with_installments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public detail includes installments and available_packages."""
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
    # Sprint 4.3: was sold_units (count of purchases). Now available_packages
    # = floor(pool_remaining / package_size). Empty company => 1_000_000 / 100
    # = 10_000 packages.
    assert body["available_packages"] == 10_000
    assert len(body["installments"]) == 1
    assert body["installments"][0]["name"] == "Visible Plan"


# ---------------------------------------------------------------------------
# Test 13: Product cover_url round-trip (Sprint F4.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_product_cover_url_round_trip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """cover_url is persisted on create, editable via PATCH, cleared via null."""
    token = await _admin_token(client, db_session)
    company = await _create_company(client, token, suffix="cov")

    # Create with cover_url.
    created = await _create_product(
        client,
        token,
        company["id"],
        suffix="cv",
        cover_url="https://cdn.example.com/products/initial.jpg",
    )
    assert created["cover_url"] == "https://cdn.example.com/products/initial.jpg"

    # Update cover_url.
    resp = await client.patch(
        f"/api/v1/staff/products/{created['id']}",
        json={"cover_url": "https://cdn.example.com/products/updated.jpg"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["cover_url"] == "https://cdn.example.com/products/updated.jpg"

    # Clear cover_url with explicit null.
    resp2 = await client.patch(
        f"/api/v1/staff/products/{created['id']}",
        json={"cover_url": None},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["cover_url"] is None


# ---------------------------------------------------------------------------
# Test 14: Public list denormalises company fields + cover_url (Sprint F4.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_denormalises_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public list returns product cover_url + company_name / logo_url / cover_url."""
    token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        token,
        suffix="dn",
        logo_url="https://cdn.example.com/co/logo.png",
        cover_url="https://cdn.example.com/co/cover.jpg",
    )
    await _activate_company(client, token, company["id"])

    product = await _create_product(
        client,
        token,
        company["id"],
        suffix="dn1",
        cover_url="https://cdn.example.com/p/hero.jpg",
    )

    # Publish product.
    await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )

    resp = await client.get(
        "/api/v1/products",
        params={"company_id": company["id"]},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]

    assert item["cover_url"] == "https://cdn.example.com/p/hero.jpg"
    assert item["company_name"] == company["name"]
    assert item["company_logo_url"] == "https://cdn.example.com/co/logo.png"
    assert item["company_cover_url"] == "https://cdn.example.com/co/cover.jpg"


# ---------------------------------------------------------------------------
# Test 15: Public detail denormalises company fields (Sprint F4.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_denormalises_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public detail returns product cover_url + company fields.

    Also verifies the null-cover_url case: product without cover_url
    should return cover_url=None (client falls back to company logo).
    """
    token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        token,
        suffix="dd",
        logo_url="https://cdn.example.com/co2/logo.png",
    )
    await _activate_company(client, token, company["id"])

    # No cover_url on product -- client fallback scenario.
    product = await _create_product(client, token, company["id"], suffix="dd1")

    # Publish.
    await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(token),
    )

    resp = await client.get(f"/api/v1/products/{product['id']}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["cover_url"] is None
    assert body["company_name"] == company["name"]
    assert body["company_logo_url"] == "https://cdn.example.com/co2/logo.png"
    assert body["company_cover_url"] is None
