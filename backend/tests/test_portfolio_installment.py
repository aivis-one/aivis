# =============================================================================
# CBSHOME Backend -- Portfolio + Dashboard Installment Regression (Sprint 4.6)
# =============================================================================
#
# Background:
#   Reported in production: investor cd5db920... viewing Immo-Pro-Invest
#   GmbH portfolio saw total_units=1250, gift_units=1250, sale_units=0,
#   total_paid_cents=118750, avg_price=$0.00 -- self-contradictory
#   ($1187.50 invested but every unit "gifted"). Root cause:
#   portfolio/service.py classified anything with legal_basis != 'sale'
#   as a gift, which silently captured the 'installment_tranche' rows
#   that arrived in Sprint 6.2.
#
#   The same omission existed in company_dashboard/service.py:
#   `total_options_sold` and `sales_by_product[*].options_sold` only
#   summed legal_basis='sale', so a company that took payment via
#   installments saw revenue rise but options_sold stay at 0.
#
# These tests pin the corrected behaviour:
#   1. Investor pays the first tranche of an installment plan (UX-01
#      pays it inline at create_plan time) -- portfolio shows the
#      paid units in `sale_units`, not `gift_units`, and avg_price
#      matches the per-unit price.
#   2. Same scenario via /portfolio/me/company/{id} (separate code
#      path, same fix).
#   3. The company sees the same activity as `total_options_sold > 0`
#      and a non-zero entry in `sales_by_product`.
#
# Test approach:
#   Drives create_plan() at the service layer (same pattern as
#   tests/test_installments.py) so we can assert on the persisted
#   purchase row before involving HTTP. Then hits the public
#   /portfolio/me, /portfolio/me/company/{id}, /company/dashboard,
#   /company/analytics endpoints to confirm the response shapes.
#
# Email prefix: "s46_" -- unique to this test file, cleaned up in
# the autouse fixture.
# =============================================================================

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.installments.service import create_plan
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.constants import PurchaseLegalBasis
from app.modules.purchases.models import Purchase
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    login_user,
    register_user,
)

EMAIL_PREFIX = "s46_"

VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


# ---------------------------------------------------------------------------
# Helpers (mirror the patterns used by test_installments.py and
# test_company_dashboard.py so reviewers can grep for the same shapes)
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company_and_login(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co1",
) -> tuple[dict, str]:
    """Create a company via staff API + active pool, then login as
    the company user. Returns (company_dict, company_user_token)."""
    email = f"{EMAIL_PREFIX}{suffix}@example.com"
    password = "companypass123"

    create_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": 100,
            "distribution_config": VALID_DIST_CONFIG,
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

    activate_resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activate_resp.status_code == 200

    login_data = await login_user(client, email=email, password=password)
    return company, login_data["session_token"]


async def _create_product_active(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    package_size: int = 100,
    suffix: str = "p1",
) -> dict:
    """Create + activate a product. package_size=100 means each pack
    is 100 units. price_per_unit_cents=100 (cloned from the company)
    means a 100-unit pack costs 10000 cents = $100.00."""
    create_resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Test Package {suffix}",
            "description": "Test installment regression product",
            "package_size": package_size,
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
    assert activate_resp.status_code == 200
    return product


