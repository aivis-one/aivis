# =============================================================================
# CBSHOME Backend -- Pack Pricing Tests (Sprint 4.4 / B7)
# =============================================================================
#
# Tests cover:
#   1: Public list endpoint populates price_per_pack_cents
#      (product.package_size * product.price_per_unit_cents)
#   2: Public detail endpoint populates price_per_pack_cents
#
# Both tests round-trip the multiplication through a real HTTP call so
# any future refactor of the pre-population path (currently in
# products/router.py via explicit Pydantic constructors) cannot
# silently drop the field.
#
# Test scope is intentionally narrow: the schema requires the field
# and we only check it survives the wire. available_packages,
# company denormalisation, and installment shaping have their own
# tests in test_products.py (tests 11-15).
#
# Email prefix: "s44pp_" -- unique to this test file, cleaned up in fixture.
# Filename suffix `_pack_pricing` keeps the broader test_products.py
# untouched and lets `pytest tests/test_products_pack_pricing.py` run
# the B7 surface in isolation.
# =============================================================================

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import (
    auth_headers,
    create_admin_user,
)

EMAIL_PREFIX = "s44pp_"

# Default values come from the helpers below. Surface them as named
# constants so the assertions read like a contract: "100 options/pack
# at 10000 cents/option = 1,000,000 cents/pack".
_DEFAULT_PACKAGE_SIZE = 100
_DEFAULT_PRICE_PER_UNIT_CENTS = 10_000
_EXPECTED_PRICE_PER_PACK_CENTS = (
    _DEFAULT_PACKAGE_SIZE * _DEFAULT_PRICE_PER_UNIT_CENTS
)  # = 1_000_000

# Reusable valid distribution config (same shape used across the
# storefront tests; product creation requires an active company that
# was created with a valid distribution).
_VALID_DIST_CONFIG = {
    "company_pct": 0.65,
    "agent_levels": [0.10, 0.03, 0.01],
}


# ---------------------------------------------------------------------------
# Helpers (mirror test_products.py to keep this file self-contained)
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company_with_pool(
    client: AsyncClient,
    admin_token: str,
    suffix: str,
) -> dict:
    """Create a company plus its 100% active pool.

    Sprint 4.3: products require an active OptionPool on their company
    before they can be created. Mirrors the helper in test_products.py.
    """
    create_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "price_per_unit_cents": _DEFAULT_PRICE_PER_UNIT_CENTS,
            "distribution_config": _VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert create_resp.status_code == 201, (
        f"Create company failed: {create_resp.text}"
    )
    company = create_resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, (
        f"Create pool failed: {pool_resp.text}"
    )

    return company


async def _create_active_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    suffix: str,
) -> dict:
    """Create a hidden product, then activate it.

    Public endpoints filter by status=active, so the product must be
    activated to surface in the responses under test.
    """
    create_resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Package {suffix}",
            "package_size": _DEFAULT_PACKAGE_SIZE,
        },
        headers=auth_headers(admin_token),
    )
    assert create_resp.status_code == 201, (
        f"Create product failed: {create_resp.text}"
    )
    product = create_resp.json()

    activate_resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activate_resp.status_code == 200, (
        f"Activate product failed: {activate_resp.text}"
    )

    return product


# ---------------------------------------------------------------------------
# Test 1: Public list populates price_per_pack_cents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_populates_price_per_pack_cents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /products returns price_per_pack_cents for each item."""
    token = await _admin_token(client, db_session)
    company = await _create_company_with_pool(client, token, suffix="lst")
    product = await _create_active_product(
        client, token, company["id"], suffix="lst"
    )

    resp = await client.get(
        "/api/v1/public/products",
        params={"company_id": company["id"]},
    )
    assert resp.status_code == 200, f"List failed: {resp.text}"
    body = resp.json()

    assert body["total"] == 1
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["id"] == product["id"]

    # Contract: price_per_pack_cents == package_size * price_per_unit_cents.
    # Defaults give 100 * 10_000 = 1_000_000 cents.
    assert item["package_size"] == _DEFAULT_PACKAGE_SIZE
    assert item["price_per_unit_cents"] == _DEFAULT_PRICE_PER_UNIT_CENTS
    assert item["price_per_pack_cents"] == _EXPECTED_PRICE_PER_PACK_CENTS
    assert (
        item["price_per_pack_cents"]
        == item["package_size"] * item["price_per_unit_cents"]
    )


# ---------------------------------------------------------------------------
# Test 2: Public detail populates price_per_pack_cents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_populates_price_per_pack_cents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /products/{id} returns price_per_pack_cents."""
    token = await _admin_token(client, db_session)
    company = await _create_company_with_pool(client, token, suffix="det")
    product = await _create_active_product(
        client, token, company["id"], suffix="det"
    )

    resp = await client.get(f"/api/v1/public/products/{product['id']}")
    assert resp.status_code == 200, f"Detail failed: {resp.text}"
    body = resp.json()

    assert body["id"] == product["id"]

    # Same contract as the list endpoint -- both code paths feed
    # through PublicProductResponse.price_per_pack_cents.
    assert body["package_size"] == _DEFAULT_PACKAGE_SIZE
    assert body["price_per_unit_cents"] == _DEFAULT_PRICE_PER_UNIT_CENTS
    assert body["price_per_pack_cents"] == _EXPECTED_PRICE_PER_PACK_CENTS
    assert (
        body["price_per_pack_cents"]
        == body["package_size"] * body["price_per_unit_cents"]
    )

    # Sprint 4.4: installments is required (no default []) -- the
    # field is always present, even on a product without plans. This
    # is the wire-level proof the schema change holds; the frontend
    # drops `?? []` based on this guarantee.
    assert "installments" in body
    assert body["installments"] == []
