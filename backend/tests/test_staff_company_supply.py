# =============================================================================
# AIVIS.ONE Backend -- Staff Company Supply Change Tests (TASK-39 item 6
#                                                          dilution ruling,
#                                                          owner, 2026-08-29)
# =============================================================================
#
# Tests cover:
#   1: no active pool -- update_supply() is a plain field write, no
#      equity_percent to recompute, audit event carries None/None
#   2: active pool -- total_options stays fixed, equity_percent is
#      recomputed from the NEW total_supply (exact Decimal assert)
#   3: a total_supply decrease that would push equity_percent above
#      100% is rejected, and NOTHING is written -- neither
#      company.total_supply nor pool.equity_percent moves. Includes a
#      dedicated regression case at the exact rounding boundary an
#      adversarial review caught in the first draft of the guard: it
#      compared the QUANTIZED percentage rather than the raw integers,
#      so total_options exceeding total_supply by 1 at ~2M scale
#      rounded down to exactly 100.0000% and slipped past `> 100`.
#   4: new_total_supply == current value is rejected
#   5: _derive_changed_fields (audit/schemas.py) denylists all four
#      company.supply_updated value keys -- no number reaches the
#      company-facing audit feed -- with a must-fire control proving
#      the function is not just unconditionally returning []
#   6: HTTP -- PATCH /supply is 403 for a plain (non-staff) investor
#   7: HTTP -- PATCH /supply happy path through the real router +
#      permission chain, and the same-value guard again through HTTP
#   8: HTTP -- GET /pool returns null for a company with no pool, and
#      the real payload once one exists
#
# ⚠ CANNOT RUN IN THIS SEAT: the suite refuses any DB not named
# `*_test`, and this machine has no local Postgres/Docker. Committed
# UNRUN -- backend tests run on the server via `aivis test`. Test 5
# (the audit denylist) needs no DB at all and WAS run directly against
# a live import during authoring, as was the rounding arithmetic behind
# test 3's regression case -- see the TASK-39 item 6 commit message.
#
# FIXTURE STRATEGY: mirrors test_pool_capacity.py's _mini_company --
# the dev DB is shared, so every test builds its OWN company (+
# optional pool) with a UUID-suffixed name, making absolute asserts
# safe without touching seeded rows.
#
# P-01: services never commit -- tests commit after service calls.
# =============================================================================

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.exceptions import BadRequestError
from app.modules.audit.schemas import _derive_changed_fields
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from app.modules.companies.service import update_supply
from app.modules.pools.models import OptionPool
from app.modules.users.models import User
from tests.helpers import auth_headers, create_admin_user, register_user


async def _mini_company(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    total_supply: int,
    with_pool_total_options: int | None = None,
) -> tuple[CompanyProfile, OptionPool | None]:
    """Build a private company (+ optional active pool) via direct ORM
    inserts -- no HTTP round trip for the company/pool rows themselves,
    since this feature has no self-service surface. Mirrors
    test_pool_capacity.py's _mini_company. company_profiles.user_id is
    a real FK to users.id (RESTRICT, NOT NULL, UNIQUE) -- a random UUID
    would fail at flush, so the owner is a real registered user exactly
    as the pool-capacity fixture does it.
    """
    owner_data = await register_user(client)
    owner_id = uuid.UUID(owner_data["user"]["id"])
    tag = uuid.uuid4().hex[:8]
    company = CompanyProfile(
        user_id=owner_id,
        name=f"SupplyTest Co {tag}",
        description="TASK-39 item 6 dilution test fixture.",
        logo_url=None,
        cover_url=None,
        promo_video_url=None,
        presentation_url=None,
        price_per_unit_cents=1000,
        total_supply=total_supply,
        shares_per_option=1,
        distribution_config={
            "company_pct": 0.80,
            "agent_levels": [0.10, 0.05, 0.05],
        },
        status=CompanyStatus.ACTIVE,
    )
    db_session.add(company)
    await db_session.flush()

    pool: OptionPool | None = None
    if with_pool_total_options is not None:
        pool = OptionPool(
            company_id=company.id,
            equity_percent=Decimal(with_pool_total_options) * 100 / Decimal(total_supply),
            total_options=with_pool_total_options,
            status="active",
        )
        db_session.add(pool)
        await db_session.flush()

    await db_session.commit()
    return company, pool


