# =============================================================================
# CBSHOME Backend -- Pool Tests (Sprint 4.3, TD-071, Share Pool Refactor)
# =============================================================================
#
# Tests cover (spec §8.6):
#   1:  POST /staff/companies/{id}/pool -> 201 with computed total_options
#   2:  Second POST -> 400 (one active pool per company)
#   3:  PATCH total_options -> equity_percent recomputed
#   4:  PATCH total_options below already-consumed -> 400
#   5:  POST /staff/products on company without an active pool -> 400
#   6:  Purchase against one product -> available_packages drops for ALL
#       products of the same company (shared pool)
#   7:  Pool exhausted -> next purchase 400 "Sold out"
#   8:  Gift purchase consumes the pool (consumed = sale_units + gift_units)
#   9:  Gift overflows into owner supply when pool just fits the package
#       (pool_remaining goes negative; purchase still succeeds, spec §3.7)
#   10: Installment calculator preview returns valid plan_config (B4)
#   11: Calculator output passes all validate_plan_config invariants and
#       can be POSTed back to /installments without modification (B4)
#
# Email prefix: "s43p_" -- unique to this test file, cleaned up in fixture.
# helpers.cleanup_test_users() already removes OptionPool rows in the
# correct order (products -> option_pools -> company_profiles, see
# Sprint 4.3 note in helpers.py). ProductInstallment cleanup was added
# in Sprint 6.2 and runs before Product deletion.
# =============================================================================

from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.pools.service import get_active_pool, get_pool_consumed
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s43p_"

# Reusable valid distribution config (mirrors test_companies.py /
# test_purchases.py).
VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users (and their pool/company/product chain) before
    and after each test."""
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


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co1",
    *,
    total_supply: int = 1_000_000,
    with_pool: bool = True,
    equity_percent: str = "100.0",
) -> dict:
    """Create a company and (optionally) its active pool.

    Most pool tests need a pool right after company creation so that
    subsequent product creation can attach to it. Tests that
    specifically check pool absence pass with_pool=False and either
    POST the pool themselves or skip pool creation entirely.

    Sprint 4.3: total_supply and shares_per_option are required by the
    company schema; the helper exposes total_supply since multiple
    tests need to size the pool exactly (sold-out, overflow). The
    pool's equity_percent is also exposed so tests can pick a slice
    smaller than 100%.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
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

    return company


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
    package_size: int = 100,
    purchase_config: dict | None = None,  # type: ignore[type-arg]
    suffix: str = "pkg",
) -> dict:
    """Create a product with the given package_size.

    purchase_config is optional; when supplied it goes through the
    standard validate_purchase_config path on the staff endpoint.
    """
    body: dict = {  # type: ignore[type-arg]
        "company_id": company_id,
        "name": f"Test Package {suffix}",
        "description": f"Test package {suffix}",
        "package_size": package_size,
    }
    if purchase_config is not None:
        body["purchase_config"] = purchase_config

    resp = await client.post(
        "/api/v1/staff/products",
        json=body,
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
    """Register an investor, approve KYC, deposit funds. Returns (token, id).

    Mirrors the same helper in test_purchases.py -- KYC approval is
    required for any purchase since TD-038, and a confirmed deposit is
    needed so the engine's balance check passes.
    """
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    # Approve KYC (TD-038: required for purchase).
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    # Deposit via direct ledger write (simulating confirmed deposit).
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_s43p",
    )
    await db_session.commit()

    return token, user_id


# ---------------------------------------------------------------------------
# 1: Create pool -- 201, equity_percent + total_options correct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pool(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/companies/{id}/pool -> 201 with computed total_options."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, suffix="t1", with_pool=False
    )

    resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "50.0"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create pool failed: {resp.text}"
    body = resp.json()

    assert body["company_id"] == company["id"]
    # Stored as Numeric(7, 4) -- compare as Decimal so trailing zeros
    # don't matter ("50.0" vs "50.0000").
    assert Decimal(body["equity_percent"]) == Decimal("50.0000")
    # total_supply=1_000_000, equity=50% -> floor(1_000_000 * 0.5) = 500_000.
    assert body["total_options"] == 500_000
    assert body["status"] == "active"
    assert body["consumed"] == 0
    assert body["remaining"] == 500_000


