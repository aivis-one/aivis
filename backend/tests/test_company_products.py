# =============================================================================
# AIVIS.ONE Backend -- Company's own products and deactivation
# =============================================================================
#
# Tests cover:
#   1: GET /company/products lists the caller's own products in every status,
#      hidden and archived included; another company's products are absent
#   2: GET /company/products by a non-company -> 403
#   3: A company with an ACTIVE product cannot deactivate itself
#      (409 company_has_active_products); nothing changes
#   4: Once the product is hidden the same company can deactivate itself
#   5: A project cannot move active -> hidden while it has an ACTIVE product
#      (409 company_has_active_products); once the product is hidden it can
#      be; the same refusal binds the staff PATCH (test 6)
#
# Companies are created the way test_companies_me.py creates them
# (POST /staff/companies as an admin, then the ordinary email login).
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from tests.helpers import auth_headers, create_admin_user, login_user, register_user

COMPANY_PASSWORD = "companypass123"


async def _company_with_login(
    client: AsyncClient, admin_token: str
) -> tuple[str, str]:
    """Create a company with an active pool and log in as it.

    Returns (company_id, company_session_token).
    """
    email = f"coprod_{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": COMPANY_PASSWORD,
            "name": f"ProductsCo {uuid.uuid4().hex[:8]}",
            "description": "A test company",
            "price_per_unit_cents": 10_000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    company_id = resp.json()["id"]

    pool = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool.status_code == 201, pool.text

    activate = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activate.status_code == 200, activate.text

    login = await login_user(client, email=email, password=COMPANY_PASSWORD)
    return company_id, login["session_token"]


async def _product(
    client: AsyncClient, admin_token: str, company_id: str, name: str
) -> str:
    resp = await client.post(
        "/api/v1/staff/products",
        json={"company_id": company_id, "name": name, "package_size": 10},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _set_product_status(
    client: AsyncClient, admin_token: str, product_id: str, status: str
) -> None:
    resp = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": status},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_company_lists_its_own_products_in_every_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hidden (the default) and archived products are listed; a second
    company's product is not."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, token = await _company_with_login(client, admin_token)
    other_id, _ = await _company_with_login(client, admin_token)

    hidden = await _product(client, admin_token, company_id, "Hidden one")
    archived = await _product(client, admin_token, company_id, "Archived one")
    await _set_product_status(client, admin_token, archived, "archived")
    foreign = await _product(client, admin_token, other_id, "Not mine")

    resp = await client.get("/api/v1/company/products", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_id = {item["id"]: item["status"] for item in body["items"]}
    assert by_id[hidden] == "hidden"
    assert by_id[archived] == "archived"
    assert foreign not in by_id
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_company_products_refused_to_a_non_company(
    client: AsyncClient,
) -> None:
    """An investor has no company profile -> 403."""
    data = await register_user(client)
    resp = await client.get(
        "/api/v1/company/products", headers=auth_headers(data["session_token"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_company_cannot_deactivate_with_an_active_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """At least one ACTIVE product = a sale is running = deactivation is
    refused with a code; hiding the product lifts the refusal."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, token = await _company_with_login(client, admin_token)
    product_id = await _product(client, admin_token, company_id, "On sale")
    await _set_product_status(client, admin_token, product_id, "active")

    refused = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": COMPANY_PASSWORD},
        headers=auth_headers(token),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "company_has_active_products"

    me = await client.get("/api/v1/users/me", headers=auth_headers(token))
    assert me.status_code == 200
    user = await db_session.get(User, uuid.UUID(me.json()["id"]))
    await db_session.refresh(user)
    assert user.is_active is True

    await _set_product_status(client, admin_token, product_id, "hidden")
    allowed = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": COMPANY_PASSWORD},
        headers=auth_headers(token),
    )
    assert allowed.status_code == 204, allowed.text


@pytest.mark.asyncio
async def test_project_cannot_be_hidden_with_an_active_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hiding the project (PATCH /companies/me, status hidden) is refused
    while one of its products is ACTIVE; hiding that product lifts it."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, token = await _company_with_login(client, admin_token)
    product_id = await _product(client, admin_token, company_id, "On sale")
    await _set_product_status(client, admin_token, product_id, "active")

    refused = await client.patch(
        "/api/v1/companies/me",
        json={"status": "hidden"},
        headers=auth_headers(token),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "company_has_active_products"
    still = await client.get("/api/v1/companies/me", headers=auth_headers(token))
    assert still.json()["status"] == "active"

    await _set_product_status(client, admin_token, product_id, "hidden")
    allowed = await client.patch(
        "/api/v1/companies/me",
        json={"status": "hidden"},
        headers=auth_headers(token),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "hidden"


@pytest.mark.asyncio
async def test_staff_cannot_hide_a_project_with_an_active_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The refusal binds staff too: PATCH /staff/companies/{id} with status
    hidden is 409 while a product is ACTIVE; hiding that product lifts it."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, _ = await _company_with_login(client, admin_token)
    product_id = await _product(client, admin_token, company_id, "On sale")
    await _set_product_status(client, admin_token, product_id, "active")

    refused = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "hidden"},
        headers=auth_headers(admin_token),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "company_has_active_products"

    await _set_product_status(client, admin_token, product_id, "hidden")
    allowed = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "hidden"},
        headers=auth_headers(admin_token),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "hidden"
