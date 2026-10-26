# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices: the client's manual-confirmation
# request and the administrator's notes (DB-backed)
# =============================================================================
#
# Through the HTTP routes, against the test database (the conftest fixtures):
# only the owner may ask, one request per invoice, refused once credited,
# allowed after expiry; the client's invoice read keeps the request across a
# reload; the staff list's filter, mark, reason and notes; the notes' right;
# the Home's count. The DB-free half is test_crypto_invoice_manual_requests.py.
# =============================================================================

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import payments_client
from app.core.audit import AuditLog
from app.modules.payments.models import CryptoInvoice, CryptoWebhookEvent, Payment
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)

_STAFF = "/api/v1/staff/crypto-invoices"
_STATS = "/api/v1/staff/dashboard/stats"


def _request_url(invoice_id: UUID) -> str:
    return f"/api/v1/payments/invoices/{invoice_id}/manual-request"


async def _client_invoice(
    client: AsyncClient,
    session: AsyncSession,
    *,
    status: str = "created",
    expires_in: timedelta = timedelta(hours=1),
) -> tuple[CryptoInvoice, str]:
    """A client with one invoice; returns (invoice, the client's token)."""
    data = await register_user(client)
    invoice = CryptoInvoice(
        id=uuid4(),
        user_id=UUID(data["user"]["id"]),
        service_invoice_id=uuid4(),
        network="USDT-TRC20",
        address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        invoice_amount_cents=20000,
        status=status,
        expires_at=datetime.now(UTC) + expires_in,
    )
    session.add(invoice)
    await session.commit()
    return invoice, data["session_token"]


async def _requests_written(session: AsyncSession, invoice_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.event == "deposit.manual_requested",
                AuditLog.target_id == invoice_id,
            )
        )
    ).scalar_one()


async def _open_count(client: AsyncClient, token: str) -> int:
    resp = await client.get(_STATS, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["manual_topup_requests_count"]


# --- the client's request ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_owner_asks_once_and_a_repeat_returns_the_same_request(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    invoice, token = await _client_invoice(client, db_session)

    first = await client.post(_request_url(invoice.id), headers=auth_headers(token))
    assert first.status_code == 200, first.text
    assert first.json()["already_requested"] is False

    second = await client.post(_request_url(invoice.id), headers=auth_headers(token))
    assert second.status_code == 200
    assert second.json()["already_requested"] is True
    assert second.json()["requested_at"] == first.json()["requested_at"]

    assert await _requests_written(db_session, invoice.id) == 1
    entry = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.event == "deposit.manual_requested",
                AuditLog.target_id == invoice.id,
            )
        )
    ).scalar_one()
    assert entry.target_type == "crypto_invoice"
    assert entry.actor_id == invoice.user_id
    assert entry.data["amount_cents"] == 20000
    assert entry.data["network"] == "USDT-TRC20"


@pytest.mark.asyncio
async def test_somebody_else_cannot_ask_for_the_invoice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    invoice, _ = await _client_invoice(client, db_session)
    other = await register_user(client)
    resp = await client.post(
        _request_url(invoice.id), headers=auth_headers(other["session_token"])
    )
    assert resp.status_code == 404
    assert await _requests_written(db_session, invoice.id) == 0