# ---------------------------------------------------------------------------
# 2: One active pool per company -- second POST -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_active_pool_per_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second POST on the same company -> 400 (pre-check or DB constraint)."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, suffix="t2", with_pool=False
    )

    resp1 = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "50.0"},
        headers=auth_headers(admin_token),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "30.0"},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 400
    assert "already has an active pool" in resp2.json()["message"]


# ---------------------------------------------------------------------------
# 3: Update pool total_options -- equity_percent recomputed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_pool_total_options(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH total_options -> 200, equity_percent recomputed from new total."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        admin_token,
        suffix="t3",
        with_pool=True,
        equity_percent="100.0",
    )
    # total_supply=1_000_000 -> pool.total_options=1_000_000.

    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"total_options": 200_000},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, f"Update failed: {resp.text}"
    body = resp.json()

    assert body["total_options"] == 200_000
    # 200_000 * 100 / 1_000_000 = 20.0000 (quantized to Numeric(7, 4)).
    assert Decimal(body["equity_percent"]) == Decimal("20.0000")
    assert body["consumed"] == 0
    assert body["remaining"] == 200_000


# ---------------------------------------------------------------------------
# 4: Update pool below consumed -- 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_pool_below_consumed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH total_options below already-consumed options -> 400."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        admin_token,
        suffix="t4",
        total_supply=1_000,
        with_pool=True,
        equity_percent="100.0",
    )
    # pool.total_options=1_000.
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t4"
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t4"
    )
    purchase_resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )
    # consumed = 10 (one package).

    # Try to shrink pool below consumed.
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"total_options": 5},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400
    msg = resp.json()["message"]
    assert "Cannot reduce" in msg
    assert "already consumed" in msg


# ---------------------------------------------------------------------------
# 5: Product creation requires an active pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_product_requires_active_pool(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/products on a company without a pool -> 400."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, suffix="t5", with_pool=False
    )

    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Test Package t5",
            "package_size": 10,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400
    # get_active_pool() raises BadRequestError("...has no active pool...").
    assert "no active pool" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 6: available_packages decreases for ALL products of the company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_available_packages_decreases(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Buy one product -> available_packages drops for ALL products of the
    same company. The pool is shared across products of one company, so
    a purchase against product1 reduces availability for product2 too.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        admin_token,
        suffix="t6",
        total_supply=100,
        with_pool=True,
        equity_percent="100.0",
    )
    # pool.total_options=100.
    await _activate_company(client, admin_token, company["id"])

    product1 = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t6_p1"
    )
    product2 = await _create_product(
        client, admin_token, company["id"], package_size=20, suffix="t6_p2"
    )
    await _activate_product(client, admin_token, product1["id"])
    await _activate_product(client, admin_token, product2["id"])

    # Initial availability: pool=100, p1 size=10 -> 10 packs;
    # p2 size=20 -> 5 packs.
    resp1 = await client.get(f"/api/v1/public/products/{product1['id']}")
    assert resp1.status_code == 200
    assert resp1.json()["available_packages"] == 10

    resp2 = await client.get(f"/api/v1/public/products/{product2['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["available_packages"] == 5

    # Buy product1 -> consumed=10, pool_remaining=90.
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t6"
    )
    purchase_resp = await client.post(
        f"/api/v1/products/{product1['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )

    # After: p1 = floor(90/10) = 9, p2 = floor(90/20) = 4. Both dropped.
    resp1 = await client.get(f"/api/v1/public/products/{product1['id']}")
    assert resp1.status_code == 200
    assert resp1.json()["available_packages"] == 9

    resp2 = await client.get(f"/api/v1/public/products/{product2['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["available_packages"] == 4


# ---------------------------------------------------------------------------
# 7: Pool sold out -> 400 on next purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_sold_out(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pool exhausted by first purchase -> second purchase 400 'Sold out'."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        admin_token,
        suffix="t7",
        total_supply=10,
        with_pool=True,
        equity_percent="100.0",
    )
    # pool.total_options=10.
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="t7"
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t7"
    )

    # First purchase empties the pool (consumed=10, remaining=0).
    resp1 = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp1.status_code == 201, f"First purchase failed: {resp1.text}"

    # Second purchase: pool_remaining=0 < package_size=10 -> 400.
    resp2 = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp2.status_code == 400
    assert "Sold out" in resp2.json()["message"]


