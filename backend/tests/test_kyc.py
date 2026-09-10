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
# H13 ADDED (P-55):
#  11: An approved person cannot buy a second session -- refused before
#      anything is written, in both the "has rows" and the "has no rows"
#      shapes, and refused again on a repeat
#  12: A revoked person still can -- the pair without which 11 would
#      pass for a submit endpoint that refused everybody
#  13: A decision never rewrites a terminal row: approval after a
#      rejection makes a NEW row, while a revocation and a decision on
#      an open session still write the row they belong to
#  14: The audit row for a decision names the status the PERSON left
#  15: The submission rate limit refuses without charging
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

from app.modules.kyc.constants import (
    KYC_SUBMIT_RATE_LIMIT,
    KYC_VERIFICATION_FEE_CENTS,
)
from app.modules.kyc.models import KYCApplication, KYCDocument
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
    set_kyc_status,
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
    """Staff finds the submitted investor, then approves with a reason
    -> user approved, reason audited.

    H17 P-85: the witness step used to be a GET on
    /staff/kyc/queue -- deleted this pass, no frontend consumer since
    iter 2.7 A2 (TD-KYC-QUEUE-ENDPOINT). This test was never really
    about the queue: it is about staff being able to find a submitted
    application before approving it, so the witness moves to
    /staff/users?kyc_status=submitted, the address the real Staff
    Users view has used since that same iteration. The queue endpoint
    returned application_id directly; the user list does not carry
    it, so the assertion checks user_id instead -- the same underlying
    claim ("staff can see this pending session before deciding it"),
    read off the address that is actually live.
    """
    staff_user, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)
    submit = await submit_kyc_application(client, token)
    application_id = submit.json()["id"]

    listing = await client.get(
        "/api/v1/staff/users?kyc_status=submitted",
        headers=auth_headers(staff_token),
    )
    assert listing.status_code == 200
    assert str(user_id) in [item["id"] for item in listing.json()["items"]]

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


# ---------------------------------------------------------------------------
# H13 -- an approved person has nothing left to buy (P-52)
# ---------------------------------------------------------------------------


async def _applications(
    session: AsyncSession, user_id: UUID
) -> list[KYCApplication]:
    """This user's applications, oldest first.

    Ordered by created_at with no tie-breaker, which is safe here and
    only here: every row these tests create is written by its own HTTP
    request, so every row carries its own transaction's now().
    """
    session.expire_all()
    return list(
        (
            await session.execute(
                select(KYCApplication)
                .where(KYCApplication.user_id == user_id)
                .order_by(KYCApplication.created_at.asc())
            )
        ).scalars().all()
    )


