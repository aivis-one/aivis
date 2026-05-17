# =============================================================================
# CBSHOME Backend -- Public Products HTTP Tests (iter 2.5-finishing)
# =============================================================================
#
# HTTP-level coverage for app/modules/products/public_router.py.
# Companion to test_public_companies.py; together they cover the
# /api/v1/public/* storefront surface before iter 2.6 rewires the
# frontend AttachmentsSection / PublicShell.
#
# What's tested:
#   1.  list returns 200 and items
#   2.  ?company_id=X filters to that company's products only
#       (other companies' products do not leak in)
#   3.  detail 200 with the public product fields populated
#   4.  detail STRIPS agent_bonus_units from every installment's
#       plan_config (R1 §1.6.3 -- _strip_agent_bonus_units)
#   5.  detail 404 for nonexistent product
#   6.  detail 404 for a hidden product
#
# Rate-limit is intentionally NOT re-tested here -- the shared bucket
# is exercised by test_public_companies.py and re-exercising the same
# Redis path twice burns time without adding signal.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
)

# ---------------------------------------------------------------------------
# Local helpers (parallel to test_public_companies.py).
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
) -> dict:
    """Create + activate a company with a 100% equity pool.

    Activates immediately because the public products router does not
    care about company status -- it cares about ProductStatus -- and
    every test in this file wants a usable, visible product.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"PubProdCo {uuid.uuid4().hex[:6]}",
            "description": "Public products router test company",
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
    company = resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, pool_resp.text

    act = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert act.status_code == 200, act.text

    return company


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    package_size: int = 100,
    activate: bool = True,
    name: str | None = None,
) -> dict:
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": name or f"PubProd {uuid.uuid4().hex[:6]}",
            "package_size": package_size,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    product = resp.json()

    if activate:
        act = await client.patch(
            f"/api/v1/staff/products/{product['id']}/status",
            json={"status": "active"},
            headers=auth_headers(admin_token),
        )
        assert act.status_code == 200, act.text

    return product


async def _create_installment_with_agent_bonus(
    client: AsyncClient,
    admin_token: str,
    product_id: str,
    *,
    agent_bonus_units: int = 5,
) -> dict:
    """Create a 2-tranche installment template with explicit agent_bonus_units.

    Product is package_size=100 @ 10000 cents per unit -> total 1_000_000.
    Two 50/50 tranches keep validate_plan_config happy.
    """
    resp = await client.post(
        f"/api/v1/staff/products/{product_id}/installments",
        json={
            "name": "Pub Plan",
            "plan_config": {
                "tranches": [
                    {"amount_cents": 500_000, "units_percent": 50},
                    {"amount_cents": 500_000, "units_percent": 50},
                ],
                "bonus_units": 0,
                "agent_bonus_units": agent_bonus_units,
            },
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _unique_ip() -> str:
    """X-Real-IP from the documentation range so the shared
    `public_companies:` rate-limit bucket can't bleed across tests.
    """
    return f"192.0.2.{uuid.uuid4().int % 200 + 50}"


# ---------------------------------------------------------------------------
# 1: list 200 + items present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_products_list_returns_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """List endpoint returns 200 and includes our active product."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])

    resp = await client.get(
        "/api/v1/public/products?per_page=100",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    found_ids = {item["id"] for item in body["items"]}
    assert product["id"] in found_ids


# ---------------------------------------------------------------------------
# 2: ?company_id filter does not leak other companies' products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_products_list_filters_by_company_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?company_id=A returns only products owned by A.

    Build two companies with one active product each. Filter by A's
    id -- B's product must not appear.
    """
    admin_token = await _admin_token(client, db_session)

    co_a = await _create_company(client, admin_token)
    co_b = await _create_company(client, admin_token)

    prod_a = await _create_product(client, admin_token, co_a["id"])
    prod_b = await _create_product(client, admin_token, co_b["id"])

    resp = await client.get(
        f"/api/v1/public/products?company_id={co_a['id']}&per_page=100",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    returned_ids = {item["id"] for item in body["items"]}
    returned_company_ids = {item["company_id"] for item in body["items"]}

    assert prod_a["id"] in returned_ids
    assert prod_b["id"] not in returned_ids
    # Every returned item belongs to company A.
    assert returned_company_ids == {co_a["id"]}


# ---------------------------------------------------------------------------
# 3: detail 200 with public fields populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_product_detail_returns_public_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/v1/public/products/{id} returns 200 with the public
    detail shape (company_name denormalised, available_packages,
    installments list).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])

    resp = await client.get(
        f"/api/v1/public/products/{product['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["id"] == product["id"]
    assert body["company_id"] == company["id"]
    assert "package_size" in body
    assert body.get("company_name")
    assert "available_packages" in body
    assert "installments" in body and isinstance(body["installments"], list)


# ---------------------------------------------------------------------------
# 4: detail strips agent_bonus_units (R1 §1.6.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_product_detail_strips_agent_bonus_units(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Per-tranche agent commission units must NOT leak via the public
    detail endpoint. _strip_agent_bonus_units removes the key from
    every installment's plan_config before serialisation.

    Setup: one product, one installment template carrying
    agent_bonus_units=5. Public response must show the installment
    but omit `agent_bonus_units` entirely.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])

    template = await _create_installment_with_agent_bonus(
        client, admin_token, product["id"], agent_bonus_units=5
    )
    # Sanity check: staff-side response should still carry the key.
    # (The strip only happens in the public router.)
    assert template["plan_config"].get("agent_bonus_units") == 5

    resp = await client.get(
        f"/api/v1/public/products/{product['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["installments"]) == 1
    public_plan_config = body["installments"][0]["plan_config"]

    assert "agent_bonus_units" not in public_plan_config, (
        "agent_bonus_units leaked via public product detail "
        f"(plan_config keys: {sorted(public_plan_config.keys())})"
    )
    # tranches + bonus_units must still be there -- only agent_bonus_units strips.
    assert "tranches" in public_plan_config
    assert "bonus_units" in public_plan_config


# ---------------------------------------------------------------------------
# 5: detail 404 for nonexistent product
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_product_detail_404_for_nonexistent(
    client: AsyncClient,
) -> None:
    """Random UUID -> 404."""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/public/products/{fake_id}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6: detail 404 for hidden product
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_product_detail_404_for_hidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Non-active product -> 404.

    Build a product but skip activation -- it stays in HIDDEN, which
    the router rejects (`if product.status != ProductStatus.ACTIVE:
    raise NotFoundError`).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(
        client, admin_token, company["id"], activate=False
    )

    resp = await client.get(
        f"/api/v1/public/products/{product['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7: list filters out hidden products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_products_list_excludes_hidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """list_products(active_only=True) drops non-ACTIVE rows.

    Build two products under the same company: one activated, one
    hidden. ?company_id=X must return ONLY the active one.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)

    visible = await _create_product(
        client, admin_token, company["id"], name="Visible", activate=True
    )
    invisible = await _create_product(
        client, admin_token, company["id"], name="Invisible", activate=False
    )

    resp = await client.get(
        f"/api/v1/public/products?company_id={company['id']}&per_page=100",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned_ids = {item["id"] for item in body["items"]}

    assert visible["id"] in returned_ids
    assert invisible["id"] not in returned_ids


# ---------------------------------------------------------------------------
# 8: pagination -- per_page caps the page size, total counts all matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_products_pagination_per_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Three active products under one company, per_page=2 -> page 1
    returns 2 items, total reports 3. Plain pagination smoke against
    the storefront grid surface.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)

    for i in range(3):
        await _create_product(
            client, admin_token, company["id"], name=f"PgProd {i}"
        )

    resp = await client.get(
        f"/api/v1/public/products?company_id={company['id']}&per_page=2&page=1",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["per_page"] == 2
    assert body["page"] == 1
    assert body["total"] == 3
    assert len(body["items"]) == 2
