# =============================================================================
# CBSHOME Backend -- Withdrawal Tests (Sprint 6.3)
# =============================================================================
#
# Tests cover:
#   1:  Create withdrawal -> 201, passive balance debited
#   2:  Create withdrawal without payout_details -> 400
#   3:  Create withdrawal insufficient balance -> 400
#   4:  Create withdrawal below minimum -> 400
#   5:  Create withdrawal above maximum -> 400
#   6:  Create second withdrawal while first pending -> 409
#   7:  Staff confirm -> 200, status=processing (MVP)
#   8:  Staff reject -> 200, passive balance restored
#   9:  List my withdrawals -> 200
#   10: Fail withdrawal -> passive balance restored
#   11: Reject -> compensating transaction has positive amount (TEST-01)
#   12: Fail   -> compensating transaction has positive amount (TEST-01)
# =============================================================================

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import get_passive_balance, record_passive_ledger
from app.modules.transactions.constants import TransactionType
from app.modules.transactions.models import Transaction
from app.modules.users.models import User
from app.modules.withdrawals.constants import WithdrawalStatus
from app.modules.withdrawals.models import Withdrawal
from app.modules.withdrawals.service import fail_withdrawal
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)



async def _create_user_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    balance_cents: int = 100000,
    with_payout_details: bool = True,
) -> tuple[UUID, str]:
    """Register user, set payout_details, credit passive balance.

    Returns (user_id, session_token).
    """
    data = await register_user(
        client
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    # Set payout_details on user.
    if with_payout_details:
        stmt = select(User).where(User.id == user_id)
        result = await db_session.execute(stmt)
        user = result.scalar_one()
        user.set_jsonb("payout_details", {"method": "crypto", "address": "TXyz123"})
        await db_session.flush()

    # Credit passive balance.
    if balance_cents > 0:
        await record_passive_ledger(
            db_session,
            user_id=user_id,
            amount_cents=balance_cents,
            status=LedgerStatus.CONFIRMED,
            reason="test:credit",
        )

    await db_session.commit()
    return user_id, token


# ---------------------------------------------------------------------------
# 1. Create withdrawal -> 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_withdrawal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User creates withdrawal -> 201, passive balance debited."""
    user_id, token = await _create_user_with_balance(
        client, db_session, balance_cents=50000
    )

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 20000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == WithdrawalStatus.PENDING
    assert body["amount_cents"] == 20000
    assert body["user_id"] == str(user_id)
    assert body["payout_details_snapshot"]["method"] == "crypto"

    # Passive balance should be reduced.
    balance = await get_passive_balance(db_session, user_id)
    assert balance["confirmed"] == 30000


# ---------------------------------------------------------------------------
# 2. No payout_details -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_withdrawal_no_payout_details(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User without payout_details -> 400."""
    _, token = await _create_user_with_balance(
        client, db_session, with_payout_details=False
    )

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 10000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "Payout details" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 3. Insufficient balance -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_withdrawal_insufficient_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Withdrawal exceeding confirmed passive balance -> 400."""
    _, token = await _create_user_with_balance(
        client, db_session, balance_cents=5000
    )

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 10000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "Insufficient" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 4. Below minimum -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_withdrawal_below_minimum(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Amount below MIN_WITHDRAWAL_CENTS -> 400."""
    _, token = await _create_user_with_balance(
        client, db_session, balance_cents=100000
    )

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 100},  # Below $10 default minimum
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "Minimum" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 5. Above maximum -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_withdrawal_above_maximum(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Amount above MAX_WITHDRAWAL_CENTS -> 400."""
    _, token = await _create_user_with_balance(
        client, db_session, balance_cents=99999999
    )

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 99999999},  # Above $100k default maximum
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "Maximum" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 6. Duplicate active withdrawal -> 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_withdrawal_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second withdrawal while first is pending -> 409."""
    _, token = await _create_user_with_balance(
        client, db_session, balance_cents=100000
    )

    resp1 = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 10000},
        headers=auth_headers(token),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 10000},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# 7. Staff confirm -> processing (MVP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_confirm_withdrawal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff confirms withdrawal -> status=processing."""
    _, token = await _create_user_with_balance(
        client, db_session, balance_cents=50000
    )
    _, admin_token = await create_admin_user(
        client, db_session
    )

    # Create withdrawal.
    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 20000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    withdrawal_id = resp.json()["id"]

    # Staff confirm.
    resp2 = await client.post(
        f"/api/v1/staff/withdrawals/{withdrawal_id}/confirm",
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] == WithdrawalStatus.PROCESSING
    assert body["confirmed_at"] is not None
    assert body["processing_at"] is not None


# ---------------------------------------------------------------------------
# 8. Staff reject -> balance restored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_reject_withdrawal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff rejects withdrawal -> balance restored via compensating entry."""
    user_id, token = await _create_user_with_balance(
        client, db_session, balance_cents=50000
    )
    _, admin_token = await create_admin_user(
        client, db_session
    )

    # Create withdrawal.
    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 20000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    withdrawal_id = resp.json()["id"]

    # Verify balance reduced.
    balance_before = await get_passive_balance(db_session, user_id)
    assert balance_before["confirmed"] == 30000

    # Staff reject.
    resp2 = await client.post(
        f"/api/v1/staff/withdrawals/{withdrawal_id}/reject",
        json={"reason": "Invalid bank details"},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] == WithdrawalStatus.REJECTED
    assert body["rejection_reason"] == "Invalid bank details"

    # Balance restored.
    db_session.expire_all()
    balance_after = await get_passive_balance(db_session, user_id)
    assert balance_after["confirmed"] == 50000


