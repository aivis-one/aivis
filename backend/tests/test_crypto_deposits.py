# =============================================================================
# AIVIS.ONE Backend -- Crypto Deposit Tests (Sprint 5.2)
# =============================================================================
#
# Tests cover:
#   1:  Get crypto address -> 200, new address created
#   2:  Get crypto address again (same network) -> 200, idempotent
#   3:  Get crypto address unsupported network -> 400
#   4:  Webhook valid payload -> Payment created, status=frozen, active_ledger entry
#   5:  Webhook invalid secret -> 401
#   6:  Webhook duplicate tx_hash -> 409
#   7:  Webhook unknown to_address -> 404
#   8:  Payment history -> 200, paginated
#   9:  Payment history empty -> 200, items=[]
#   10: get_payment by id -> correct payment returned
#
# Email prefix: "s52_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.ledgers.models import ActiveLedger, LedgerStatus
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import Payment
from app.modules.payments.service import get_payment
from tests.helpers import auth_headers, register_user



def webhook_headers() -> dict[str, str]:
    """Build headers with webhook secret for crypto webhook calls."""
    return {"X-Webhook-Secret": settings.crypto_webhook_secret}


async def _create_user(
    client: AsyncClient
) -> tuple[str, str]:
    """Helper: register user, return (user_id, token)."""
    data = await register_user(
        client
    )
    return data["user"]["id"], data["session_token"]


# ---------------------------------------------------------------------------
# POST /payments/crypto-address
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_crypto_address_new(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get crypto address -> 200, new address created."""
    user_id, token = await _create_user(client)

    resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "TRC20"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["network"] == "TRC20"
    assert body["user_id"] == user_id
    assert body["address"].startswith("AIVIS_TRC20_")


@pytest.mark.asyncio
async def test_get_crypto_address_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get crypto address twice for same network -> same address returned."""
    _, token = await _create_user(client)

    resp1 = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "ERC20"},
        headers=auth_headers(token),
    )
    assert resp1.status_code == 200
    addr1 = resp1.json()["address"]

    resp2 = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "ERC20"},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    addr2 = resp2.json()["address"]

    assert addr1 == addr2