async def _latest_decision_audit(session: AsyncSession, user_id: UUID) -> dict:
    """The newest kyc.status_changed row about this user."""
    return (
        await session.execute(
            text(
                "SELECT data FROM audit_log WHERE event = 'kyc.status_changed' "
                "AND target_id = :uid ORDER BY created_at DESC LIMIT 1"
            ),
            {"uid": str(user_id)},
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_submit_from_an_approved_person_costs_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An approved person is refused before anything at all is written.

    The fee buys a session, and somebody already verified has nothing a
    session could give them. Before H13 this charged ten dollars, stored
    a second set of identity documents that this module has no path to
    delete, and pushed the person back behind the gate until staff
    decided again.

    Funded for TWO sessions on purpose, so a charge would have somewhere
    to come from and the assertion is about refusal rather than about an
    empty wallet. Submitted twice -- the repeat axis: a rule that
    refuses once and lets the second through is the same defect one turn
    later. No object check against MinIO is needed to say none were
    written: an object and its kyc_documents row are created together in
    one transaction, so a document count that did not move is an object
    count that did not move.
    """
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS * 2)

    first = await submit_kyc_application(client, token)
    assert first.status_code == 201, first.text
    approved = await client.post(
        f"/api/v1/staff/kyc/{first.json()['id']}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert approved.status_code == 204, approved.text

    for attempt in range(2):
        again = await submit_kyc_application(client, token)
        assert again.status_code == 409, f"attempt {attempt}: {again.text}"
        assert again.json()["error"] == "kyc_already_verified"

    balance = await get_active_balance(db_session, user_id)
    assert (
        int(balance["frozen"]) + int(balance["confirmed"])
        == KYC_VERIFICATION_FEE_CENTS
    )

    applications = await _applications(db_session, user_id)
    assert len(applications) == 1

    debits = (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all()
    assert len(debits) == 1

    transactions = (
        await db_session.execute(
            select(Transaction).where(Transaction.user_id == user_id)
        )
    ).scalars().all()
    assert len(transactions) == 1

    documents = (
        await db_session.execute(
            select(KYCDocument).where(
                KYCDocument.application_id == applications[0].id
            )
        )
    ).scalars().all()
    assert len(documents) == 2  # passport: front + selfie


@pytest.mark.asyncio
async def test_an_approved_person_with_no_application_row_is_refused_too(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Emptiness axis: approved, and not one row in kyc_applications.

    Not a contrived state -- it is what an account imported from the old
    platform looks like, and what tests/helpers.register_user produces
    by default. The refusal reads User.kyc_status rather than the
    application history precisely so that this shape is covered; a check
    written against the newest row would let this person pay.
    """
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)
    await set_kyc_status(user_id, KYCStatus.APPROVED)

    resp = await submit_kyc_application(client, token)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "kyc_already_verified"

    assert await _applications(db_session, user_id) == []
    balance = await get_active_balance(db_session, user_id)
    assert (
        int(balance["frozen"]) + int(balance["confirmed"])
        == KYC_VERIFICATION_FEE_CENTS
    )


@pytest.mark.asyncio
async def test_a_revoked_person_can_still_pay_for_a_new_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The pair to the two tests above: "refuses X" needs "admits Y".

    Without this, a submit endpoint that refused everybody would pass
    both of them. REVOKED is the case worth naming, because it is the
    one an over-broad reading of "already decided" would swallow: the
    person's approval was withdrawn, they have no verification, and
    buying a new session is exactly the route back. (The REJECTED half
    is held by test_staff_rejects_and_a_retry_costs_again above.)
    """
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS * 2)

    first = await submit_kyc_application(client, token)
    assert first.status_code == 201
    await client.post(
        f"/api/v1/staff/kyc/{first.json()['id']}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    revoked = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/revoke",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert revoked.status_code == 204, revoked.text

    second = await submit_kyc_application(client, token)
    assert second.status_code == 201, second.text

    debits = (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all()
    assert len(debits) == 2


# ---------------------------------------------------------------------------
# H13 -- a decision never rewrites a terminal row (P-53)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_after_a_rejection_creates_a_new_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The refused session keeps its documents; the approval claims none.

    Before H13 the user-level approval was written onto the newest row
    whatever it said, so the row that had been REJECTED became APPROVED
    -- and the passport and selfie submitted for a refused session
    became the stated basis of the approval, with the row's
    document_type travelling along and transactions.reference_id
    pointing at a row asserting the opposite of what was paid for.

    Both halves are asserted, and the second is the load-bearing one: a
    new row that inherited document_type would claim documents it does
    not have.
    """
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)

    submit = await submit_kyc_application(client, token)
    assert submit.status_code == 201
    rejected = await client.post(
        f"/api/v1/staff/kyc/{submit.json()['id']}/reject",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert rejected.status_code == 204, rejected.text

    approved = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert approved.status_code == 204, approved.text

    applications = await _applications(db_session, user_id)
    assert [a.status for a in applications] == [
        KYCStatus.REJECTED,
        KYCStatus.APPROVED,
    ]

    old, new = applications
    assert UUID(submit.json()["id"]) == old.id
    assert old.document_type == "passport"
    assert new.document_type is None

    old_documents = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == old.id)
        )
    ).scalars().all()
    assert len(old_documents) == 2

    new_documents = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == new.id)
        )
    ).scalars().all()
    assert new_documents == []

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.kyc_status == KYCStatus.APPROVED


