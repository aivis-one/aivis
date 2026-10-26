# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices: manual confirmation (DB-backed)
# =============================================================================
#
# The staff list and the confirmation through the HTTP routes. Needs the test
# database (the conftest fixtures). The DB-free half is
# test_crypto_invoice_manual_confirm.py.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import ActiveLedger
from app.modules.ledgers.service import get_active_balance
from app.modules.payments.models import CryptoInvoice, Payment
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)

_URL = "/api/v1/staff/crypto-invoices"


async def _invoice(
    client: AsyncClient, session: AsyncSession, amount_cents: int = 20000
) -> CryptoInvoice:
    data = await register_user(client)
    invoice = CryptoInvoice(
        id=uuid4(),
        user_id=UUID(data["user"]["id"]),
        service_invoice_id=uuid4(),
        network="USDT-TRC20",
        address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        invoice_amount_cents=amount_cents,
        status="created",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(invoice)
    await session.commit()
    return invoice


@pytest.mark.asyncio
async def test_admin_confirms_and_the_balance_shows_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await create_admin_user(client, db_session)
    invoice = await _invoice(client, db_session)

    resp = await client.post(
        f"{_URL}/{invoice.id}/confirm",
        json={"reason": "paid by bank transfer"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    payment_id = UUID(resp.json()["payment_id"])

    payment = (
        await db_session.execute(select(Payment).where(Payment.id == payment_id))
    ).scalar_one()
    assert payment.status == "confirmed"
    assert payment.provider == "manual"
    assert payment.amount_cents == 20000

    balance = await get_active_balance(db_session, invoice.user_id)
    assert balance["confirmed"] == 20000
    ledger = (
        await db_session.execute(
            select(ActiveLedger).where(ActiveLedger.origin_payment_id == payment_id)
        )
    ).scalar_one()
    assert ledger.reason == f"deposit:manual:{payment_id}"


@pytest.mark.asyncio
async def test_a_second_manual_confirm_is_409_and_credits_nothing_more(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await create_admin_user(client, db_session)
    invoice = await _invoice(client, db_session)
    body = {"reason": "paid by bank transfer"}
    first = await client.post(
        f"{_URL}/{invoice.id}/confirm", json=body, headers=auth_headers(token)
    )
    assert first.status_code == 200
    second = await client.post(
        f"{_URL}/{invoice.id}/confirm", json=body, headers=auth_headers(token)
    )
    assert second.status_code == 409
    balance = await get_active_balance(db_session, invoice.user_id)
    assert balance["confirmed"] == 20000


@pytest.mark.asyncio
async def test_non_admin_staff_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await create_staff_user(client, db_session)
    invoice = await _invoice(client, db_session)
    resp = await client.post(
        f"{_URL}/{invoice.id}/confirm",
        json={"reason": "paid by bank transfer"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert (await client.get(_URL, headers=auth_headers(token))).status_code == 403


@pytest.mark.asyncio
async def test_list_shows_credited_state_and_filters_by_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, token = await create_admin_user(client, db_session)
    paid = await _invoice(client, db_session)
    open_ = await _invoice(client, db_session, amount_cents=500)
    await client.post(
        f"{_URL}/{paid.id}/confirm",
        json={"reason": "paid by bank transfer"},
        headers=auth_headers(token),
    )

    listed = await client.get(
        _URL, params={"user_id": str(paid.user_id)}, headers=auth_headers(token)
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [i["id"] for i in items] == [str(paid.id)]
    assert items[0]["credited"] is True and items[0]["credited_by"] == "manual"

    everything = await client.get(_URL, headers=auth_headers(token))
    by_id = {i["id"]: i for i in everything.json()["items"]}
    assert by_id[str(open_.id)]["credited"] is False
    assert by_id[str(open_.id)]["credited_by"] is None
