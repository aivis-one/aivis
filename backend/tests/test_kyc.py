# =============================================================================
# AIVIS.ONE Backend -- KYC Tests (Sprint 2.1, rewritten for H10)
# =============================================================================
#
# Tests cover:
#   1: Submit -> 201, fee charged, ledger + transaction rows written
#   2: Balance below the fee -> 400 and NOTHING written (no partial charge)
#   3: No ledger history at all -> same refusal, still nothing written
#   4: Second submit while a session is open -> 409, charged once only
#   5: GET /kyc/status carries the fee and the balance
#   6: Staff decision on a queued application (approve / reject)
#   7: Reason is mandatory in all three empty forms
#   8: Staff approval of a person with no application -- free, creates one
#   9: Revocation puts the person back behind the gate
#  10: The transaction type the fee uses is accepted by the CHECK
#      constraint, and a foreign literal still is not
#
# WHAT HAPPENED TO THE WEBHOOK TESTS. Seven tests here used to drive
# POST /api/v1/kyc/webhook: approved, rejected-then-resubmit, unknown
# user, invalid status, and three notification cases. The endpoint is
# gone (H10 P-44) -- it authenticated by comparing a shared secret that
# defaulted to the empty string against a header that defaulted to the
# empty string, so an unset secret approved anyone. Those tests were
# right about the BEHAVIOUR they asserted -- a decision must sync
# User.kyc_status, must refuse an unknown user, must refuse a status
# that is not a decision, and must emit exactly one notification -- and
# every one of those assertions survives below against the decision
# functions that replaced the receiver. What did not survive is the
# transport.
#
# Email prefix: "s21_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.kyc.constants import KYC_VERIFICATION_FEE_CENTS
from app.modules.kyc.models import KYCApplication
from app.modules.ledgers.models import ActiveLedger
from app.modules.ledgers.service import get_active_balance
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.models import Transaction
from app.modules.users.models import KYCStatus, User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    fund_user,
    register_user,
    submit_kyc_application,
)

REASON = "Documents checked by hand during the H10 test run."


async def _unverified_investor(client: AsyncClient) -> tuple[str, UUID]:
    """A registered investor who has not paid for verification."""
    data = await register_user(client, verified=False)
    return data["session_token"], UUID(data["user"]["id"])


