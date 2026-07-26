# =============================================================================
# AIVIS.ONE Backend -- Consistency Semaphore Tests (Sprint 6.4)
# =============================================================================
#
# Tests cover:
#   1:  GET /staff/consistency -> 200, response structure
#   2:  Non-staff -> 401/403
#   3:  Staff with financial_operations -> 200
#   4:  S-01 fail: inject unbalanced ledger entry
#   5:  S-05 fail: negative confirmed active balance
#   6:  S-06 fail: negative confirmed passive balance
#   7:  S-12 fail: gift purchase with nonzero paid_cents
#   8:  IS-04 fail: paid tranche without purchase_id
#   9:  Details are JSON-serializable (no Decimal crash)
#   10: Injected violation detected, cleanup restores specific semaphore
#
# NOTE: Tests do NOT assume a globally clean DB. Other test files may leave
#   residual ledger data. Each test injects a specific violation and checks
#   only the targeted semaphore, not overall_status.
#
# Email prefix: "s64c_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)



async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    _, token = await create_admin_user(
        client, db_session
    )
    return token


async def _create_investor(
    client: AsyncClient
) -> tuple[UUID, str]:
    data = await register_user(
        client
    )
    return UUID(data["user"]["id"]), data["session_token"]


def _find(body: dict, name: str) -> dict:
    return next(r for r in body["results"] if r["name"] == name)


# ---------------------------------------------------------------------------
# 1: Response structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consistency_response_structure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /staff/consistency -> 200 with correct structure."""
    token = await _admin_token(client, db_session)
    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] in ("pass", "fail")
    # 19 = 18 original semaphores + IS-07 (completed plans with
    # reversed tranche funding, tranche-unwind round). Bump this pin
    # whenever a semaphore is added to _ALL_SEMAPHORES.
    assert body["total"] == 19
    assert body["passed"] + body["failed"] == body["total"]
    for r in body["results"]:
        assert r["status"] in ("pass", "fail")
        assert r["severity"] in ("critical", "high")


# ---------------------------------------------------------------------------
# 2: Non-staff -> 401/403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consistency_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await _create_investor(client)
    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 3: Staff with permission -> 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consistency_staff_with_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await create_staff_user(
        client, db_session
    )
    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 19  # see structure test for the pin note


# ---------------------------------------------------------------------------
# 4: S-01 fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s01_unbalanced_ledger(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin_token(client, db_session)
    user_id, _ = await _create_investor(client)

    orphan = ActiveLedger(
        user_id=user_id, amount_cents=99999,
        status=LedgerStatus.CONFIRMED, reason="test:orphan",
    )
    db_session.add(orphan)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert _find(resp.json(), "S-01")["status"] == "fail"

    await db_session.delete(orphan)
    await db_session.commit()


# ---------------------------------------------------------------------------
# 5: S-05 fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s05_negative_active_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin_token(client, db_session)
    user_id, _ = await _create_investor(client)

    debit = ActiveLedger(
        user_id=user_id, amount_cents=-50000,
        status=LedgerStatus.CONFIRMED, reason="test:debit",
    )
    db_session.add(debit)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    s05 = _find(resp.json(), "S-05")
    assert s05["status"] == "fail"
    assert s05["details"]["users_with_negative_active"] >= 1

    await db_session.delete(debit)
    await db_session.commit()


# ---------------------------------------------------------------------------
# 6: S-06 fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s06_negative_passive_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin_token(client, db_session)
    user_id, _ = await _create_investor(client)

    debit = PassiveLedger(
        user_id=user_id, amount_cents=-30000,
        status=LedgerStatus.CONFIRMED, reason="test:passive_debit",
    )
    db_session.add(debit)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert _find(resp.json(), "S-06")["status"] == "fail"

    await db_session.delete(debit)
    await db_session.commit()


