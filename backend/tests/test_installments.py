# =============================================================================
# CBSHOME Backend -- Installment Tests (Sprint 6.2)
# =============================================================================
#
# Tests cover:
#   -- Unit: scheduler (february rule) --
#   1:  calculate_due_date normal month
#   2:  calculate_due_date february clamping (31 -> 28)
#   3:  calculate_due_date leap year february (31 -> 29)
#   4:  calculate_due_date April 30 clamping (31 -> 30)
#   5:  calculate_due_date invalid offset -> ValueError
#
#   -- Unit: validate_plan_config units decomposition --
#   6:  units decompose exactly -> ok
#   7:  units don't decompose -> BadRequestError
#
#   -- Integration: create_plan --
#   8:  create_plan success -> plan + tranches created
#   9:  create_plan template not found -> 404
#   10: create_plan template wrong product -> 400
#   11: create_plan product not active -> 400
#   11b: create_plan without KYC -> 400
#
#   -- Integration: endpoints --
#   12: POST /products/{id}/installment -> 201
#   13: POST /products/{id}/installment non-investor -> 403
#   14: GET /installments/me -> 200
#   15: GET /installments/{id} -> 200 with tranches
#   16: GET /installments/{id} other investor -> 404
#
#   -- Integration: pay_tranche --
#   17: pay_tranche success -> tranche paid + purchase created
#   18: pay_tranche insufficient -> overdue
#
#   -- Integration: complete_plan + default_plan --
#   19: all tranches paid -> plan completed + bonus purchase
#   20: overdue default -> plan defaulted + remaining cancelled
#
# Email prefix: "s62_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import date, datetime, UTC
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.installments.scheduler import calculate_due_date
from app.modules.installments.service import (
    complete_plan,
    create_plan,
    default_plan,
    pay_tranche,
)
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.products.constants import validate_plan_config
from app.modules.purchases.constants import PurchaseLegalBasis
from app.modules.purchases.models import Purchase
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s62_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company(
    client: AsyncClient, admin_token: str, suffix: str = "co1"
) -> dict:
    """Sprint 4.3: also creates active OptionPool for the company."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": 10000,
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
    assert resp.status_code == 201
    company = resp.json()

    # Sprint 4.3: products require an active pool.
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
    *,
    units: int = 100,
) -> dict:
    """Sprint 4.3: kwarg `units` stays for call-site compat; column is package_size."""
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": "Test Package",
            "package_size": units,  # Sprint 4.3: column renamed
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    return resp.json()


async def _activate_product(
    client: AsyncClient, admin_token: str, product_id: str
) -> None:
    resp = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _create_installment_template(
    client: AsyncClient,
    admin_token: str,
    product_id: str,
    *,
    tranches: list[dict] | None = None,
    bonus_units: int = 10,
    agent_bonus_units: int = 5,
) -> dict:
    """Create a ProductInstallment template."""
    if tranches is None:
        # Default: 2 tranches, 50/50 split.
        # Product is 100 units * 10000 cents = 1_000_000 total.
        tranches = [
            {"amount_cents": 500_000, "units_percent": 50},
            {"amount_cents": 500_000, "units_percent": 50},
        ]

    resp = await client.post(
        f"/api/v1/staff/products/{product_id}/installments",
        json={
            "name": "Test Plan",
            "plan_config": {
                "tranches": tranches,
                "bonus_units": bonus_units,
                "agent_bonus_units": agent_bonus_units,
            },
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create installment failed: {resp.text}"
    return resp.json()


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "inv1",
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    # Approve KYC (TD-038: required for installment purchase).
    from app.modules.users.models import User as UserModel
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db_session.execute(stmt)
    user_obj = result.scalar_one()
    user_obj.kyc_status = "approved"
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_s62",
    )
    await db_session.commit()

    return token, user_id


# ---------------------------------------------------------------------------
# Unit tests: scheduler (february rule)
# ---------------------------------------------------------------------------


def test_due_date_normal_month() -> None:
    """Normal month: Jan 15 + 1 month = Feb 15."""
    result = calculate_due_date(date(2026, 1, 15), 1)
    assert result == date(2026, 2, 15)


def test_due_date_february_clamping() -> None:
    """Dec 31 + 2 months = Feb 28 (non-leap year)."""
    result = calculate_due_date(date(2025, 12, 31), 2)
    assert result == date(2026, 2, 28)


def test_due_date_leap_year() -> None:
    """Dec 31 + 2 months in leap year = Feb 29."""
    result = calculate_due_date(date(2027, 12, 31), 2)
    assert result == date(2028, 2, 29)


def test_due_date_april_clamping() -> None:
    """Dec 31 + 4 months = Apr 30."""
    result = calculate_due_date(date(2025, 12, 31), 4)
    assert result == date(2026, 4, 30)


def test_due_date_invalid_offset() -> None:
    """month_offset < 1 -> ValueError."""
    with pytest.raises(ValueError, match="month_offset must be >= 1"):
        calculate_due_date(date(2026, 1, 1), 0)


# ---------------------------------------------------------------------------
# Unit tests: validate_plan_config units decomposition
# ---------------------------------------------------------------------------


def test_units_decomposition_exact() -> None:
    """50/50 split of 100 units -> ok."""
    config = {
        "tranches": [
            {"amount_cents": 500_000, "units_percent": 50},
            {"amount_cents": 500_000, "units_percent": 50},
        ],
        "bonus_units": 0,
        "agent_bonus_units": 0,
    }
    # Should not raise.
    validate_plan_config(config, product_units=100, price_per_unit_cents=10000)


def test_units_decomposition_error() -> None:
    """50/50 split of 7 units -> 3+3=6 != 7 -> error."""
    config = {
        "tranches": [
            {"amount_cents": 35_000, "units_percent": 50},
            {"amount_cents": 35_000, "units_percent": 50},
        ],
        "bonus_units": 0,
        "agent_bonus_units": 0,
    }
    with pytest.raises(BadRequestError, match="units decomposition error"):
        validate_plan_config(config, product_units=7, price_per_unit_cents=10000)


# ---------------------------------------------------------------------------
# Integration tests: create_plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_plan_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_plan -> plan created with correct tranches."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    _, inv_id = await _create_investor_with_balance(client, db_session)

    # Load investor user.
    from app.modules.users.models import User
    inv_user = await db_session.get(User, inv_id)

    plan = await create_plan(
        product_id=UUID(product["id"]),
        product_installment_id=UUID(template["id"]),
        investor=inv_user,
        session=db_session,
    )
    await db_session.commit()

    assert plan.status == InstallmentPlanStatus.ACTIVE
    assert plan.total_price_cents == 1_000_000
    assert plan.total_units == 100

    # Check tranches.
    stmt = (
        select(InstallmentTranche)
        .where(InstallmentTranche.plan_id == plan.id)
        .order_by(InstallmentTranche.number.asc())
    )
    result = await db_session.execute(stmt)
    tranches = list(result.scalars().all())

    assert len(tranches) == 2
    assert tranches[0].number == 1
    assert tranches[0].amount_cents == 500_000
    assert tranches[0].units_unlocked == 50
    # UX-01: create_plan pays tranche #1 inline.
    assert tranches[0].status == InstallmentTrancheStatus.PAID
    assert tranches[0].paid_at is not None
    assert tranches[0].purchase_id is not None
    assert tranches[1].number == 2
    assert tranches[1].units_unlocked == 50
    assert tranches[1].status == InstallmentTrancheStatus.SCHEDULED


@pytest.mark.asyncio
async def test_create_plan_template_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_plan with nonexistent template -> NotFoundError."""
    from uuid import uuid4
    from app.core.exceptions import NotFoundError
    from app.modules.users.models import User

    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    _, inv_id = await _create_investor_with_balance(client, db_session)
    inv_user = await db_session.get(User, inv_id)

    with pytest.raises(NotFoundError):
        await create_plan(
            product_id=UUID(product["id"]),
            product_installment_id=uuid4(),
            investor=inv_user,
            session=db_session,
        )