async def _create_installment_template(
    client: AsyncClient,
    admin_token: str,
    product_id: str,
) -> dict:
    """Create a 50/50 two-tranche template against a 100-unit / 10000-
    cents product. Each tranche unlocks 50 units for 5000 cents.

    Both bonuses are zeroed out so they cannot create gift Purchase
    rows that confuse the regression assertion (the test focuses on
    the tranche purchase only)."""
    resp = await client.post(
        f"/api/v1/staff/products/{product_id}/installments",
        json={
            "name": "Test Plan",
            "plan_config": {
                "tranches": [
                    {"amount_cents": 5000, "units_percent": 50},
                    {"amount_cents": 5000, "units_percent": 50},
                ],
                "bonus_units": 0,
                "agent_bonus_units": 0,
            },
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, (
        f"Create installment template failed: {resp.text}"
    )
    return resp.json()


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    suffix: str = "inv",
    balance_cents: int = 100_000,
) -> tuple[str, UUID]:
    """Register investor, force-approve KYC, deposit balance.

    Default balance is generous so the first tranche payment cannot
    fail on insufficient funds."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_s46",
    )
    await db_session.commit()

    return token, user_id


async def _pay_first_tranche_via_service(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    *,
    company_suffix: str,
    investor_suffix: str,
) -> tuple[dict, str, UUID, str]:
    """Build the full chain: company + pool + product + template +
    investor + plan. UX-01 pays the first tranche inline inside
    create_plan, so by the time this returns the investor has one
    Purchase row with legal_basis='installment_tranche' on file.

    Returns (company, company_token, investor_id, investor_token).
    """
    company, company_token = await _create_company_and_login(
        client, admin_token, suffix=company_suffix
    )
    product = await _create_product_active(
        client, admin_token, company["id"], suffix=f"{company_suffix}_p"
    )
    template = await _create_installment_template(
        client, admin_token, product["id"]
    )

    investor_token, investor_id = await _create_investor_with_balance(
        client, db_session, suffix=investor_suffix
    )

    # Drive create_plan at the service layer so we can hit the same
    # code path as production -- the HTTP route ultimately calls the
    # same function. UX-01 pays tranche #1 inline.
    investor_user = await db_session.get(User, investor_id)
    plan = await create_plan(
        product_id=UUID(product["id"]),
        product_installment_id=UUID(template["id"]),
        investor=investor_user,
        session=db_session,
    )
    await db_session.commit()
    assert plan is not None  # sanity

    # Verify a single installment_tranche purchase row exists -- this
    # is the precise data shape that broke the production portfolio
    # rendering. If the chain ever generates extra rows (e.g. a stray
    # gift), later assertions need to be adjusted.
    purchases_stmt = (
        select(Purchase)
        .where(
            Purchase.investor_id == investor_id,
            Purchase.company_id == UUID(company["id"]),
        )
    )
    purchases = list(
        (await db_session.execute(purchases_stmt)).scalars().all()
    )
    assert len(purchases) == 1, (
        f"Expected exactly one tranche purchase, got {len(purchases)}: "
        f"{[(p.legal_basis, p.units, p.paid_cents) for p in purchases]}"
    )
    assert (
        purchases[0].legal_basis == PurchaseLegalBasis.INSTALLMENT_TRANCHE
    ), f"Wrong legal_basis: {purchases[0].legal_basis}"
    # 50 units unlocked, 5000 cents paid -- matches the 50/50 template
    # and the product price (100 cents/unit).
    assert purchases[0].units == 50
    assert purchases[0].paid_cents == 5000
    assert purchases[0].price_per_unit_cents == 100

    return company, company_token, investor_id, investor_token


# ---------------------------------------------------------------------------
# Test 1: /portfolio/me classifies installment_tranche as sale_units
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_me_installment_tranche_counts_as_sale(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor paid one tranche -> portfolio shows the units as
    sale_units (not gift_units), with a meaningful avg_price.

    Pre-fix this was: sale_units=0, gift_units=50, avg_price=0,
    total_paid_cents=5000 -- the production bug.
    """
    admin_token = await _admin_token(client, db_session)
    company, _company_token, _inv_id, inv_token = (
        await _pay_first_tranche_via_service(
            client, admin_token, db_session,
            company_suffix="t1", investor_suffix="inv_t1",
        )
    )

    resp = await client.get(
        "/api/v1/portfolio/me",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, f"/portfolio/me failed: {resp.text}"
    body = resp.json()

    assert len(body["positions"]) == 1
    pos = body["positions"][0]
    assert pos["company_id"] == company["id"]
    assert pos["total_units"] == 50
    # Sprint 4.6 hotfix: installment_tranche -> sale_units, not
    # gift_units. avg_price = 5000 / 50 = 100 cents/unit.
    assert pos["sale_units"] == 50
    assert pos["gift_units"] == 0
    assert pos["total_paid_cents"] == 5000
    assert pos["avg_price_cents"] == 100


# ---------------------------------------------------------------------------
# Test 2: /portfolio/me/company/{id} — same fix on the detail path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_company_detail_installment_tranche_counts_as_sale(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Same regression on the per-company detail endpoint, which
    has its own aggregation query in get_company_position()."""
    admin_token = await _admin_token(client, db_session)
    company, _company_token, _inv_id, inv_token = (
        await _pay_first_tranche_via_service(
            client, admin_token, db_session,
            company_suffix="t2", investor_suffix="inv_t2",
        )
    )

    resp = await client.get(
        f"/api/v1/portfolio/me/company/{company['id']}",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, (
        f"/portfolio/me/company/{{id}} failed: {resp.text}"
    )
    body = resp.json()

    assert body["total_units"] == 50
    assert body["sale_units"] == 50
    assert body["gift_units"] == 0
    assert body["total_paid_cents"] == 5000
    assert body["avg_price_cents"] == 100
    # The single tranche purchase is in the paginated list too.
    assert body["total"] == 1
    assert len(body["purchases"]) == 1
    assert body["purchases"][0]["legal_basis"] == "installment_tranche"


# ---------------------------------------------------------------------------
# Test 3: /company/dashboard counts installment_tranche in
#         total_options_sold + sales_by_product[*].options_sold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_dashboard_counts_installment_in_options_sold(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Company side of the same fix: paid tranches must show up in
    total_options_sold and per-product analytics. Pre-fix the company
    saw revenue=5000 but options_sold=0 -- visually inconsistent."""
    admin_token = await _admin_token(client, db_session)
    _company, company_token, _inv_id, _inv_token = (
        await _pay_first_tranche_via_service(
            client, admin_token, db_session,
            company_suffix="t3", investor_suffix="inv_t3",
        )
    )

    # /company/dashboard -- top-level total_options_sold
    dash_resp = await client.get(
        "/api/v1/company/dashboard",
        headers=auth_headers(company_token),
    )
    assert dash_resp.status_code == 200, (
        f"/company/dashboard failed: {dash_resp.text}"
    )
    dash = dash_resp.json()
    assert dash["total_revenue_cents"] == 5000
    assert dash["total_options_sold"] == 50  # was 0 pre-fix

    # /company/analytics -- same number plus per-product breakdown
    ana_resp = await client.get(
        "/api/v1/company/analytics",
        headers=auth_headers(company_token),
    )
    assert ana_resp.status_code == 200, (
        f"/company/analytics failed: {ana_resp.text}"
    )
    ana = ana_resp.json()
    assert ana["total_revenue_cents"] == 5000
    assert ana["total_options_sold"] == 50
    # The tranche sale was in the current month (just happened).
    assert ana["revenue_this_month_cents"] == 5000

    # The single product gets the credit: 5000 cents revenue, 50 options.
    assert len(ana["sales_by_product"]) == 1
    product_row = ana["sales_by_product"][0]
    assert product_row["revenue_cents"] == 5000
    assert product_row["options_sold"] == 50  # was 0 pre-fix
