# =============================================================================
# CBSHOME Backend -- Company Dashboard Tests (Sprint 4.3 / B5)
# =============================================================================
#
# Tests cover:
#   1: GET /company/dashboard -- newly created company, no pool -> zeros
#   2: GET /company/dashboard -- pool + 1 purchase -> revenue / sold / pool
#   3: GET /company/dashboard -- 25 transactions inserted -> 20 newest, DESC
#   4: GET /company/dashboard -- investor caller -> 403
#   5: GET /company/analytics -- newly created company -> zeros + empty arrays
#   6: GET /company/analytics -- one sale this month -> totals + 1 bucket + 1 row
#   7: GET /company/analytics -- 2 products, 1 sold -> both rows, zero-row last
#   8: GET /company/analytics -- investor caller -> 403
#
# Email prefix: "s43d_" -- unique to this file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import CompanyProfile
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.transactions.models import Transaction
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    login_user,
    register_user,
)

EMAIL_PREFIX = "s43d_"

VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users (and their company/pool/product/transaction chain)
    before and after each test. Transactions are wiped via the user_id FK
    chain inside cleanup_test_users (extended by Sprint 6.4)."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create an admin (all permissions) and return the session token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "co1",
    *,
    total_supply: int = 1_000_000,
    with_pool: bool = True,
    equity_percent: str = "100.0",
) -> tuple[dict, str]:
    """Create a company via staff API + (optionally) its pool, then login
    as the freshly created company user.

    Returns (company_dict, company_user_session_token).
    """
    admin_token = await _admin_token(client, db_session)

    email = f"{EMAIL_PREFIX}{suffix}@example.com"
    password = "companypass123"

    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": total_supply,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    company = resp.json()

    if with_pool:
        pool_resp = await client.post(
            f"/api/v1/staff/companies/{company['id']}/pool",
            json={"equity_percent": equity_percent},
            headers=auth_headers(admin_token),
        )
        assert pool_resp.status_code == 201, (
            f"Create pool failed: {pool_resp.text}"
        )

    # Login as the company user (same email/password the staff endpoint
    # used to create the underlying User row).
    login_data = await login_user(client, email=email, password=password)
    return company, login_data["session_token"]


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    """Set company status to active."""
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, f"Activate company failed: {resp.text}"


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    package_size: int = 10,
    suffix: str = "pkg",
) -> dict:
    """Create a product and return response."""
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Test Package {suffix}",
            "description": f"Test package {suffix}",
            "package_size": package_size,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create product failed: {resp.text}"
    return resp.json()