@pytest.mark.asyncio
async def test_create_plan_template_wrong_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_plan with template from different product -> BadRequestError."""
    from app.modules.users.models import User

    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])

    product1 = await _create_product(client, admin_token, company["id"])
    product2 = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product1["id"])
    await _activate_product(client, admin_token, product2["id"])

    # Template belongs to product2.
    template = await _create_installment_template(client, admin_token, product2["id"])

    _, inv_id = await _create_investor_with_balance(client, db_session)
    inv_user = await db_session.get(User, inv_id)

    with pytest.raises(BadRequestError, match="does not belong"):
        await create_plan(
            product_id=UUID(product1["id"]),
            product_installment_id=UUID(template["id"]),
            investor=inv_user,
            session=db_session,
        )


@pytest.mark.asyncio
async def test_create_plan_product_not_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_plan with non-active product -> BadRequestError."""
    from app.modules.users.models import User

    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    # Product stays hidden (not activated).
    template = await _create_installment_template(client, admin_token, product["id"])

    _, inv_id = await _create_investor_with_balance(client, db_session)
    inv_user = await db_session.get(User, inv_id)

    with pytest.raises(BadRequestError, match="not available for purchase"):
        await create_plan(
            product_id=UUID(product["id"]),
            product_installment_id=UUID(template["id"]),
            investor=inv_user,
            session=db_session,
        )