async def _admin(client: AsyncClient, db_session: AsyncSession) -> User:
    # create_admin_user returns a TUPLE (user, token) -- unpacked here,
    # not assigned whole (the exact bug this ruling's own build caught
    # in its first draft, per the TASK-39 narrative).
    admin, _token = await create_admin_user(client, db_session)
    return admin


# ---------------------------------------------------------------------------
# 1: no active pool -- plain field write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_supply_no_pool_is_plain_write(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company, pool = await _mini_company(client, db_session, total_supply=1_000_000)
    assert pool is None
    admin = await _admin(client, db_session)

    updated = await update_supply(company.id, 1_500_000, admin, db_session)
    await db_session.commit()

    assert updated.total_supply == 1_500_000

    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.target_type == "company",
                AuditLog.target_id == company.id,
                AuditLog.event == "company.supply_updated",
            )
        )
    ).scalar_one()
    assert row.data["old_total_supply"] == 1_000_000
    assert row.data["new_total_supply"] == 1_500_000
    assert row.data["old_equity_percent"] is None
    assert row.data["new_equity_percent"] is None


# ---------------------------------------------------------------------------
# 2: active pool -- total_options fixed, equity_percent recomputed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_supply_recomputes_equity_percent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # 200,000 options over 1,000,000 supply = 20.0000%.
    company, pool = await _mini_company(
        client, db_session, total_supply=1_000_000, with_pool_total_options=200_000
    )
    assert pool is not None
    assert pool.equity_percent == Decimal("20.0000")
    admin = await _admin(client, db_session)

    # Double the supply: options unchanged, percentage HALVES.
    await update_supply(company.id, 2_000_000, admin, db_session)
    await db_session.commit()

    await db_session.refresh(company)
    await db_session.refresh(pool)
    assert company.total_supply == 2_000_000
    assert pool.total_options == 200_000  # unchanged -- the whole point of the ruling
    assert pool.equity_percent == Decimal("10.0000")


# ---------------------------------------------------------------------------
# 3: a decrease that would exceed 100% is rejected, and NOTHING moves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_supply_rejects_over_100_percent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company, pool = await _mini_company(
        client, db_session, total_supply=1_000_000, with_pool_total_options=200_000
    )
    assert pool is not None
    admin = await _admin(client, db_session)

    # 200,000 options over a 150,000 supply would be >100% -- refused.
    with pytest.raises(BadRequestError) as exc:
        await update_supply(company.id, 150_000, admin, db_session)
    await db_session.rollback()
    assert "100%" in str(exc.value)

    # Re-fetch from DB (not the in-memory objects) -- confirms the
    # guard ran BEFORE any write, not merely that a rollback undid one.
    fresh_company = (
        await db_session.execute(
            select(CompanyProfile).where(CompanyProfile.id == company.id)
        )
    ).scalar_one()
    fresh_pool = (
        await db_session.execute(
            select(OptionPool).where(OptionPool.id == pool.id)
        )
    ).scalar_one()
    assert fresh_company.total_supply == 1_000_000
    assert fresh_pool.equity_percent == Decimal("20.0000")