@pytest.mark.asyncio
async def test_get_crypto_address_unsupported_network(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get crypto address for unsupported network -> 400."""
    _, token = await _create_user(client)

    resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "SOLANA"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /payments/crypto/webhook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_valid_payload(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Webhook with valid payload -> Payment created, frozen, active_ledger entry."""
    user_id_str, token = await _create_user(client)
    user_id = UUID(user_id_str)

    # First, create a deposit address.
    addr_resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "TRC20"},
        headers=auth_headers(token),
    )
    to_address = addr_resp.json()["address"]

    # Send webhook.
    tx_hash = f"0x{uuid4().hex}"
    webhook_body = {
        "network": "TRC20",
        "to_address": to_address,
        "from_address": "TSenderWallet123",
        "tx_hash": tx_hash,
        "amount_crypto": "100.50",
        "amount_usd_cents": 10050,
        "confirmed_block": 12345678,
        "exchange_rate": "1.00",
    }
    resp = await client.post(
        "/api/v1/payments/crypto/webhook",
        json=webhook_body,
        headers=webhook_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["payment_status"] == "frozen"
    payment_id = UUID(body["payment_id"])

    # Verify Payment in DB.
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await db_session.execute(stmt)
    payment = result.scalar_one()

    assert payment.user_id == user_id
    assert payment.amount_cents == 10050
    assert payment.status == PaymentStatus.FROZEN
    assert payment.frozen_until is not None
    assert payment.provider_data is not None
    assert payment.provider_data["tx_hash"] == tx_hash

    # Verify active_ledger entry.
    ledger_stmt = select(ActiveLedger).where(
        ActiveLedger.origin_payment_id == payment_id,
    )
    ledger_result = await db_session.execute(ledger_stmt)
    ledger_entry = ledger_result.scalar_one()

    assert ledger_entry.user_id == user_id
    assert ledger_entry.amount_cents == 10050
    assert ledger_entry.status == LedgerStatus.FROZEN
    assert ledger_entry.frozen_until is not None
    assert f"deposit:crypto:{tx_hash}" == ledger_entry.reason


@pytest.mark.asyncio
async def test_webhook_invalid_secret(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Webhook with wrong secret -> 401."""
    resp = await client.post(
        "/api/v1/payments/crypto/webhook",
        json={
            "network": "TRC20",
            "to_address": "AIVIS_TRC20_fake",
            "from_address": "TSender",
            "tx_hash": f"0x{uuid4().hex}",
            "amount_crypto": "50.00",
            "amount_usd_cents": 5000,
        },
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_duplicate_tx_hash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Webhook with duplicate tx_hash -> 409."""
    _, token = await _create_user(client)

    # Create deposit address.
    addr_resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "TRC20"},
        headers=auth_headers(token),
    )
    to_address = addr_resp.json()["address"]

    webhook_body = {
        "network": "TRC20",
        "to_address": to_address,
        "from_address": "TSender",
        "tx_hash": f"0x{uuid4().hex}",
        "amount_crypto": "50.00",
        "amount_usd_cents": 5000,
    }

    # First call -> ok.
    resp1 = await client.post(
        "/api/v1/payments/crypto/webhook",
        json=webhook_body,
        headers=webhook_headers(),
    )
    assert resp1.status_code == 200

    # Second call with same tx_hash -> 409.
    resp2 = await client.post(
        "/api/v1/payments/crypto/webhook",
        json=webhook_body,
        headers=webhook_headers(),
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_webhook_unknown_address(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Webhook with unknown to_address -> 404."""
    resp = await client.post(
        "/api/v1/payments/crypto/webhook",
        json={
            "network": "TRC20",
            "to_address": "AIVIS_TRC20_nonexistent",
            "from_address": "TSender",
            "tx_hash": f"0x{uuid4().hex}",
            "amount_crypto": "10.00",
            "amount_usd_cents": 1000,
        },
        headers=webhook_headers(),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /payments/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_payment_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payment history -> 200, contains the payment we created."""
    _, token = await _create_user(client)

    # Create address + webhook to have a payment.
    addr_resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "BEP20"},
        headers=auth_headers(token),
    )
    to_address = addr_resp.json()["address"]

    await client.post(
        "/api/v1/payments/crypto/webhook",
        json={
            "network": "BEP20",
            "to_address": to_address,
            "from_address": "BSender",
            "tx_hash": f"0x{uuid4().hex}",
            "amount_crypto": "200.00",
            "amount_usd_cents": 20000,
        },
        headers=webhook_headers(),
    )

    # Fetch history.
    resp = await client.get(
        "/api/v1/payments/history",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["total"] == 1
    assert body["page"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["amount_cents"] == 20000
    assert body["items"][0]["status"] == "frozen"


@pytest.mark.asyncio
async def test_payment_history_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payment history for user with no payments -> 200, empty."""
    _, token = await _create_user(client)

    resp = await client.get(
        "/api/v1/payments/history",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# ---------------------------------------------------------------------------
# get_payment service function
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_payment_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """get_payment() returns the correct payment by ID."""
    _, token = await _create_user(client)

    # Create address + webhook.
    addr_resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "PoS"},
        headers=auth_headers(token),
    )
    to_address = addr_resp.json()["address"]

    wh_resp = await client.post(
        "/api/v1/payments/crypto/webhook",
        json={
            "network": "PoS",
            "to_address": to_address,
            "from_address": "PSender",
            "tx_hash": f"0x{uuid4().hex}",
            "amount_crypto": "75.00",
            "amount_usd_cents": 7500,
        },
        headers=webhook_headers(),
    )
    payment_id = UUID(wh_resp.json()["payment_id"])

    # Call service directly.
    payment = await get_payment(payment_id, db_session)

    assert payment.id == payment_id
    assert payment.amount_cents == 7500
    assert payment.status == PaymentStatus.FROZEN