@pytest.mark.asyncio
async def test_create_plan_no_kyc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_plan without KYC approval -> BadRequestError."""
    from app.modules.users.models import User

    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(
        client, admin_token, product["id"]
    )

    # Investor WITHOUT kyc — just register + fund, no kyc_status change.
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}nokyc@example.com"
    )
    inv_id = UUID(data["user"]["id"])
    await record_active_ledger(
        db_session,
        user_id=inv_id,
        amount_cents=2_000_000,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_nokyc",
    )
    await db_session.commit()

    inv_user = await db_session.get(User, inv_id)
    with pytest.raises(BadRequestError, match="KYC"):
        await create_plan(
            product_id=UUID(product["id"]),
            product_installment_id=UUID(template["id"]),
            investor=inv_user,
            session=db_session,
        )


# ---------------------------------------------------------------------------
# Integration tests: endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_create_installment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /products/{id}/installment -> 201."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(client, db_session)

    resp = await client.post(
        f"/api/v1/products/{product['id']}/installment",
        json={"product_installment_id": template["id"]},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Create installment failed: {resp.text}"

    data = resp.json()
    assert data["status"] == "active"
    assert data["total_price_cents"] == 1_000_000
    assert data["total_units"] == 100


@pytest.mark.asyncio
async def test_endpoint_create_installment_non_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /products/{id}/installment by staff -> 403."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    resp = await client.post(
        f"/api/v1/products/{product['id']}/installment",
        json={"product_installment_id": template["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_endpoint_list_my_plans(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /installments/me -> 200 with plans."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(client, db_session)

    # Create a plan.
    await client.post(
        f"/api/v1/products/{product['id']}/installment",
        json={"product_installment_id": template["id"]},
        headers=auth_headers(inv_token),
    )

    resp = await client.get(
        "/api/v1/installments/me",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_endpoint_plan_detail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /installments/{id} -> 200 with tranches."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(client, db_session)

    create_resp = await client.post(
        f"/api/v1/products/{product['id']}/installment",
        json={"product_installment_id": template["id"]},
        headers=auth_headers(inv_token),
    )
    plan_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/installments/{plan_id}",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tranches"]) == 2
    assert body["tranches"][0]["number"] == 1
    assert body["tranches"][1]["number"] == 2


@pytest.mark.asyncio
async def test_endpoint_plan_detail_other_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /installments/{id} by another investor -> 404."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    inv1_token, _ = await _create_investor_with_balance(client, db_session, suffix="inv1")
    inv2_token, _ = await _create_investor_with_balance(client, db_session, suffix="inv2")

    create_resp = await client.post(
        f"/api/v1/products/{product['id']}/installment",
        json={"product_installment_id": template["id"]},
        headers=auth_headers(inv1_token),
    )
    plan_id = create_resp.json()["id"]

    # Investor 2 tries to access investor 1's plan.
    resp = await client.get(
        f"/api/v1/installments/{plan_id}",
        headers=auth_headers(inv2_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests: pay_tranche, complete, default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pay_tranche_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """pay_tranche with sufficient balance -> tranche paid.

    UX-01 changed create_plan to pay tranche #1 inline, so this test
    exercises pay_tranche against tranche #2 (the first one the daemon
    would normally touch).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    _, inv_id = await _create_investor_with_balance(client, db_session)

    from app.modules.users.models import User
    inv_user = await db_session.get(User, inv_id)

    plan = await create_plan(
        product_id=UUID(product["id"]),
        product_installment_id=UUID(template["id"]),
        investor=inv_user,
        session=db_session,
    )
    await db_session.commit()

    # Tranche #1 was already paid inline by create_plan (UX-01);
    # exercise pay_tranche on #2.
    stmt = (
        select(InstallmentTranche)
        .where(
            InstallmentTranche.plan_id == plan.id,
            InstallmentTranche.number == 2,
        )
    )
    result = await db_session.execute(stmt)
    tranche = result.scalar_one()

    was_paid = await pay_tranche(tranche, plan, db_session)
    await db_session.commit()

    assert was_paid is True

    await db_session.refresh(tranche)
    assert tranche.status == InstallmentTrancheStatus.PAID
    assert tranche.purchase_id is not None
    assert tranche.paid_at is not None