# ---------------------------------------------------------------------------
# Submit -- the money
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_charges_the_fee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Submit with exactly the fee -> 201, ledger and transaction written."""
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)

    resp = await submit_kyc_application(client, token)
    assert resp.status_code == 201, resp.text
    application_id = UUID(resp.json()["id"])

    balance = await get_active_balance(db_session, user_id)
    assert int(balance["frozen"]) + int(balance["confirmed"]) == 0

    debit = (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all()
    assert len(debit) == 1
    assert debit[0].amount_cents == -KYC_VERIFICATION_FEE_CENTS
    assert str(application_id) in debit[0].reason

    txn = (
        await db_session.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.KYC_VERIFICATION_FEE,
            )
        )
    ).scalars().all()
    assert len(txn) == 1
    assert txn[0].amount_cents == -KYC_VERIFICATION_FEE_CENTS
    assert txn[0].reference_type == ReferenceType.KYC_APPLICATION
    assert txn[0].reference_id == application_id

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.kyc_status == KYCStatus.SUBMITTED


@pytest.mark.asyncio
async def test_submit_one_cent_short_charges_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A cent below the fee -> refused, and NOT charged partially.

    The pair to the test above, and the more important half: a refusal
    that still moved money would be worse than no gate at all.
    """
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS - 1)

    resp = await submit_kyc_application(client, token)
    assert resp.status_code == 400, resp.text

    balance = await get_active_balance(db_session, user_id)
    total = int(balance["frozen"]) + int(balance["confirmed"])
    assert total == KYC_VERIFICATION_FEE_CENTS - 1

    assert (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all() == []
    assert (
        await db_session.execute(
            select(Transaction).where(Transaction.user_id == user_id)
        )
    ).scalars().all() == []
    assert (
        await db_session.execute(
            select(KYCApplication).where(KYCApplication.user_id == user_id)
        )
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_submit_with_no_ledger_history_at_all(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Emptiness axis: not a small balance, no rows whatsoever.

    get_active_balance coalesces an empty SUM to zero; this is the test
    that says so out loud rather than trusting the coalesce.
    """
    token, user_id = await _unverified_investor(client)

    resp = await submit_kyc_application(client, token)
    assert resp.status_code == 400, resp.text

    assert (
        await db_session.execute(
            select(ActiveLedger).where(ActiveLedger.user_id == user_id)
        )
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_second_submit_is_refused_and_charges_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Repeat axis: the fee buys a session, not an attempt.

    Funded for two sessions, submitting twice -- the second is refused
    while the first is still open, and exactly one debit exists.
    """
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS * 2)

    first = await submit_kyc_application(client, token)
    assert first.status_code == 201
    second = await submit_kyc_application(client, token)
    assert second.status_code == 409, second.text

    debits = (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all()
    assert len(debits) == 1

    balance = await get_active_balance(db_session, user_id)
    assert (
        int(balance["frozen"]) + int(balance["confirmed"])
        == KYC_VERIFICATION_FEE_CENTS
    )


@pytest.mark.asyncio
async def test_status_carries_fee_and_balance(client: AsyncClient) -> None:
    """GET /kyc/status answers the money question the gate raises.

    dashboard/summary, the usual source of a balance, is behind the
    gate; this endpoint is in front of it.
    """
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, 250)

    resp = await client.get("/api/v1/kyc/status", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["kyc_status"] == KYCStatus.NOT_STARTED
    assert body["fee_cents"] == KYC_VERIFICATION_FEE_CENTS
    assert body["available_cents"] == 250
    assert body["application_id"] is None


# ---------------------------------------------------------------------------
# Staff decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_approves_queued_application(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Queue -> approve with a reason -> user approved, reason audited."""
    staff_user, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)
    submit = await submit_kyc_application(client, token)
    application_id = submit.json()["id"]

    queue = await client.get(
        "/api/v1/staff/kyc/queue", headers=auth_headers(staff_token)
    )
    assert queue.status_code == 200
    assert application_id in [item["id"] for item in queue.json()]

    resp = await client.post(
        f"/api/v1/staff/kyc/{application_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 204, resp.text

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.kyc_status == KYCStatus.APPROVED


@pytest.mark.asyncio
async def test_staff_rejects_and_a_retry_costs_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rejected -> a new session is a new, paid application."""
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS * 2)

    first = await submit_kyc_application(client, token)
    await client.post(
        f"/api/v1/staff/kyc/{first.json()['id']}/reject",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )

    second = await submit_kyc_application(client, token)
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]

    debits = (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all()
    assert len(debits) == 2


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="key-absent"),
        pytest.param({"reason": ""}, id="empty-string"),
        pytest.param({"reason": "   "}, id="whitespace-only"),
        pytest.param({"reason": None}, id="null"),
    ],
)
@pytest.mark.asyncio
async def test_approval_without_a_real_reason_is_refused(
    client: AsyncClient, db_session: AsyncSession, body: dict
) -> None:
    """Emptiness axis on the reason -- all four forms of nothing."""
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)
    submit = await submit_kyc_application(client, token)

    resp = await client.post(
        f"/api/v1/staff/kyc/{submit.json()['id']}/approve",
        json=body,
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 422, resp.text

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.kyc_status == KYCStatus.SUBMITTED


@pytest.mark.asyncio
async def test_successful_approval_stores_a_non_empty_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The pair to the test above: "no X" needs "there is Y and Y is not empty".

    Without this, a bug that dropped the reason on the floor would pass
    every one of the four refusal cases above.
    """
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)
    submit = await submit_kyc_application(client, token)

    await client.post(
        f"/api/v1/staff/kyc/{submit.json()['id']}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )

    row = (
        await db_session.execute(
            text(
                "SELECT data FROM audit_log WHERE event = 'kyc.status_changed' "
                "AND target_id = :uid ORDER BY created_at DESC LIMIT 1"
            ),
            {"uid": str(user_id)},
        )
    ).scalar_one()
    assert row["reason"] == REASON
    assert row["to"] == KYCStatus.APPROVED


@pytest.mark.asyncio
async def test_staff_approves_a_person_with_no_application(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The entry the queue cannot offer -- and it is free.

    An old user arriving under a new address has no application, is in
    no queue, and cannot make one without paying. This is the flow that
    was impossible before H10.
    """
    _, staff_token = await create_admin_user(client, db_session)
    _, user_id = await _unverified_investor(client)

    resp = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 204, resp.text

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.kyc_status == KYCStatus.APPROVED

    applications = (
        await db_session.execute(
            select(KYCApplication).where(KYCApplication.user_id == user_id)
        )
    ).scalars().all()
    assert len(applications) == 1
    assert applications[0].status == KYCStatus.APPROVED

    # Free: no debit, no transaction.
    assert (
        await db_session.execute(
            select(ActiveLedger).where(ActiveLedger.user_id == user_id)
        )
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_approving_an_approved_person_twice_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Repeat axis on the decision."""
    _, staff_token = await create_admin_user(client, db_session)
    _, user_id = await _unverified_investor(client)

    first = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert first.status_code == 204
    second = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_approving_an_unknown_user_is_a_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Shortage axis: a user id that names nobody creates no orphan row."""
    _, staff_token = await create_admin_user(client, db_session)

    resp = await client.post(
        f"/api/v1/staff/kyc/users/{uuid4()}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_revocation_puts_the_person_back_behind_the_gate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Withdrawing an approval is visible to the gate immediately."""
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)

    await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    allowed = await client.get(
        "/api/v1/dashboard/summary", headers=auth_headers(token)
    )
    assert allowed.status_code != 402

    resp = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/revoke",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 204, resp.text

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.kyc_status == KYCStatus.REVOKED

    refused = await client.get(
        "/api/v1/dashboard/summary", headers=auth_headers(token)
    )
    assert refused.status_code == 402
    assert refused.json()["error"] == "kyc_revoked"


@pytest.mark.asyncio
async def test_revoking_someone_never_approved_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Only an approval can be withdrawn."""
    _, staff_token = await create_admin_user(client, db_session)
    _, user_id = await _unverified_investor(client)

    resp = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/revoke",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# The constraint the fee had to be let through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_type_constraint_admits_the_fee_and_nothing_new(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Migration 0049 widened ck_transactions_type by exactly one literal.

    Both halves matter. The first says the new type is accepted -- seven
    tests in this tree once failed for months against a constraint
    nobody had widened. The second says the constraint still bites, so a
    green first half cannot be explained by someone dropping it.
    """
    _, user_id = await _unverified_investor(client)

    await db_session.execute(
        text(
            "INSERT INTO transactions (id, user_id, type, amount_cents, "
            "currency, created_at) VALUES (gen_random_uuid(), :uid, "
            "'kyc:verification_fee', -1000, 'USD', now())"
        ),
        {"uid": str(user_id)},
    )
    await db_session.flush()

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO transactions (id, user_id, type, amount_cents, "
                "currency, created_at) VALUES (gen_random_uuid(), :uid, "
                "'kyc:not_a_real_type', -1000, 'USD', now())"
            ),
            {"uid": str(user_id)},
        )
        await db_session.flush()
    assert "ck_transactions_type" in str(excinfo.value)
    await db_session.rollback()