# ---------------------------------------------------------------------------
# 7: S-12 fail (raw SQL to bypass FK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s12_gift_with_paid_cents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin_token(client, db_session)
    user_id, _ = await _create_investor(client)

    # Disable FK checks for raw INSERT (no real product/company needed).
    await db_session.execute(text("SET session_replication_role = 'replica'"))
    await db_session.execute(
        text("""
            INSERT INTO purchases
                (id, investor_id, product_id, company_id,
                 legal_basis, units, paid_cents, price_per_unit_cents, status)
            VALUES
                (gen_random_uuid(), :uid, gen_random_uuid(), gen_random_uuid(),
                 'gift', 10, 999, 100, 'active')
        """),
        {"uid": user_id},
    )
    await db_session.execute(text("SET session_replication_role = 'origin'"))
    await db_session.commit()

    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    s12 = _find(resp.json(), "S-12")
    assert s12["status"] == "fail"
    assert s12["details"]["gift_purchases_with_nonzero_paid"] >= 1

    await db_session.execute(
        text("DELETE FROM purchases WHERE investor_id = :uid AND paid_cents = 999"),
        {"uid": user_id},
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# 8: IS-04 fail (raw SQL to bypass FK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is04_paid_tranche_no_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin_token(client, db_session)
    user_id, _ = await _create_investor(client)

    # Disable FK checks for raw INSERT (no real product/template needed).
    await db_session.execute(text("SET session_replication_role = 'replica'"))
    # Reuse user_id as plan_id for easy cleanup.
    await db_session.execute(
        text("""
            INSERT INTO installment_plans
                (id, investor_id, product_id, product_installment_id, company_id,
                 plan_config_snapshot, total_price_cents, total_units,
                 price_per_unit_cents, status)
            VALUES
                (:pid, :uid, gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
                 '{"tranches": [], "bonus_units": 0}'::jsonb, 10000, 10, 1000, 'active')
        """),
        {"pid": user_id, "uid": user_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO installment_tranches
                (id, plan_id, number, due_date, amount_cents,
                 units_unlocked, status, purchase_id)
            VALUES
                (gen_random_uuid(), :pid, 1, CURRENT_DATE, 5000, 5, 'paid', NULL)
        """),
        {"pid": user_id},
    )
    await db_session.execute(text("SET session_replication_role = 'origin'"))
    await db_session.commit()

    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    is04 = _find(resp.json(), "IS-04")
    assert is04["status"] == "fail"
    assert is04["details"]["paid_tranches_without_purchase"] >= 1

    await db_session.execute(
        text("DELETE FROM installment_tranches WHERE plan_id = :pid"), {"pid": user_id},
    )
    await db_session.execute(
        text("DELETE FROM installment_plans WHERE id = :pid"), {"pid": user_id},
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# 9: JSON-serializable (no Decimal crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consistency_no_decimal_crash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """All details are JSON-serializable — no Decimal crash."""
    token = await _admin_token(client, db_session)
    resp = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    # 200 means serialization succeeded (Decimal would crash with 500).
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 10: Violation inject + cleanup -> specific semaphore recovers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s05_recovers_after_cleanup(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Adding a violation increments the S-05 counter by exactly one;
    removing it returns the counter to its prior value.

    Per this file's documented contract (see module docstring at the
    top): tests do NOT assume a globally clean DB. Asserting that
    S-05 is `pass` after cleanup would require the entire ledger to
    be free of negative confirmed balances, which is not true across
    test runs -- test_purchases / test_installments / test_withdrawals
    leave residual ledger entries that survive aivis update. So we
    measure the relative change in the S-05 counter, which is a
    stricter check anyway: it proves our orphan -- and only our
    orphan -- moved the count by exactly one in each direction.
    """
    token = await _admin_token(client, db_session)
    user_id, _ = await _create_investor(client)

    # Baseline before any modification.
    resp0 = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp0.status_code == 200
    baseline = _find(
        resp0.json(), "S-05"
    )["details"]["users_with_negative_active"]

    # Inject the S-05 violation.
    orphan = ActiveLedger(
        user_id=user_id, amount_cents=-77777,
        status=LedgerStatus.CONFIRMED, reason="test:cleanup_s05",
    )
    db_session.add(orphan)
    await db_session.commit()

    # Counter went up by exactly one.
    resp1 = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp1.status_code == 200
    count_with_orphan = _find(
        resp1.json(), "S-05"
    )["details"]["users_with_negative_active"]
    assert count_with_orphan == baseline + 1

    # Cleanup.
    await db_session.delete(orphan)
    await db_session.commit()

    # Counter returned to baseline.
    resp2 = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    count_after_cleanup = _find(
        resp2.json(), "S-05"
    )["details"]["users_with_negative_active"]
    assert count_after_cleanup == baseline