# ---------------------------------------------------------------------------
# 8: Gift purchase consumes the pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gift_consumes_pool(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase with always-gift bonus: pool consumes both sale and gift units.

    Spec §3.5/§3.7: gift purchases count against the pool just like
    sales. If the pool has room, no overflow happens; consumed equals
    sale_units + gift_units.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        admin_token,
        suffix="t8",
        total_supply=200,
        with_pool=True,
        equity_percent="100.0",
    )
    # pool.total_options=200.
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(
        client,
        admin_token,
        company["id"],
        package_size=100,
        purchase_config={
            "bonuses": [
                {
                    "condition": "always",
                    "bonus_units_percent": 10,
                    "funded_by": "company",
                },
            ],
        },
        suffix="t8",
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t8"
    )
    purchase_resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )
    purchases = purchase_resp.json()
    # One sale + one gift purchase.
    assert len(purchases) == 2

    # consumed = 100 (sale) + 10 (gift) = 110, pool_remaining = 90.
    consumed = await get_pool_consumed(UUID(company["id"]), db_session)
    assert consumed == 110

    pool = await get_active_pool(UUID(company["id"]), db_session)
    assert pool.total_options - consumed == 90


# ---------------------------------------------------------------------------
# 9: Gift overflow into owner supply (pool_remaining goes negative)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gift_overflow_allowed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pool exactly fits the package; gift overflows into owner supply.

    Spec §3.7: gift purchases consume the pool first; if the pool runs
    out, they overflow into owner supply (total_supply - pool.total_options).
    The purchase still succeeds and pool.total_options - consumed
    becomes negative by exactly the gift amount.

    Setup: total_supply=200, equity=50% -> pool=100, owner_supply=100.
    package_size=100, gift=10% -> sale=100 + gift=10 = 110 consumed.
    pool_remaining = 100 - 110 = -10. Owner supply absorbs the 10
    (200 - 110 = 90 still left in the company overall).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client,
        admin_token,
        suffix="t9",
        total_supply=200,
        with_pool=True,
        equity_percent="50.0",
    )
    # pool.total_options=100, owner_supply=100.
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(
        client,
        admin_token,
        company["id"],
        package_size=100,
        purchase_config={
            "bonuses": [
                {
                    "condition": "always",
                    "bonus_units_percent": 10,
                    "funded_by": "company",
                },
            ],
        },
        suffix="t9",
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_t9"
    )

    # Pre-purchase pool_remaining = 100 == package_size, so the gating
    # check in execute_purchase passes. Then sale (100) + gift (10) tip
    # consumed past total_options.
    purchase_resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, (
        f"Purchase failed: {purchase_resp.text}"
    )
    purchases = purchase_resp.json()
    assert len(purchases) == 2

    consumed = await get_pool_consumed(UUID(company["id"]), db_session)
    # 100 sale + 10 gift.
    assert consumed == 110

    pool = await get_active_pool(UUID(company["id"]), db_session)
    # pool_remaining = 100 - 110 = -10 (overflowed by exactly the gift).
    assert pool.total_options - consumed == -10


