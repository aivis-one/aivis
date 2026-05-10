# =============================================================================
# CBSHOME Backend -- Dashboard + Portfolio Tests (Sprint 9.2,
#                                                  Refactor 2 iter 2.4)
# =============================================================================
#
# Tests cover:
#   1:  GET /dashboard/summary -- empty portfolio, balances zero
#   2:  GET /dashboard/summary -- one purchase, correct figures
#   3:  GET /dashboard/summary -- two companies, companies list
#   4:  GET /dashboard/summary -- unauthorized -> 401
#   5:  GET /portfolio/me -- empty -> empty positions
#   6:  GET /portfolio/me -- sale purchase -> correct avg_price
#   7:  GET /portfolio/me/company/{id} -- flat aggregate + paginated purchases
#   8:  GET /portfolio/me/company/{id} -- no purchases -> 404
#
# Refactor 2 iter 2.4: per-Purchase certificate tests (formerly 9-11)
# moved to tests/test_purchase_agreement.py with broader coverage
# (happy path, owner-scope 404, template_missing 500, email 204,
# XSS autoescape). Endpoint also renamed /certificate -> /agreement.
#
# Email prefix: "s92_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger, record_passive_ledger
from app.modules.purchases.models import Purchase
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s92_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_purchases.py)
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co1",
    *,
    price_per_unit_cents: int = 10000,
) -> dict:
    """Create a company via staff endpoint.

    Sprint 4.3: also creates active OptionPool for the company.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": price_per_unit_cents,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            # Sprint 4.3:
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    company = resp.json()

    # Sprint 4.3: products require an active pool.
    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, f"Create pool failed: {pool_resp.text}"

    return company


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    units: int = 100,
    name: str = "Test Package",
) -> dict:
    """Create a product via staff endpoint."""
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": name,
            "package_size": units,  # Sprint 4.3: column renamed
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create product failed: {resp.text}"
    return resp.json()


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    """Set company status to active."""
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _activate_product(
    client: AsyncClient, admin_token: str, product_id: str
) -> None:
    """Set product status to active."""
    resp = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "inv1",
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    """Create investor, deposit funds, return (token, user_id)."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    # Approve KYC (required for purchase).
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    # Deposit via direct ledger write.
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_s92",
    )
    await db_session.commit()

    return token, user_id


async def _buy_product(
    client: AsyncClient,
    inv_token: str,
    product_id: str,
) -> list[dict]:
    """Purchase a product, return list of purchase records."""
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"
    return resp.json()


async def _setup_company_product_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_token: str,
    *,
    company_suffix: str = "co1",
    investor_suffix: str = "inv1",
    units: int = 100,
    price_per_unit_cents: int = 10000,
) -> tuple[str, UUID, dict, dict, list[dict]]:
    """Full setup: company + product + investor + purchase.

    Returns (inv_token, inv_id, company, product, purchases).
    """
    company = await _create_company(
        client, admin_token, company_suffix,
        price_per_unit_cents=price_per_unit_cents,
    )
    product = await _create_product(
        client, admin_token, company["id"], units=units,
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session, suffix=investor_suffix,
    )

    purchases = await _buy_product(client, inv_token, product["id"])

    return inv_token, inv_id, company, product, purchases


# ===========================================================================
# Dashboard Tests (1-4)
# ===========================================================================