@pytest.mark.asyncio
async def test_create_plan_insufficient_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_plan with insufficient balance -> BadRequestError, nothing persisted.

    UX-01: create_plan pays tranche #1 inline. If the investor can't
    cover it, the whole call aborts and the plan + tranche rows are
    rolled back -- no orphan plan with a day-1 overdue tranche.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    # Investor with only 100 cents -- not enough for 500_000 tranche.
    _, inv_id = await _create_investor_with_balance(
        client, db_session, suffix="inv_broke", balance_cents=100
    )

    from app.modules.users.models import User
    inv_user = await db_session.get(User, inv_id)

    with pytest.raises(BadRequestError, match="[Ii]nsufficient"):
        await create_plan(
            product_id=UUID(product["id"]),
            product_installment_id=UUID(template["id"]),
            investor=inv_user,
            session=db_session,
        )
    await db_session.rollback()

    # Confirm no plan was left behind.
    stmt = select(InstallmentPlan).where(InstallmentPlan.investor_id == inv_id)
    result = await db_session.execute(stmt)
    plans = list(result.scalars().all())
    assert plans == []


@pytest.mark.asyncio
async def test_pay_tranche_insufficient_overdue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """pay_tranche with insufficient balance -> tranche overdue.

    Create a plan with just enough balance to cover tranche #1 (paid
    inline via UX-01). Then exercise pay_tranche on tranche #2 while
    the balance is empty -- expect it to flip to OVERDUE.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    # Balance == 1 * tranche amount: enough for #1, nothing left for #2.
    _, inv_id = await _create_investor_with_balance(
        client, db_session, suffix="inv_just_one", balance_cents=500_000
    )

    from app.modules.users.models import User
    inv_user = await db_session.get(User, inv_id)

    plan = await create_plan(
        product_id=UUID(product["id"]),
        product_installment_id=UUID(template["id"]),
        investor=inv_user,
        session=db_session,
    )
    await db_session.commit()

    # Tranche #1 is now PAID inline; balance is 0. Grab #2.
    stmt = (
        select(InstallmentTranche)
        .where(
            InstallmentTranche.plan_id == plan.id,
            InstallmentTranche.number == 2,
        )
    )
    result = await db_session.execute(stmt)
    tranche = result.scalar_one()

    was_paid = await pay_tranche(tranche, plan, db_session)
    await db_session.commit()

    assert was_paid is False

    await db_session.refresh(tranche)
    assert tranche.status == InstallmentTrancheStatus.OVERDUE


@pytest.mark.asyncio
async def test_complete_plan_with_bonuses(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """All tranches paid -> plan completed, bonus purchase created."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(
        client, admin_token, product["id"],
        bonus_units=10, agent_bonus_units=0,
    )

    _, inv_id = await _create_investor_with_balance(client, db_session)

    from app.modules.users.models import User
    inv_user = await db_session.get(User, inv_id)

    plan = await create_plan(
        product_id=UUID(product["id"]),
        product_installment_id=UUID(template["id"]),
        investor=inv_user,
        session=db_session,
    )
    await db_session.commit()

    # Tranche #1 already paid by create_plan (UX-01); pay only #2 here
    # to drive the plan to completion.
    for tranche_num in [2]:
        stmt = (
            select(InstallmentTranche)
            .where(
                InstallmentTranche.plan_id == plan.id,
                InstallmentTranche.number == tranche_num,
            )
        )
        result = await db_session.execute(stmt)
        tranche = result.scalar_one()
        await pay_tranche(tranche, plan, db_session)
        await db_session.commit()

    # Plan should be completed.
    await db_session.refresh(plan)
    assert plan.status == InstallmentPlanStatus.COMPLETED
    assert plan.completed_at is not None

    # Check bonus purchase was created.
    stmt = (
        select(Purchase)
        .where(
            Purchase.investor_id == inv_id,
            Purchase.legal_basis == PurchaseLegalBasis.GIFT,
        )
    )
    result = await db_session.execute(stmt)
    gift_purchases = list(result.scalars().all())

    assert len(gift_purchases) >= 1
    bonus_purchase = gift_purchases[-1]
    assert bonus_purchase.units == 10
    assert bonus_purchase.paid_cents == 0