# ---------------------------------------------------------------------------
# 10: Installment calculator preview returns valid plan_config (B4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_installment_preview(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/products/{id}/installments/preview -> plan_config + summary.

    Setup: package_size=100, price=10000 cents/unit -> total=1_000_000 cents.
    Inputs: num_tranches=6, last_tranche_percent=50, amount_rounding_cents=500.

    Expected (spec §3.9 example):
      regular_pct = (100 - 50) // 5 = 10, actual_last_pct = 50 (no remainder)
      regular_units = 10 * 100 // 100 = 10, last_units = 50
      regular_amount = (1_000_000 // 6 // 500) * 500 = 333 * 500 = 166_500
      last_amount = 1_000_000 - 166_500 * 5 = 167_500
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, suffix="t10",
        total_supply=10_000, with_pool=True, equity_percent="100.0",
    )
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(
        client, admin_token, company["id"], package_size=100, suffix="t10"
    )
    # Note: product.price_per_unit_cents is denormalised from company
    # at creation time = 10000 (set in _create_company).

    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments/preview",
        json={
            "num_tranches": 6,
            "last_tranche_percent": 50,
            "amount_rounding_cents": 500,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, f"Preview failed: {resp.text}"
    body = resp.json()

    plan_config = body["plan_config"]
    assert plan_config["bonus_units"] == 0
    assert plan_config["agent_bonus_units"] == 0
    assert len(plan_config["tranches"]) == 6

    # Regular tranches: percent=10, amount=166_500.
    for i in range(5):
        tranche = plan_config["tranches"][i]
        assert tranche["units_percent"] == 10
        assert tranche["amount_cents"] == 166_500

    # Last tranche: percent=50, amount=167_500 (absorbed remainder).
    last = plan_config["tranches"][5]
    assert last["units_percent"] == 50
    assert last["amount_cents"] == 167_500

    # Summary mirrors the tranche numbers.
    summary = body["summary"]
    assert summary["package_size"] == 100
    assert summary["num_tranches"] == 6
    assert summary["total_amount_cents"] == 1_000_000
    assert summary["regular_amount_cents"] == 166_500
    assert summary["last_amount_cents"] == 167_500
    assert summary["regular_units"] == 10
    assert summary["last_units"] == 50
    assert summary["regular_units_percent"] == 10
    assert summary["last_units_percent"] == 50


# ---------------------------------------------------------------------------
# 11: Calculator output passes invariants and round-trips through create (B4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_installment_preview_invariants(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Calculator output satisfies validate_plan_config invariants.

    Non-trivial input: last_tranche_percent=33, num_tranches=6.
    Integer division leaves a remainder which is absorbed by the last
    tranche -- the actual last percent becomes 35 (not 33). The whole
    plan_config must still be acceptable to POST /installments unchanged
    (round-trip), proving the calculator's inputs and the validator's
    invariants stay in sync.

    Setup: package_size=100, price=10000 -> total=1_000_000.
    Inputs: N=6, last=33, rounding=500.
    Expected:
      regular_pct = 67 // 5 = 13, actual_last_pct = 100 - 13 * 5 = 35
      regular_units = 13, last_units = 35; sum = 13*5 + 35 = 100 ✓
      regular_amount = (1_000_000 // 6 // 500) * 500 = 166_500
      last_amount = 1_000_000 - 166_500 * 5 = 167_500
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, suffix="t11",
        total_supply=10_000, with_pool=True, equity_percent="100.0",
    )
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(
        client, admin_token, company["id"], package_size=100, suffix="t11"
    )

    resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments/preview",
        json={
            "num_tranches": 6,
            "last_tranche_percent": 33,
            "amount_rounding_cents": 500,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, f"Preview failed: {resp.text}"
    body = resp.json()
    plan_config = body["plan_config"]
    summary = body["summary"]

    package_size = 100
    price_per_unit = 10000
    expected_total = package_size * price_per_unit  # 1_000_000

    # -- Invariant 1: sum(amount_cents) == package_size * price --
    sum_amount = sum(t["amount_cents"] for t in plan_config["tranches"])
    assert sum_amount == expected_total
    assert summary["total_amount_cents"] == expected_total

    # -- Invariant 2: sum(units_percent) == 100 --
    sum_pct = sum(t["units_percent"] for t in plan_config["tranches"])
    assert sum_pct == 100

    # -- Invariant 3: integer units decomposition is exact --
    sum_units = sum(
        t["units_percent"] * package_size // 100
        for t in plan_config["tranches"]
    )
    assert sum_units == package_size

    # -- Invariant 4: regular tranche amounts are multiples of rounding --
    for tranche in plan_config["tranches"][:-1]:
        assert tranche["amount_cents"] % 500 == 0

    # -- Invariant 5: remainder absorbed in last tranche --
    # Requested 33% -> actual 35% (33 + 2 from integer-division remainder).
    assert summary["regular_units_percent"] == 13
    assert summary["last_units_percent"] == 35
    assert plan_config["tranches"][-1]["units_percent"] == 35

    # -- Round-trip: calculator output is accepted by create_installment --
    # If validate_plan_config rejects the config the create call returns
    # 400; this test then fails with the validator's message in the body.
    create_resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={
            "name": "Preview round-trip",
            "plan_config": plan_config,
        },
        headers=auth_headers(admin_token),
    )
    assert create_resp.status_code == 201, (
        f"plan_config from preview rejected by create_installment: "
        f"{create_resp.text}"
    )
