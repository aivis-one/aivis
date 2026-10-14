# =============================================================================
# AIVIS.ONE Backend -- Installment Worker: KYC pause (H34 P-126)
# =============================================================================
#
# Tests cover (the daemon itself, run_installment_batch -- not pay_tranche
# or default_plan in isolation, which test_installments.py covers):
#   1: an owner who is not APPROVED, in every such status: a due tranche
#      is neither paid nor moved to OVERDUE, whatever the balance.
#   2: an OVERDUE tranche past the grace window of a paused plan does not
#      default the plan -- and its pair: the same plan with an APPROVED
#      owner IS defaulted, so the pause assertion is not vacuous.
#   3: approved again -> the next pass pays the tranche that fell due
#      during the pause.
#   4: the KNOWN CEILING in installments/worker.py::_process_defaults,
#      pinned: the pause does not extend the grace window, so a plan
#      paused past it is defaulted on the first pass after re-approval
#      when the balance is short.
#
# Plan shape: two tranches of 500_000 (test_installments.py's template).
# create_plan pays #1 inline, so every test here works on tranche #2, whose
# due date (and status) the test sets directly.
#
# The daemon walks every due tranche in the database, not just these. The
# assertions are all about this test's own plan; other tests' plans are
# never due (their tranches fall due a month after creation).
# =============================================================================

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.installments.service import create_plan
from app.modules.installments.worker import run_installment_batch
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import get_active_balance, record_active_ledger
from app.modules.users.models import KYCStatus, User
from tests.helpers import auth_headers, create_admin_user, register_user

_TRANCHE_CENTS = 500_000

_NOT_APPROVED = [
    status for status in KYCStatus if status != KYCStatus.APPROVED
]


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def _product_with_template(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[str, str]:
    """An active company, pool, product and a two-tranche template."""
    _, admin = await create_admin_user(client, db_session)
    headers = auth_headers(admin)
    co = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"iw_co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": "Installment Worker Co",
            "description": "Company for the installment worker tests",
            "price_per_unit_cents": 10000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=headers,
    )
    assert co.status_code == 201, co.text
    company_id = co.json()["id"]
    pool = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "100.0"},
        headers=headers,
    )
    assert pool.status_code == 201, pool.text
    prod = await client.post(
        "/api/v1/staff/products",
        json={"company_id": company_id, "name": "Plan Package", "package_size": 100},
        headers=headers,
    )
    assert prod.status_code == 201, prod.text
    product_id = prod.json()["id"]
    for url, body in (
        (f"/api/v1/staff/companies/{company_id}", {"status": "active"}),
        (f"/api/v1/staff/products/{product_id}/status", {"status": "active"}),
    ):
        resp = await client.patch(url, json=body, headers=headers)
        assert resp.status_code == 200, resp.text
    tpl = await client.post(
        f"/api/v1/staff/products/{product_id}/installments",
        json={
            "name": "Two tranches",
            "plan_config": {
                "tranches": [
                    {"amount_cents": _TRANCHE_CENTS, "units_percent": 50},
                    {"amount_cents": _TRANCHE_CENTS, "units_percent": 50},
                ],
                "bonus_units": 0,
                "agent_bonus_units": 0,
            },
        },
        headers=headers,
    )
    assert tpl.status_code == 201, tpl.text
    return product_id, tpl.json()["id"]