@pytest.mark.asyncio
async def test_an_expired_invoice_may_still_be_asked_for(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    invoice, token = await _client_invoice(
        client, db_session, status="expired", expires_in=-timedelta(hours=2)
    )
    resp = await client.post(_request_url(invoice.id), headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert await _requests_written(db_session, invoice.id) == 1


@pytest.mark.asyncio
async def test_an_invoice_credited_by_hand_is_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    invoice, token = await _client_invoice(client, db_session)
    confirmed = await client.post(
        f"{_STAFF}/{invoice.id}/confirm",
        json={"reason": "paid by bank transfer"},
        headers=auth_headers(admin_token),
    )
    assert confirmed.status_code == 200
    resp = await client.post(_request_url(invoice.id), headers=auth_headers(token))
    assert resp.status_code == 409
    assert await _requests_written(db_session, invoice.id) == 0


@pytest.mark.asyncio
async def test_an_invoice_the_service_credited_is_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    invoice, token = await _client_invoice(client, db_session)
    frozen = Payment(
        user_id=invoice.user_id,
        amount_cents=20000,
        currency="USD",
        payment_type="crypto",
        provider="crypto_usdt_usdt-trc20",
        status="frozen",
        frozen_until=datetime.now(UTC) + timedelta(hours=1),
        provider_data={"service_invoice_id": str(invoice.service_invoice_id)},
    )
    db_session.add(frozen)
    await db_session.flush()
    db_session.add(
        CryptoWebhookEvent(
            invoice_id=invoice.service_invoice_id,
            status="confirmed",
            product_ref=invoice.id,
            credited_amount_cents=20000,
            occurred_at=datetime.now(UTC),
            outcome="credited",
            payment_id=frozen.id,
        )
    )
    await db_session.commit()
    resp = await client.post(_request_url(invoice.id), headers=auth_headers(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_the_invoice_read_keeps_the_request_across_a_reload(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoice, token = await _client_invoice(client, db_session)

    async def remote(_service_id: UUID) -> dict[str, Any]:
        return {"status": "created", "attempts_remaining": 3}

    monkeypatch.setattr(payments_client, "get_invoice", remote)
    url = f"/api/v1/payments/invoices/{invoice.id}"

    before = await client.get(url, headers=auth_headers(token))
    assert before.status_code == 200, before.text
    assert before.json()["manual_requested_at"] is None
    assert before.json()["manually_credited"] is False

    await client.post(_request_url(invoice.id), headers=auth_headers(token))
    after = await client.get(url, headers=auth_headers(token))
    assert after.json()["manual_requested_at"] is not None
    current = await client.get(
        "/api/v1/payments/invoices/current",
        params={"network": "USDT-TRC20"},
        headers=auth_headers(token),
    )
    assert current.json()["manual_requested_at"] is not None
    # Staff-only facts never reach the client.
    assert "notes" not in after.json() and "confirm_reason" not in after.json()

    _, admin_token = await create_admin_user(client, db_session)
    await client.post(
        f"{_STAFF}/{invoice.id}/confirm",
        json={"reason": "paid by bank transfer"},
        headers=auth_headers(admin_token),
    )
    credited = await client.get(url, headers=auth_headers(token))
    assert credited.json()["manually_credited"] is True


# --- the staff side ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_list_marks_filters_and_counts_open_requests(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    asked, asked_token = await _client_invoice(client, db_session)
    paid, paid_token = await _client_invoice(client, db_session)
    plain, _ = await _client_invoice(client, db_session)

    start = await _open_count(client, admin_token)
    await client.post(_request_url(asked.id), headers=auth_headers(asked_token))
    await client.post(_request_url(paid.id), headers=auth_headers(paid_token))
    assert await _open_count(client, admin_token) == start + 2

    reason = "paid by bank transfer, checked the statement"
    await client.post(
        f"{_STAFF}/{paid.id}/confirm",
        json={"reason": reason},
        headers=auth_headers(admin_token),
    )
    assert await _open_count(client, admin_token) == start + 1

    filtered = await client.get(
        _STAFF,
        params={"open_request": "true", "per_page": 100},
        headers=auth_headers(admin_token),
    )
    assert filtered.status_code == 200, filtered.text
    ids = {i["id"] for i in filtered.json()["items"]}
    assert str(asked.id) in ids
    assert str(paid.id) not in ids and str(plain.id) not in ids
    assert all(i["manual_request_open"] for i in filtered.json()["items"])

    for invoice, open_, requested in (
        (asked, True, True),
        (paid, False, True),
        (plain, False, False),
    ):
        listed = await client.get(
            _STAFF,
            params={"user_id": str(invoice.user_id)},
            headers=auth_headers(admin_token),
        )
        (row,) = listed.json()["items"]
        assert row["manual_request_open"] is open_
        assert (row["manual_requested_at"] is not None) is requested

    paid_row = (
        await client.get(
            _STAFF,
            params={"user_id": str(paid.user_id)},
            headers=auth_headers(admin_token),
        )
    ).json()["items"][0]
    assert paid_row["credited_by"] == "manual"
    assert paid_row["confirm_reason"] == reason


@pytest.mark.asyncio
async def test_notes_are_written_by_an_administrator_and_listed_oldest_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    invoice, _ = await _client_invoice(client, db_session)
    url = f"{_STAFF}/{invoice.id}/notes"

    first = await client.post(
        url,
        json={"text": "asked for the bank statement"},
        headers=auth_headers(admin_token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["author_name"]
    # A note after the confirmation is allowed as well.
    await client.post(
        f"{_STAFF}/{invoice.id}/confirm",
        json={"reason": "paid by bank transfer"},
        headers=auth_headers(admin_token),
    )
    second = await client.post(
        url, json={"text": "statement received"}, headers=auth_headers(admin_token)
    )
    assert second.status_code == 200

    too_short = await client.post(
        url, json={"text": " a "}, headers=auth_headers(admin_token)
    )
    assert too_short.status_code == 422

    listed = await client.get(
        _STAFF,
        params={"user_id": str(invoice.user_id)},
        headers=auth_headers(admin_token),
    )
    notes = listed.json()["items"][0]["notes"]
    assert [n["text"] for n in notes] == [
        "asked for the bank statement",
        "statement received",
    ]
    assert all(n["created_at"] and n["author_name"] for n in notes)

    missing = await client.post(
        f"{_STAFF}/{uuid4()}/notes",
        json={"text": "nothing"},
        headers=auth_headers(admin_token),
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_staff_without_the_administrator_mark_cannot_write_notes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, staff_token = await create_staff_user(client, db_session)
    invoice, client_token = await _client_invoice(client, db_session)
    url = f"{_STAFF}/{invoice.id}/notes"
    assert (
        await client.post(
            url, json={"text": "a note"}, headers=auth_headers(staff_token)
        )
    ).status_code == 403
    # Nor can the client reach the staff route.
    assert (
        await client.post(
            url, json={"text": "a note"}, headers=auth_headers(client_token)
        )
    ).status_code in (401, 403)