@pytest.mark.asyncio
async def test_revocation_after_an_approval_reuses_the_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The negative twin of the test above -- and the regression to fear.

    Reusing a row is not a bug in general; it is the whole shape of a
    withdrawal, which is by construction a SECOND decision on the row it
    withdraws. _write_decision's notification idempotency_key carries
    the status for exactly this reason. A P-53 fix that made every
    decision open a new row would pass the test above and break this,
    which is why the two are written as a pair.
    """
    _, staff_token = await create_admin_user(client, db_session)
    _, user_id = await _unverified_investor(client)

    approved = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert approved.status_code == 204, approved.text
    created = await _applications(db_session, user_id)
    assert len(created) == 1

    revoked = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/revoke",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert revoked.status_code == 204, revoked.text

    after = await _applications(db_session, user_id)
    assert len(after) == 1
    assert after[0].id == created[0].id
    assert after[0].status == KYCStatus.REVOKED


@pytest.mark.asyncio
async def test_user_level_decision_on_an_open_session_reuses_its_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The other row a decision is entitled to write on: the paid one.

    Staff can approve from the person's card as well as from the queue,
    and when the person has an open session that is the session being
    decided. Opening a second row here would leave a paid SUBMITTED row
    undecided forever -- in the queue, and in front of the gate.
    """
    _, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)

    submit = await submit_kyc_application(client, token)
    assert submit.status_code == 201

    approved = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    assert approved.status_code == 204, approved.text

    applications = await _applications(db_session, user_id)
    assert len(applications) == 1
    assert applications[0].id == UUID(submit.json()["id"])
    assert applications[0].status == KYCStatus.APPROVED
    # The paid session keeps what it was paid for.
    assert applications[0].document_type == "passport"


@pytest.mark.asyncio
async def test_the_decision_audit_names_the_status_the_person_left(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"from" is the user's previous status, not the row's.

    This is the guard on the half of P-53 that has no visible symptom.
    Once an approval after a rejection opens a NEW row, that row is born
    carrying APPROVED, so an audit written from application.status would
    record "from: approved, to: approved" for the transition most worth
    reading: the one where a refusal was overturned.

    The second half covers the branch that was already wrong before
    H13 and is fixed by the same line -- approving somebody who has no
    row at all was audited as a move from APPROVED to APPROVED, for a
    person who had never been approved in their life.
    """
    _, staff_token = await create_admin_user(client, db_session)
    token, rejected_user = await _unverified_investor(client)
    await fund_user(rejected_user, KYC_VERIFICATION_FEE_CENTS)

    submit = await submit_kyc_application(client, token)
    assert submit.status_code == 201
    await client.post(
        f"/api/v1/staff/kyc/{submit.json()['id']}/reject",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )
    await client.post(
        f"/api/v1/staff/kyc/users/{rejected_user}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )

    row = await _latest_decision_audit(db_session, rejected_user)
    assert row["from"] == KYCStatus.REJECTED
    assert row["to"] == KYCStatus.APPROVED

    _, fresh_user = await _unverified_investor(client)
    await client.post(
        f"/api/v1/staff/kyc/users/{fresh_user}/approve",
        json={"reason": REASON},
        headers=auth_headers(staff_token),
    )

    fresh_row = await _latest_decision_audit(db_session, fresh_user)
    assert fresh_row["from"] == KYCStatus.NOT_STARTED
    assert fresh_row["to"] == KYCStatus.APPROVED


# ---------------------------------------------------------------------------
# H13 -- the submission rate limit (P-56)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_rate_limit_refuses_without_charging(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Past the cap the endpoint answers 429 and touches nothing.

    Every request counts, refusals included -- that is the point of a
    limit on an endpoint whose body is buffered in full before anything
    here can decide anything (see the KNOWN CEILING marker in
    kyc/router.py). So the walk is one accepted submission followed by
    conflicts, and the request after the cap is the one that changes
    shape.

    THE conftest clear_rate_limit FIXTURE IS DELIBERATELY NOT EXTENDED
    for this key, and that decision is invisible unless written down.
    It clears the auth-flow families because those are keyed by a fixed
    test IP; this key carries the user's id, every test registers a
    fresh user with a random UUID, and a run creates its database anew.
    Nothing can bleed between tests or between runs, so a cleaner would
    be a fixture that never fires.
    """
    max_requests, _window = KYC_SUBMIT_RATE_LIMIT
    token, user_id = await _unverified_investor(client)
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)

    first = await submit_kyc_application(client, token)
    assert first.status_code == 201, first.text

    for attempt in range(2, max_requests + 1):
        conflict = await submit_kyc_application(client, token)
        assert conflict.status_code == 409, f"attempt {attempt}: {conflict.text}"

    limited = await submit_kyc_application(client, token)
    assert limited.status_code == 429, limited.text
    assert limited.json()["error"] == "rate_limit_exceeded"
    assert "Retry-After" in limited.headers

    debits = (
        await db_session.execute(
            select(ActiveLedger).where(
                ActiveLedger.user_id == user_id,
                ActiveLedger.amount_cents < 0,
            )
        )
    ).scalars().all()
    assert len(debits) == 1
    assert len(await _applications(db_session, user_id)) == 1