@pytest.mark.asyncio
async def test_update_supply_rejects_rounding_edge_case(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression: the ceiling guard must compare the exact integers,
    never the rounded percentage.

    2,000,002 options over a 2,000,001 supply is total_options >
    total_supply by exactly 1 -- an invalid state (over 100%) that an
    adversarial review caught slipping past a `quantized_pct > 100`
    check: (2000002 / 2000001 * 100) quantizes to exactly 100.0000%
    with Decimal's default ROUND_HALF_EVEN, so the rounded check alone
    would have accepted it. Verified directly against the real
    _compute_equity_percent during authoring: quantized value is
    Decimal('100.0000'), not above 100. The fixed guard compares
    pool.total_options to new_total_supply directly and must still
    reject this.
    """
    company, pool = await _mini_company(
        client, db_session, total_supply=2_000_001, with_pool_total_options=2_000_002
    )
    assert pool is not None
    admin = await _admin(client, db_session)

    with pytest.raises(BadRequestError) as exc:
        await update_supply(company.id, 2_000_001, admin, db_session)
    await db_session.rollback()
    assert "100%" in str(exc.value)

    fresh_company = (
        await db_session.execute(
            select(CompanyProfile).where(CompanyProfile.id == company.id)
        )
    ).scalar_one()
    assert fresh_company.total_supply == 2_000_001  # the fixture's own starting value, unwritten


# ---------------------------------------------------------------------------
# 4: same-value guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_supply_rejects_same_value(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company, _pool = await _mini_company(client, db_session, total_supply=500_000)
    admin = await _admin(client, db_session)

    with pytest.raises(BadRequestError) as exc:
        await update_supply(company.id, 500_000, admin, db_session)
    await db_session.rollback()
    assert "same as the current value" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# 5: the company-facing audit feed must never see a number (no DB needed)
# ---------------------------------------------------------------------------


def test_supply_updated_audit_event_leaks_no_value() -> None:
    """_derive_changed_fields must denylist all four value-only keys.

    Pure function, no DB -- this one WAS run directly (see module
    header) rather than only committed unrun.
    """
    data = {
        "old_total_supply": 1_000_000,
        "new_total_supply": 1_200_000,
        "old_equity_percent": "15.0000",
        "new_equity_percent": "12.5000",
    }
    assert _derive_changed_fields(data) == []

    # Must-fire control: a REAL fields list still passes through
    # verbatim, proving the [] above is the denylist firing and not
    # this function unconditionally returning an empty list.
    control = _derive_changed_fields({"fields": ["name", "total_supply"]})
    assert control == ["name", "total_supply"]


# ---------------------------------------------------------------------------
# 6: HTTP -- 403 for a plain investor (no staff profile at all)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_supply_forbidden_for_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    investor_data = await register_user(client)
    token = investor_data["session_token"]
    fake_id = str(uuid.uuid4())

    resp = await client.patch(
        f"/api/v1/staff/companies/{fake_id}/supply",
        json={"total_supply": 1},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 7: HTTP -- PATCH /supply happy path through the real router/permission
#    chain (adversarial review finding: the direct-service tests above
#    never exercise require_staff_permission("project_manage") + the
#    financial_operations check, or that the route reads body.total_supply
#    into the right service argument)
# ---------------------------------------------------------------------------


async def _create_company_http(client: AsyncClient, admin_token: str) -> dict:
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"supply_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"SupplyHttpCo {uuid.uuid4().hex[:8]}",
            "description": "TASK-39 item 6 GET /pool test company",
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
    return resp.json()


@pytest.mark.asyncio
async def test_patch_supply_happy_path_via_router(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _admin_user, admin_token = await create_admin_user(client, db_session)
    company = await _create_company_http(client, admin_token)
    company_id = company["id"]
    assert company["total_supply"] == 1_000_000

    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}/supply",
        json={"total_supply": 1_500_000},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_supply"] == 1_500_000

    # Same-value guard also holds through the router, not just the
    # direct-service call in test 4.
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}/supply",
        json={"total_supply": 1_500_000},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# 8: HTTP -- GET /pool: null with no pool, real payload once one exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pool_null_then_populated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _admin_user, admin_token = await create_admin_user(client, db_session)
    company = await _create_company_http(client, admin_token)
    company_id = company["id"]

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/pool",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() is None

    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "25.0000"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/pool",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None
    assert body["company_id"] == company_id
    assert body["equity_percent"] == "25.0000"
    assert body["total_options"] == 250_000  # 25% of 1,000,000
    assert body["consumed"] == 0
    assert body["remaining"] == 250_000