@pytest.mark.asyncio
async def test_default_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """default_plan -> plan defaulted, remaining tranches cancelled.

    UX-01 flow: tranche #1 is paid inline by create_plan, so the
    real-world default scenario is that tranche #2 (or later) goes
    overdue past the grace period. The investor is given exactly
    enough for tranche #1 so there is nothing left for the daemon
    to spend on tranche #2.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])
    product = await _create_product(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])
    template = await _create_installment_template(client, admin_token, product["id"])

    # Balance == one tranche: create_plan's inline tranche #1 goes
    # through; tranche #2 will never be affordable.
    _, inv_id = await _create_investor_with_balance(
        client, db_session, suffix="inv_default", balance_cents=500_000
    )

    from app.modules.users.models import User
    inv_user = await db_session.get(User, inv_id)

    plan = await create_plan(
        product_id=UUID(product["id"]),
        product_installment_id=UUID(template["id"]),
        investor=inv_user,
        session=db_session,
    )
    await db_session.commit()

    # Mark tranche #2 as overdue (simulating daemon after grace period).
    stmt = (
        select(InstallmentTranche)
        .where(
            InstallmentTranche.plan_id == plan.id,
            InstallmentTranche.number == 2,
        )
    )
    result = await db_session.execute(stmt)
    tranche2 = result.scalar_one()
    tranche2.status = InstallmentTrancheStatus.OVERDUE
    await db_session.flush()

    # Default the plan.
    await default_plan(plan, tranche2, db_session)
    await db_session.commit()

    await db_session.refresh(plan)
    assert plan.status == InstallmentPlanStatus.DEFAULTED
    assert plan.defaulted_at is not None

    await db_session.refresh(tranche2)
    assert tranche2.status == InstallmentTrancheStatus.DEFAULTED

    # Tranche #1 stays PAID (already executed by UX-01) -- default
    # only cancels scheduled/overdue tranches.
    stmt1 = (
        select(InstallmentTranche)
        .where(
            InstallmentTranche.plan_id == plan.id,
            InstallmentTranche.number == 1,
        )
    )
    result1 = await db_session.execute(stmt1)
    tranche1 = result1.scalar_one()
    assert tranche1.status == InstallmentTrancheStatus.PAID