# ---------------------------------------------------------------------------
# 9. List my withdrawals -> 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_withdrawals(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /withdrawals/me returns user's withdrawal history."""
    _, token = await _create_user_with_balance(
        client, db_session, balance_cents=100000
    )

    # Create a withdrawal.
    await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 10000},
        headers=auth_headers(token),
    )

    resp = await client.get(
        "/api/v1/withdrawals/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["amount_cents"] == 10000


# ---------------------------------------------------------------------------
# 10. Fail withdrawal -> balance restored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_withdrawal_restores_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Failed withdrawal (provider reject) -> compensating entry restores balance."""
    user_id, token = await _create_user_with_balance(
        client, db_session, balance_cents=50000
    )
    _, admin_token = await create_admin_user(
        client, db_session
    )

    # Create and confirm withdrawal.
    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 20000},
        headers=auth_headers(token),
    )
    withdrawal_id = UUID(resp.json()["id"])

    await client.post(
        f"/api/v1/staff/withdrawals/{withdrawal_id}/confirm",
        headers=auth_headers(admin_token),
    )

    # Simulate provider failure via service call.
    await fail_withdrawal(withdrawal_id, db_session)
    await db_session.commit()

    # Verify status.
    db_session.expire_all()
    stmt = select(Withdrawal).where(Withdrawal.id == withdrawal_id)
    result = await db_session.execute(stmt)
    w = result.scalar_one()
    assert w.status == WithdrawalStatus.FAILED

    # Balance restored.
    balance = await get_passive_balance(db_session, user_id)
    assert balance["confirmed"] == 50000


# ---------------------------------------------------------------------------
# 11. Reject -> compensating transaction has positive amount (TEST-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_withdrawal_records_positive_compensating_transaction(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff reject writes a transaction with type=withdrawal:rejected and
    a POSITIVE amount_cents matching the original withdrawal amount.

    Convention (transactions/models.py docstring): positive = money in,
    negative = money out. WITHDRAWAL_CREATED is negative (money leaving
    the user); the compensating WITHDRAWAL_REJECTED on the rejection
    path must be positive (money returning). A sign regression on this
    line would still pass the existing balance-restoration test (which
    asserts the *final* balance via record_passive_ledger), because the
    passive_ledger entry is a separate write. This test pins the sign
    on the transaction log itself.
    """
    user_id, token = await _create_user_with_balance(
        client, db_session, balance_cents=50000
    )
    _, admin_token = await create_admin_user(client, db_session)

    amount = 20000

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": amount},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    withdrawal_id = UUID(resp.json()["id"])

    resp2 = await client.post(
        f"/api/v1/staff/withdrawals/{withdrawal_id}/reject",
        json={"reason": "Test rejection"},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200

    # Locate the compensating transaction. user_id + type + reference_id
    # is sufficient: there is exactly one withdrawal:rejected event per
    # withdrawal lifecycle, and reference_id pins it to this withdrawal.
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.WITHDRAWAL_REJECTED,
        Transaction.reference_id == withdrawal_id,
    )
    txn = (await db_session.execute(stmt)).scalar_one_or_none()

    assert txn is not None, (
        "Staff reject must write a WITHDRAWAL_REJECTED transaction row "
        "referencing this withdrawal."
    )
    assert txn.amount_cents > 0, (
        "Compensating WITHDRAWAL_REJECTED amount must be positive "
        f"(money returning to user). Got {txn.amount_cents}."
    )
    assert txn.amount_cents == amount, (
        "Compensating amount must exactly match the original withdrawal "
        f"amount {amount}; got {txn.amount_cents}."
    )


# ---------------------------------------------------------------------------
# 12. Fail -> compensating transaction has positive amount (TEST-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_withdrawal_records_positive_compensating_transaction(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Provider-fail writes a transaction with type=withdrawal:failed and
    a POSITIVE amount_cents matching the original withdrawal amount.

    Symmetric guard to the reject test above, covering the second exit
    path that compensates the user.
    """
    user_id, token = await _create_user_with_balance(
        client, db_session, balance_cents=50000
    )
    _, admin_token = await create_admin_user(client, db_session)

    amount = 20000

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": amount},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    withdrawal_id = UUID(resp.json()["id"])

    # Confirm first (FAILED can only be reached from PROCESSING).
    await client.post(
        f"/api/v1/staff/withdrawals/{withdrawal_id}/confirm",
        headers=auth_headers(admin_token),
    )

    await fail_withdrawal(withdrawal_id, db_session)
    await db_session.commit()

    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.WITHDRAWAL_FAILED,
        Transaction.reference_id == withdrawal_id,
    )
    txn = (await db_session.execute(stmt)).scalar_one_or_none()

    assert txn is not None, (
        "fail_withdrawal must write a WITHDRAWAL_FAILED transaction row "
        "referencing this withdrawal."
    )
    assert txn.amount_cents > 0, (
        "Compensating WITHDRAWAL_FAILED amount must be positive "
        f"(money returning to user). Got {txn.amount_cents}."
    )
    assert txn.amount_cents == amount, (
        "Compensating amount must exactly match the original withdrawal "
        f"amount {amount}; got {txn.amount_cents}."
    )
