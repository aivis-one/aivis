# =============================================================================
# CBSHOME Backend -- Transaction Tests (Sprint 6.4)
# =============================================================================
#
# Tests cover:
#   1:  GET /transactions -> 200 empty list
#   2:  Deposit webhook creates deposit:received transaction
#   3:  GET /transactions with type filter
#   4:  GET /transactions with date range filter
#   5:  GET /transactions with amount range filter
#   6:  GET /transactions/{id} -> 200
#   7:  GET /transactions/{id} other user -> 404
#   8:  GET /transactions type prefix filter (e.g. "deposit:")
#
# Email prefix: "s64t_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transactions.constants import TransactionType
from app.modules.transactions.service import record_transaction
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    register_user,
)

EMAIL_PREFIX = "s64t_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _create_user(
    client: AsyncClient, suffix: str
) -> tuple[UUID, str]:
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), data["session_token"]


# ---------------------------------------------------------------------------
# 1: Empty list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transactions_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await _create_user(client, "empty")
    resp = await client.get(
        "/api/v1/transactions", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["page"] == 1
    assert body["per_page"] == 20


# ---------------------------------------------------------------------------
# 2: record_transaction creates entry visible in list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_created_on_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, token = await _create_user(client, "rec")
    await record_transaction(
        db_session,
        user_id=user_id,
        type=TransactionType.DEPOSIT_RECEIVED,
        amount_cents=50000,
        details={"network": "TRC20", "tx_hash": "0xtest123"},
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["type"] == "deposit:received"
    assert item["amount_cents"] == 50000
    assert item["details"]["network"] == "TRC20"


# ---------------------------------------------------------------------------
# 3: Type filter (exact match)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transactions_type_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, token = await _create_user(client, "filt")
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.DEPOSIT_RECEIVED, amount_cents=10000,
    )
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.WITHDRAWAL_CREATED, amount_cents=-5000,
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions?type=deposit:received",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["type"] == "deposit:received"


# ---------------------------------------------------------------------------
# 4: Date range filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transactions_date_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, token = await _create_user(client, "date")
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.DEPOSIT_RECEIVED, amount_cents=20000,
    )
    await db_session.commit()

    # Future date range -> empty. Use strftime to avoid timezone suffix.
    future = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    resp = await client.get(
        f"/api/v1/transactions?date_from={future}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Past date range -> includes our entry.
    past = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    resp2 = await client.get(
        f"/api/v1/transactions?date_from={past}",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 1


# ---------------------------------------------------------------------------
# 5: Amount range filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transactions_amount_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, token = await _create_user(client, "amt")
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.DEPOSIT_RECEIVED, amount_cents=50000,
    )
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.WITHDRAWAL_CREATED, amount_cents=-5000,
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions?amount_min=10000",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["amount_cents"] == 50000


# ---------------------------------------------------------------------------
# 6: GET by ID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_get_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, token = await _create_user(client, "byid")
    txn = await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.PURCHASE_COMPLETED, amount_cents=-30000,
        details={"product_id": str(uuid4())},
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/transactions/{txn.id}", headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(txn.id)
    assert body["type"] == "purchase:completed"
    assert body["amount_cents"] == -30000


# ---------------------------------------------------------------------------
# 7: GET by ID other user -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transaction_get_other_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id_a, _ = await _create_user(client, "owna")
    _, token_b = await _create_user(client, "ownb")
    txn = await record_transaction(
        db_session, user_id=user_id_a,
        type=TransactionType.DEPOSIT_RECEIVED, amount_cents=10000,
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/transactions/{txn.id}", headers=auth_headers(token_b),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8: Type prefix filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transactions_type_prefix_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, token = await _create_user(client, "pfx")
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.DEPOSIT_RECEIVED, amount_cents=10000,
    )
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.DEPOSIT_CONFIRMED, amount_cents=10000,
    )
    await record_transaction(
        db_session, user_id=user_id,
        type=TransactionType.WITHDRAWAL_CREATED, amount_cents=-5000,
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/transactions?type=deposit:",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for item in body["items"]:
        assert item["type"].startswith("deposit:")