async def _activate_product(
    client: AsyncClient, admin_token: str, product_id: str
) -> None:
    """Set product status to active."""
    resp = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, f"Activate product failed: {resp.text}"


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "inv1",
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    """Register investor, approve KYC, deposit funds. Returns (token, id)."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_s43d",
    )
    await db_session.commit()

    return token, user_id


async def _company_user_id(
    db_session: AsyncSession, company_id: str
) -> UUID:
    """Look up the User.id linked to a CompanyProfile."""
    stmt = select(CompanyProfile.user_id).where(
        CompanyProfile.id == UUID(company_id)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# 1: Dashboard -- newly created company, no pool, no purchases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_basic_no_pool(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Newly created company without a pool: zeros, pool=None, empty feed."""
    _, company_token = await _create_company_and_login(
        client, db_session, suffix="t1", with_pool=False
    )

    resp = await client.get(
        "/api/v1/company/dashboard",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"Dashboard failed: {resp.text}"
    body = resp.json()

    assert body["passive_balance"] == {"frozen": 0, "confirmed": 0}
    assert body["total_revenue_cents"] == 0
    assert body["total_options_sold"] == 0
    assert body["products_count"] == 0
    assert body["pool"] is None
    assert body["recent_transactions"] == []


# ---------------------------------------------------------------------------
# 2: Dashboard -- pool + 1 purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_with_pool_and_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pool + 1 purchase: revenue, options_sold, pool stats reflect it."""
    admin_token = await _admin_token(client, db_session)
    company, company_token = await _create_company_and_login(
        client, db_session, suffix="t2",
        total_supply=1_000, with_pool=True, equity_percent="100.0",
    )
    await _activate_company(client, admin_token, company["id"])

    product = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t2_p"
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t2"
    )
    purchase_resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )

    resp = await client.get(
        "/api/v1/company/dashboard",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"Dashboard failed: {resp.text}"
    body = resp.json()

    # 10 units * 10000 cents/unit = 100_000.
    assert body["total_revenue_cents"] == 100_000
    assert body["total_options_sold"] == 10
    assert body["products_count"] == 1

    pool = body["pool"]
    assert pool is not None
    assert pool["total_options"] == 1_000
    assert pool["consumed"] == 10
    assert pool["remaining"] == 990
    assert pool["status"] == "active"


# ---------------------------------------------------------------------------
# 3: Dashboard -- recent_transactions limit + ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_recent_transactions_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Insert 25 transactions for the company user; response returns 20
    newest, ordered DESC by created_at."""
    company, company_token = await _create_company_and_login(
        client, db_session, suffix="t3", with_pool=False
    )
    company_user_id = await _company_user_id(db_session, company["id"])

    # Distinct created_at values so ORDER BY DESC is deterministic.
    base_time = datetime.now(UTC) - timedelta(days=1)
    for i in range(25):
        txn = Transaction(
            user_id=company_user_id,
            type="test:event",
            amount_cents=i * 100,
            currency="USD",
            details={"index": i},
            created_at=base_time + timedelta(seconds=i),
        )
        db_session.add(txn)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/company/dashboard",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"Dashboard failed: {resp.text}"
    body = resp.json()

    recent = body["recent_transactions"]
    assert len(recent) == 20

    # Newest first. We inserted with index 0..24 (oldest..newest), so
    # the response should hold indices 24, 23, ..., 5.
    indices = [t["details"]["index"] for t in recent]
    assert indices == list(range(24, 4, -1))

    # Sanity: schema fields rendered correctly.
    first = recent[0]
    assert first["type"] == "test:event"
    assert first["currency"] == "USD"
    assert first["amount_cents"] == 24 * 100


# ---------------------------------------------------------------------------
# 4: Dashboard -- investor caller -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_forbidden_for_non_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor (no CompanyProfile) calling /company/dashboard -> 403."""
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t4"
    )

    resp = await client.get(
        "/api/v1/company/dashboard",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403
    assert "not linked to a company" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 5: Analytics -- newly created company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_basic(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Newly created company: all zeros, both arrays empty."""
    _, company_token = await _create_company_and_login(
        client, db_session, suffix="t5", with_pool=False
    )

    resp = await client.get(
        "/api/v1/company/analytics",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"Analytics failed: {resp.text}"
    body = resp.json()

    assert body["total_revenue_cents"] == 0
    assert body["revenue_this_month_cents"] == 0
    assert body["total_options_sold"] == 0
    assert body["sales_by_month"] == []
    assert body["sales_by_product"] == []


# ---------------------------------------------------------------------------
# 6: Analytics -- one sale in current month
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_with_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """One sale in the current month: totals + 1 month bucket + 1 product row."""
    admin_token = await _admin_token(client, db_session)
    company, company_token = await _create_company_and_login(
        client, db_session, suffix="t6",
        total_supply=1_000, with_pool=True, equity_percent="100.0",
    )
    await _activate_company(client, admin_token, company["id"])

    product = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t6_p"
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t6"
    )
    purchase_resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )

    resp = await client.get(
        "/api/v1/company/analytics",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"Analytics failed: {resp.text}"
    body = resp.json()

    assert body["total_revenue_cents"] == 100_000
    # Purchase happened just now -> in the current UTC month.
    assert body["revenue_this_month_cents"] == 100_000
    assert body["total_options_sold"] == 10

    # Single month bucket -- the current UTC month.
    expected_month = datetime.now(UTC).strftime("%Y-%m")
    assert len(body["sales_by_month"]) == 1
    bucket = body["sales_by_month"][0]
    assert bucket["month"] == expected_month
    assert bucket["revenue_cents"] == 100_000
    assert bucket["options_sold"] == 10

    # Single product row.
    assert len(body["sales_by_product"]) == 1
    row = body["sales_by_product"][0]
    assert row["product_id"] == product["id"]
    assert row["product_name"] == "Test Package t6_p"
    assert row["revenue_cents"] == 100_000
    assert row["options_sold"] == 10


# ---------------------------------------------------------------------------
# 7: Analytics -- zero-sales product still appears
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_sales_by_product_includes_zero_sales(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two products of one company, only one sold; both appear in
    sales_by_product, zero-sales row last (revenue DESC)."""
    admin_token = await _admin_token(client, db_session)
    company, company_token = await _create_company_and_login(
        client, db_session, suffix="t7",
        total_supply=1_000, with_pool=True, equity_percent="100.0",
    )
    await _activate_company(client, admin_token, company["id"])

    p_sold = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t7_sold"
    )
    p_unsold = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t7_unsold"
    )
    await _activate_product(client, admin_token, p_sold["id"])
    await _activate_product(client, admin_token, p_unsold["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t7"
    )
    purchase_resp = await client.post(
        f"/api/v1/products/{p_sold['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )

    resp = await client.get(
        "/api/v1/company/analytics",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"Analytics failed: {resp.text}"
    body = resp.json()

    rows = body["sales_by_product"]
    assert len(rows) == 2

    # Sold product first (revenue DESC).
    assert rows[0]["product_id"] == p_sold["id"]
    assert rows[0]["revenue_cents"] == 100_000
    assert rows[0]["options_sold"] == 10

    # Unsold product is still listed, with zeros.
    assert rows[1]["product_id"] == p_unsold["id"]
    assert rows[1]["revenue_cents"] == 0
    assert rows[1]["options_sold"] == 0


# ---------------------------------------------------------------------------
# 8: Analytics -- investor caller -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analytics_forbidden_for_non_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor (no CompanyProfile) calling /company/analytics -> 403."""
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t8"
    )

    resp = await client.get(
        "/api/v1/company/analytics",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403
    assert "not linked to a company" in resp.json()["message"]