async def _plan(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    left_after_first: int,
    second_status: str,
    second_due: datetime,
    owner_status: str,
) -> tuple[UUID, UUID, UUID]:
    """A plan whose tranche #1 is paid and whose tranche #2 is set as given.

    Returns (investor_id, plan_id, tranche_2_id). The owner is APPROVED
    while the plan is created (create_plan refuses anyone else) and then
    moved to owner_status -- the shape a revocation actually takes.
    """
    product_id, template_id = await _product_with_template(client, db_session)
    data = await register_user(client)
    investor_id = UUID(data["user"]["id"])
    await record_active_ledger(
        db_session,
        user_id=investor_id,
        amount_cents=_TRANCHE_CENTS + left_after_first,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_iw_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    investor = await db_session.get(User, investor_id)
    assert investor is not None and investor.kyc_status == KYCStatus.APPROVED
    plan = await create_plan(
        product_id=UUID(product_id),
        product_installment_id=UUID(template_id),
        investor=investor,
        session=db_session,
    )
    await db_session.commit()

    second = (
        await db_session.execute(
            select(InstallmentTranche).where(
                InstallmentTranche.plan_id == plan.id,
                InstallmentTranche.number == 2,
            )
        )
    ).scalar_one()
    second.status = second_status
    second.due_date = second_due.date()
    investor.kyc_status = owner_status
    await db_session.commit()
    return investor_id, plan.id, second.id


async def _state(
    db_session: AsyncSession, plan_id: UUID, tranche_id: UUID
) -> tuple[str, str]:
    db_session.expire_all()
    plan = await db_session.get(InstallmentPlan, plan_id)
    tranche = await db_session.get(InstallmentTranche, tranche_id)
    assert plan is not None and tranche is not None
    return plan.status, tranche.status


async def _available(db_session: AsyncSession, user_id: UUID) -> int:
    balance = await get_active_balance(db_session, user_id)
    return int(balance["frozen"]) + int(balance["confirmed"])


async def _set_owner(db_session: AsyncSession, user_id: UUID, status: str) -> None:
    db_session.expire_all()
    user = await db_session.get(User, user_id)
    assert user is not None
    user.kyc_status = status
    await db_session.commit()


def _days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


# ---------------------------------------------------------------------------
# 1: a due tranche of a paused plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_status", _NOT_APPROVED)
@pytest.mark.parametrize(
    "left_after_first",
    [_TRANCHE_CENTS, 0],
    ids=["balance-covers-it", "balance-short"],
)
async def test_a_paused_plan_is_neither_paid_nor_marked_overdue(
    client: AsyncClient,
    db_session: AsyncSession,
    owner_status: str,
    left_after_first: int,
) -> None:
    """Every status but APPROVED pauses the plan. With the balance there,
    an unpaused daemon would pay; with it short, it would mark OVERDUE.
    Paused, it does neither: the tranche stays SCHEDULED, the plan
    ACTIVE, and not a cent moves."""
    investor_id, plan_id, tranche_id = await _plan(
        client,
        db_session,
        left_after_first=left_after_first,
        second_status=InstallmentTrancheStatus.SCHEDULED,
        second_due=_days_ago(1),
        owner_status=owner_status,
    )

    await run_installment_batch()

    assert await _state(db_session, plan_id, tranche_id) == (
        InstallmentPlanStatus.ACTIVE,
        InstallmentTrancheStatus.SCHEDULED,
    )
    assert await _available(db_session, investor_id) == left_after_first


# ---------------------------------------------------------------------------
# 2: the default path, paused and not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_paused_plan_past_its_grace_window_is_not_defaulted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tranche #2 went OVERDUE before the revocation and its window has
    run out. Paused, the plan stays ACTIVE and the tranche OVERDUE --
    the pause freezes the state, it does not undo it."""
    _, plan_id, tranche_id = await _plan(
        client,
        db_session,
        left_after_first=0,
        second_status=InstallmentTrancheStatus.OVERDUE,
        second_due=_days_ago(settings.installment_default_days + 1),
        owner_status=KYCStatus.REVOKED,
    )

    await run_installment_batch()

    assert await _state(db_session, plan_id, tranche_id) == (
        InstallmentPlanStatus.ACTIVE,
        InstallmentTrancheStatus.OVERDUE,
    )


@pytest.mark.asyncio
async def test_an_approved_plan_past_its_grace_window_is_defaulted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The pair of the test above, one difference: the owner is APPROVED.
    The same daemon pass defaults the plan -- so the plan above stayed
    ACTIVE because of the pause, not because the default path did not
    reach it."""
    _, plan_id, tranche_id = await _plan(
        client,
        db_session,
        left_after_first=0,
        second_status=InstallmentTrancheStatus.OVERDUE,
        second_due=_days_ago(settings.installment_default_days + 1),
        owner_status=KYCStatus.APPROVED,
    )

    await run_installment_batch()

    assert await _state(db_session, plan_id, tranche_id) == (
        InstallmentPlanStatus.DEFAULTED,
        InstallmentTrancheStatus.DEFAULTED,
    )


# ---------------------------------------------------------------------------
# 3: back to APPROVED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_again_the_next_pass_pays(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Paused for a pass, then approved: the next pass pays the tranche
    that fell due during the pause, exactly as if there had been none."""
    investor_id, plan_id, tranche_id = await _plan(
        client,
        db_session,
        left_after_first=_TRANCHE_CENTS,
        second_status=InstallmentTrancheStatus.SCHEDULED,
        second_due=_days_ago(3),
        owner_status=KYCStatus.REVOKED,
    )
    await run_installment_batch()
    assert (await _state(db_session, plan_id, tranche_id))[1] == (
        InstallmentTrancheStatus.SCHEDULED
    )

    await _set_owner(db_session, investor_id, KYCStatus.APPROVED)
    await run_installment_batch()

    assert await _state(db_session, plan_id, tranche_id) == (
        InstallmentPlanStatus.COMPLETED,
        InstallmentTrancheStatus.PAID,
    )
    assert await _available(db_session, investor_id) == 0


# ---------------------------------------------------------------------------
# 4: the acknowledged ceiling, pinned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pause_does_not_extend_the_grace_window(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """KNOWN CEILING in installments/worker.py::_process_defaults, pinned
    as it stands so that a change to it is a decision, not an accident.

    The tranche fell due during a pause longer than the grace window.
    Approved again with a short balance, ONE pass moves it to OVERDUE
    (phase 1) and defaults the plan (phase 2): the window is counted from
    the due date, and the pause used it up."""
    investor_id, plan_id, tranche_id = await _plan(
        client,
        db_session,
        left_after_first=0,
        second_status=InstallmentTrancheStatus.SCHEDULED,
        second_due=_days_ago(settings.installment_default_days + 5),
        owner_status=KYCStatus.REVOKED,
    )
    await run_installment_batch()
    assert await _state(db_session, plan_id, tranche_id) == (
        InstallmentPlanStatus.ACTIVE,
        InstallmentTrancheStatus.SCHEDULED,
    )

    await _set_owner(db_session, investor_id, KYCStatus.APPROVED)
    await run_installment_batch()

    assert await _state(db_session, plan_id, tranche_id) == (
        InstallmentPlanStatus.DEFAULTED,
        InstallmentTrancheStatus.DEFAULTED,
    )
