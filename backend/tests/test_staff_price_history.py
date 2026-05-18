# =============================================================================
# CBSHOME Backend -- Staff Company Price History Tests (iter 2.6c B3)
# =============================================================================
#
# HTTP-level smoke coverage for the new
#   GET /api/v1/staff/companies/{company_id}/price-history
# endpoint added in iter 2.6c B3.
#
# Tests cover:
#   1: happy path -- two PATCH /price calls leave two history rows,
#      newest first; envelope shape matches PriceHistoryListResponse
#   2: 404 on unknown company_id (raised by get_company inside service)
#   3: 403 for investor (no company_manage permission)
#
# Robustness contract (mirrors B1 / B2 notes):
#   * The dev DB is shared. We never assert "items list length is
#     exactly N" against an unfiltered call -- but here the filter
#     is by company_id, so every company we stage is bracket-fresh
#     and we CAN assert exact counts of OUR rows on OUR company.
#     CompanyPriceHistory is keyed by company_id (FK RESTRICT), so
#     no cross-test contamination is possible inside the filter.
#   * All emails / company names are UUID-suffixed.
#
# Email prefix:
#   Company users -- "ph26c_" via _create_company (UUID-suffixed).
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin staff user and return their session token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    *,
    price_per_unit_cents: int = 10_000,
) -> dict:
    """POST /staff/companies. Created in HIDDEN status by default.

    No pool, no activation -- the price-history endpoint does not
    depend on company status or pool existence. Initial price is
    captured at creation as the company's price_per_unit_cents but is
    NOT mirrored into CompanyPriceHistory (see CompanyPriceHistory
    model -- rows are only written by update_price()).
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"ph26c_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"PriceHistoryCo {uuid.uuid4().hex[:8]}",
            "description": "Staff price history test company",
            "price_per_unit_cents": price_per_unit_cents,
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
    return resp.json()


async def _patch_price(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    new_price: int,
) -> None:
    """PATCH /staff/companies/{id}/price.

    Each call appends one row to CompanyPriceHistory with
    changed_by=<admin user id> and server_default changed_at=now().
    The service rejects new_price == old_price with 400, so callers
    must use strictly different values.
    """
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}/price",
        json={"price_per_unit_cents": new_price},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 1: happy path -- two price changes -> two rows, newest first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_price_history_returns_changes_newest_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two PATCH /price calls -> GET returns two rows, newest first.

    Filter is by company_id, so the result set cannot be polluted by
    any other test's price changes. We DO assert exact item count
    (== 2) and price ordering ([new -> old]) on this filtered view.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)  # initial price 10000

    # Two distinct price changes.
    await _patch_price(client, admin_token, company["id"], 20_000)
    await _patch_price(client, admin_token, company["id"], 30_000)

    resp = await client.get(
        f"/api/v1/staff/companies/{company['id']}/price-history",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Envelope shape.
    assert body["page"] == 1
    assert body["per_page"] == 20
    assert body["total"] == 2
    assert len(body["items"]) == 2

    # Newest first: second PATCH (30_000) sits above the first (20_000).
    assert body["items"][0]["price_per_unit_cents"] == 30_000
    assert body["items"][1]["price_per_unit_cents"] == 20_000

    # Each row carries the four documented fields, with `changed_by`
    # pointing at SOMEBODY -- we don't pin the value because the test
    # admin user is created freshly each run and recovering its UUID
    # via /users/me would add a roundtrip that buys nothing material.
    for item in body["items"]:
        assert "id" in item
        assert "changed_at" in item
        assert "changed_by" in item


# ---------------------------------------------------------------------------
# 2: 404 on unknown company_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_price_history_404_for_unknown_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Non-existent company_id -> 404. The service's get_company call
    is the gatekeeper; an empty 200 would let a probe leak which UUIDs
    are valid via timing / response shape.
    """
    admin_token = await _admin_token(client, db_session)
    fake_id = uuid.uuid4()

    resp = await client.get(
        f"/api/v1/staff/companies/{fake_id}/price-history",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# 3: 403 for investor (no company_manage permission)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_price_history_forbidden_for_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor with no staff profile -> 403.

    require_staff_permission("company_manage") rejects the request
    before the company_id is even looked up, so we don't need an
    existing company for this assertion. Using a fresh random UUID
    in the path keeps the test independent of any other state.
    """
    inv_data = await register_user(client)
    inv_token = inv_data["session_token"]

    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/staff/companies/{fake_id}/price-history",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403, resp.text