@pytest.mark.asyncio
async def test_dashboard_summary_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dashboard with no purchases -> all zeros, empty companies list."""
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_empty", balance_cents=50_000,
    )

    resp = await client.get(
        "/api/v1/dashboard/summary",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_invested_cents"] == 0
    assert body["total_units"] == 0
    assert body["current_value_cents"] == 0
    assert body["companies_count"] == 0
    assert body["companies"] == []

    # Balance should reflect the deposit.
    assert body["active_balance"]["confirmed"] == 50_000
    assert body["active_balance"]["frozen"] == 0
    assert body["passive_balance"]["confirmed"] == 0


@pytest.mark.asyncio
async def test_dashboard_summary_with_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dashboard with one purchase -> correct portfolio figures."""
    admin_token = await _admin_token(client, db_session)
    inv_token, inv_id, company, product, purchases = (
        await _setup_company_product_purchase(
            client, db_session, admin_token,
            units=50, price_per_unit_cents=10000,
        )
    )

    resp = await client.get(
        "/api/v1/dashboard/summary",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    # 50 units * 10000 cents = 500_000 invested.
    assert body["total_invested_cents"] == 500_000
    assert body["total_units"] == 50
    assert body["current_value_cents"] == 50 * 10000
    assert body["companies_count"] == 1
    assert len(body["companies"]) == 1

    co = body["companies"][0]
    assert co["company_id"] == company["id"]
    assert co["company_name"] == "Test Company co1"
    assert co["total_units"] == 50
    assert co["invested_cents"] == 500_000


@pytest.mark.asyncio
async def test_dashboard_summary_multiple_companies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dashboard with purchases in two companies -> companies list."""
    admin_token = await _admin_token(client, db_session)

    # Company 1: 10 units * 10000.
    company1 = await _create_company(
        client, admin_token, "mc1", price_per_unit_cents=10000,
    )
    product1 = await _create_product(
        client, admin_token, company1["id"], units=10,
    )
    await _activate_company(client, admin_token, company1["id"])
    await _activate_product(client, admin_token, product1["id"])

    # Company 2: 20 units * 5000.
    company2 = await _create_company(
        client, admin_token, "mc2", price_per_unit_cents=5000,
    )
    product2 = await _create_product(
        client, admin_token, company2["id"], units=20,
    )
    await _activate_company(client, admin_token, company2["id"])
    await _activate_product(client, admin_token, product2["id"])

    # Investor buys both.
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_mc", balance_cents=5_000_000,
    )
    await _buy_product(client, inv_token, product1["id"])
    await _buy_product(client, inv_token, product2["id"])

    resp = await client.get(
        "/api/v1/dashboard/summary",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["companies_count"] == 2
    assert len(body["companies"]) == 2
    # 10*10000 + 20*5000 = 100_000 + 100_000 = 200_000 invested.
    assert body["total_invested_cents"] == 200_000
    assert body["total_units"] == 30


@pytest.mark.asyncio
async def test_dashboard_summary_unauthorized(
    client: AsyncClient,
) -> None:
    """Dashboard without auth -> 401."""
    resp = await client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


# ===========================================================================
# Portfolio Tests (5-8)
# ===========================================================================


@pytest.mark.asyncio
async def test_portfolio_me_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Portfolio with no purchases -> empty positions."""
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_pe", balance_cents=10_000,
    )

    resp = await client.get(
        "/api/v1/portfolio/me",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["positions"] == []


@pytest.mark.asyncio
async def test_portfolio_me_with_avg_price(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Portfolio with sale purchase -> correct avg_price and split."""
    admin_token = await _admin_token(client, db_session)
    inv_token, inv_id, company, product, purchases = (
        await _setup_company_product_purchase(
            client, db_session, admin_token,
            units=100, price_per_unit_cents=10000,
            company_suffix="pf1", investor_suffix="inv_pf",
        )
    )

    resp = await client.get(
        "/api/v1/portfolio/me",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["positions"]) == 1
    pos = body["positions"][0]
    assert pos["company_id"] == company["id"]
    assert pos["total_units"] == 100
    assert pos["sale_units"] == 100
    assert pos["gift_units"] == 0
    assert pos["total_paid_cents"] == 100 * 10000
    # avg_price = SUM(paid_cents) / SUM(sale_units) = 1_000_000 / 100.
    assert pos["avg_price_cents"] == 10000
    assert pos["current_price_cents"] == 10000
    assert pos["current_value_cents"] == 100 * 10000
    assert pos["purchases_count"] >= 1


@pytest.mark.asyncio
async def test_portfolio_company_detail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Portfolio company detail -> flat aggregate + paginated purchases."""
    admin_token = await _admin_token(client, db_session)
    inv_token, inv_id, company, product, purchases = (
        await _setup_company_product_purchase(
            client, db_session, admin_token,
            units=50, price_per_unit_cents=20000,
            company_suffix="pd1", investor_suffix="inv_pd",
        )
    )

    resp = await client.get(
        f"/api/v1/portfolio/me/company/{company['id']}",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    # Flat position fields (no nested "position" object).
    assert body["company_id"] == company["id"]
    assert body["total_units"] == 50
    assert body["current_price_cents"] == 20000

    # Paginated purchases (field is "total", not "total_purchases").
    assert body["total"] >= 1
    assert len(body["purchases"]) >= 1
    assert body["page"] == 1

    # PurchaseItemResponse has no product_name.
    p = body["purchases"][0]
    assert p["units"] == 50
    assert "id" in p
    assert "legal_basis" in p


@pytest.mark.asyncio
async def test_portfolio_company_no_purchases(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Portfolio company detail with no purchases -> 404."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "np1")
    await _activate_company(client, admin_token, company["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_np",
    )

    resp = await client.get(
        f"/api/v1/portfolio/me/company/{company['id']}",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 404
