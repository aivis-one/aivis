# =============================================================================
# AIVIS.ONE Backend -- Payments webhook receiver tests (H8)
# =============================================================================
#
# The inbound half of the payments integration: the service POSTs an
# event here when an invoice reaches a terminal status, and this is what
# turns that event into a balance.
#
# WHAT IS COVERED, AND WHY EACH ONE HAS A PAIR:
#
#   1: the secret. Empty configured secret is fail-closed -- PAIRED with
#      a configured secret that lets a request through, because a
#      receiver that rejects everything would pass the first assertion
#      on its own and be useless.
#   2: deduplication. A repeat of (invoice_id, status) credits nothing
#      -- PAIRED with the first delivery crediting, because a receiver
#      that never credits also passes "the second one did not credit".
#   3: a zero credit is a real credit, not an absence. A dust transfer
#      confirms an invoice and credits 0.
#   4: an ABSENT optional key and an explicit null are different inputs,
#      asserted separately rather than as one "falsy" case.
#   5: all four service statuses, one test each.
#
# THREE AXES ON EVERY INPUT (repeat / emptiness / wrong shape) are
# spread across the file and named in each test's docstring.
#
# NO SERVICE IS DRIVEN HERE. The events are built by hand, which is what
# the service's delivery does over HTTP anyway -- there is nothing in
# between to fake.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.ledgers.models import ActiveLedger, LedgerStatus
from app.modules.payments.constants import PaymentStatus, WebhookOutcome
from app.modules.payments.models import CryptoInvoice, CryptoWebhookEvent, Payment
from tests.helpers import register_user

_SECRET = "h8-webhook-secret"
_NETWORK = "USDT-TRC20"
_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
_URL = "/api/v1/payments/webhook"


@pytest.fixture
def configured_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """A receiver with a secret set, which is the normal deployment."""
    monkeypatch.setattr(settings, "payments_webhook_secret", _SECRET)
    return _SECRET


async def _make_invoice(
    client: AsyncClient,
    session: AsyncSession,
    *,
    amount_cents: int = 20000,
) -> CryptoInvoice:
    """A user with one open invoice, built the way open_invoice builds it.

    product_ref is the row's primary key and is minted before the
    service is called, so an event's product_ref is always a key here.
    """
    data = await register_user(client)
    invoice = CryptoInvoice(
        id=uuid4(),
        user_id=UUID(data["user"]["id"]),
        service_invoice_id=uuid4(),
        network=_NETWORK,
        address=_ADDRESS,
        invoice_amount_cents=amount_cents,
        status="created",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(invoice)
    await session.commit()
    return invoice


def _event(
    invoice: CryptoInvoice,
    status: str = "confirmed",
    **extra: object,
) -> dict[str, object]:
    """An event body in the shape TOR section 8 fixes.

    Optional keys are ABSENT unless a test passes them, which is how the
    service behaves: it omits them rather than sending null.
    """
    body: dict[str, object] = {
        "invoice_id": str(invoice.service_invoice_id),
        "product_ref": str(invoice.id),
        "status": status,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    body.update(extra)
    return body


async def _balance_rows(
    session: AsyncSession, user_id: UUID
) -> list[ActiveLedger]:
    result = await session.execute(
        select(ActiveLedger).where(ActiveLedger.user_id == user_id)
    )
    return list(result.scalars().all())


async def _payments_of(session: AsyncSession, user_id: UUID) -> list[Payment]:
    result = await session.execute(
        select(Payment).where(Payment.user_id == user_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 1. The secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_configured_secret_rejects_everything(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: an unconfigured receiver is not an open one.

    EMPTINESS AXIS ON THE HEADER, and the reason the emptiness check
    runs before compare_digest: compare_digest("", "") is TRUE, so a box
    with no secret configured would otherwise accept every request that
    omits the header -- and the header defaults to "".
    """
    monkeypatch.setattr(settings, "payments_webhook_secret", "")
    invoice = await _make_invoice(client, db_session)

    no_header = await client.post(_URL, json=_event(invoice))
    empty_header = await client.post(
        _URL, json=_event(invoice), headers={"X-Payments-Secret": ""}
    )
    some_header = await client.post(
        _URL, json=_event(invoice), headers={"X-Payments-Secret": "anything"}
    )

    assert no_header.status_code == 401
    assert empty_header.status_code == 401
    assert some_header.status_code == 401

    # The pair to "nothing was accepted": nothing was written either.
    assert await _payments_of(db_session, invoice.user_id) == []


@pytest.mark.asyncio
async def test_configured_secret_admits_and_wrong_one_does_not(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The pair for the test above: a real secret does let a delivery in.

    WRONG-SHAPE AXIS ON THE HEADER: a truncated secret, a case-flipped
    one and one with trailing whitespace are all rejected. Without this
    pair, a receiver that rejected every request would pass the
    fail-closed test and look correct.
    """
    invoice = await _make_invoice(client, db_session)

    for wrong in (
        configured_secret[:-1],
        configured_secret.upper(),
        configured_secret + " ",
    ):
        resp = await client.post(
            _URL, json=_event(invoice), headers={"X-Payments-Secret": wrong}
        )
        assert resp.status_code == 401, wrong

    accepted = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=20000),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert accepted.status_code == 200
    assert accepted.json()["outcome"] == WebhookOutcome.CREDITED.value


@pytest.mark.asyncio
async def test_receiver_requires_no_user_session(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The endpoint authenticates the SERVICE, not a user.

    No Authorization header, no session cookie: the caller is another
    process. If this ever starts requiring a user, every delivery
    becomes a 401 and every payment stops.
    """
    invoice = await _make_invoice(client, db_session)
    resp = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=15000),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Deduplication -- and its pair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_confirmed_event_credits(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The pair to the duplicate test: a first delivery moves money.

    Asserts the whole chain, because a Payment with no ledger entry is
    not a credited balance: Payment (frozen) + ActiveLedger (frozen,
    linked by origin_payment_id) + the event row recording the outcome.
    """
    invoice = await _make_invoice(client, db_session)

    resp = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=20000, underpaid=False),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == WebhookOutcome.CREDITED.value

    payments = await _payments_of(db_session, invoice.user_id)
    assert len(payments) == 1
    assert payments[0].amount_cents == 20000
    # FROZEN, not CONFIRMED: the cooling-off is what run_confirmation_batch
    # later flips, and that flip is the only emitter of the
    # deposit.confirmed notification.
    assert payments[0].status == PaymentStatus.FROZEN
    assert payments[0].frozen_until is not None

    entries = await _balance_rows(db_session, invoice.user_id)
    assert len(entries) == 1
    assert entries[0].amount_cents == 20000
    assert entries[0].status == LedgerStatus.FROZEN
    assert entries[0].origin_payment_id == payments[0].id
    assert str(invoice.service_invoice_id) in entries[0].reason


@pytest.mark.asyncio
async def test_repeat_of_same_invoice_and_status_credits_once(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """REPEAT AXIS ON THE BODY: at-least-once delivery must not pay twice.

    The service re-delivers after a restart or an expired lease, so this
    is normal traffic rather than an attack. The second delivery is
    answered 200 -- a non-2xx would make the service retry a duplicate
    until its outbox row died.
    """
    invoice = await _make_invoice(client, db_session)
    body = _event(invoice, credited_amount_cents=20000)
    headers = {"X-Payments-Secret": configured_secret}

    first = await client.post(_URL, json=body, headers=headers)
    second = await client.post(_URL, json=body, headers=headers)
    third = await client.post(_URL, json=body, headers=headers)

    assert first.json()["outcome"] == WebhookOutcome.CREDITED.value
    assert second.status_code == 200
    assert second.json()["outcome"] == "duplicate"
    assert third.json()["outcome"] == "duplicate"

    assert len(await _payments_of(db_session, invoice.user_id)) == 1
    entries = await _balance_rows(db_session, invoice.user_id)
    assert len(entries) == 1
    assert sum(e.amount_cents for e in entries) == 20000


@pytest.mark.asyncio
async def test_two_statuses_for_one_invoice_are_two_events(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The dedup key is the PAIR, not the invoice.

    REPEAT AXIS ON product_ref: the same invoice legitimately produces
    more than one event, and deduplicating on the invoice alone would
    swallow the second. `expired` then `confirmed` is the ordering the
    service's lazy resolution actually produces.
    """
    invoice = await _make_invoice(client, db_session)
    headers = {"X-Payments-Secret": configured_secret}

    expired = await client.post(
        _URL, json=_event(invoice, status="expired"), headers=headers
    )
    confirmed = await client.post(
        _URL,
        json=_event(invoice, status="confirmed", credited_amount_cents=20000),
        headers=headers,
    )

    assert expired.json()["outcome"] == WebhookOutcome.STATUS_CACHED.value
    # CREDITED DESPITE THE EARLIER `expired`. The decision is made on the
    # amount in the event, never on the cached status column -- and the
    # service resolves expiry lazily, so this ordering is expected
    # rather than a contradiction.
    assert confirmed.json()["outcome"] == WebhookOutcome.CREDITED.value
    assert len(await _payments_of(db_session, invoice.user_id)) == 1


# ---------------------------------------------------------------------------
# 3. A zero credit is a credit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_credit_is_a_normal_path(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """A dust transfer confirms the invoice and credits nothing.

    credited_amount_cents = 0 with underpaid = true is a real event, not
    a malformed one. Anything testing this field for truthiness reads
    the zero as "no amount arrived" and drops the whole event -- which
    would also lose the record that the invoice was settled.
    """
    invoice = await _make_invoice(client, db_session)

    resp = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=0, underpaid=True),
        headers={"X-Payments-Secret": configured_secret},
    )

    assert resp.status_code == 200
    assert resp.json()["outcome"] == WebhookOutcome.CREDITED.value

    payments = await _payments_of(db_session, invoice.user_id)
    assert len(payments) == 1
    assert payments[0].amount_cents == 0
    assert payments[0].provider_data is not None
    assert payments[0].provider_data["underpaid"] is True

    entries = await _balance_rows(db_session, invoice.user_id)
    assert len(entries) == 1
    assert entries[0].amount_cents == 0


# ---------------------------------------------------------------------------
# 4. Absent key vs explicit null -- separately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirmed_without_the_amount_key_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """EMPTINESS AXIS ON THE BODY: a confirmed event carrying no amount.

    422 rather than 200: there is no amount to credit and the receiver
    will not guess one. The cost is named rather than hidden -- the
    service's outbox row ends up `failed` with its last error, which is
    a trace that can be FOUND with a query, where a 200 would leave the
    failure only in our own logs.
    """
    invoice = await _make_invoice(client, db_session)

    resp = await client.post(
        _URL,
        json=_event(invoice, status="confirmed"),
        headers={"X-Payments-Secret": configured_secret},
    )

    assert resp.status_code == 422
    assert await _payments_of(db_session, invoice.user_id) == []
    # A refused event leaves NO event row: it was not processed, and a
    # row saying otherwise would make a corrected redelivery look like a
    # duplicate.
    result = await db_session.execute(
        select(CryptoWebhookEvent).where(
            CryptoWebhookEvent.invoice_id == invoice.service_invoice_id
        )
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_explicit_null_amount_is_refused_by_the_schema(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The other half of the pair above: null is NOT the same as absent.

    The service omits an optional key it cannot fill; it never sends
    null. So a null is a body this service does not produce, and
    accepting it as "absent" would hide whatever produced it. Asserted
    separately from the absent case on purpose -- one test covering
    "falsy" would not distinguish them, which is exactly the confusion
    being guarded against.
    """
    invoice = await _make_invoice(client, db_session)
    headers = {"X-Payments-Secret": configured_secret}

    null_amount = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=None),
        headers=headers,
    )
    null_underpaid = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=100, underpaid=None),
        headers=headers,
    )

    assert null_amount.status_code == 422
    assert null_underpaid.status_code == 422
    assert await _payments_of(db_session, invoice.user_id) == []


@pytest.mark.asyncio
async def test_absent_optional_keys_are_stored_as_null_not_zero(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The event row keeps "absent" and "zero" apart on disk too.

    An expired event carries neither optional key. Storing 0 for the
    absent amount would make the row claim the service reported a zero
    credit, which is a different fact.
    """
    invoice = await _make_invoice(client, db_session)

    await client.post(
        _URL,
        json=_event(invoice, status="expired"),
        headers={"X-Payments-Secret": configured_secret},
    )

    result = await db_session.execute(
        select(CryptoWebhookEvent).where(
            CryptoWebhookEvent.invoice_id == invoice.service_invoice_id
        )
    )
    row = result.scalar_one()
    assert row.credited_amount_cents is None
    assert row.underpaid is None


# ---------------------------------------------------------------------------
# 5. All four statuses, one test each
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirmed_status_credits(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """confirmed -- the only status that moves money."""
    invoice = await _make_invoice(client, db_session)
    resp = await client.post(
        _URL,
        json=_event(invoice, status="confirmed", credited_amount_cents=12345),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.json()["outcome"] == WebhookOutcome.CREDITED.value
    await db_session.refresh(invoice)
    assert invoice.status == "confirmed"


@pytest.mark.asyncio
async def test_expired_status_is_accepted_and_credits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """expired -- accepted, cached, no money.

    Accepted rather than ignored: an ignored event is retried until the
    service's outbox row goes `failed`, and the cached status a screen
    reads would stay stale.
    """
    invoice = await _make_invoice(client, db_session)
    resp = await client.post(
        _URL,
        json=_event(invoice, status="expired"),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == WebhookOutcome.STATUS_CACHED.value
    assert await _payments_of(db_session, invoice.user_id) == []
    await db_session.refresh(invoice)
    assert invoice.status == "expired"


@pytest.mark.asyncio
async def test_attempts_exhausted_status_is_accepted_and_credits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """attempts_exhausted -- accepted, cached, no money."""
    invoice = await _make_invoice(client, db_session)
    resp = await client.post(
        _URL,
        json=_event(invoice, status="attempts_exhausted"),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == WebhookOutcome.STATUS_CACHED.value
    assert await _payments_of(db_session, invoice.user_id) == []
    await db_session.refresh(invoice)
    assert invoice.status == "attempts_exhausted"


@pytest.mark.asyncio
async def test_stalled_status_is_accepted_and_credits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """stalled -- accepted, cached, no money."""
    invoice = await _make_invoice(client, db_session)
    resp = await client.post(
        _URL,
        json=_event(invoice, status="stalled"),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == WebhookOutcome.STATUS_CACHED.value
    assert await _payments_of(db_session, invoice.user_id) == []
    await db_session.refresh(invoice)
    assert invoice.status == "stalled"


@pytest.mark.asyncio
async def test_unknown_status_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """WRONG-SHAPE AXIS ON THE BODY: a fifth status.

    422 rather than a silently accepted 200: a status this receiver does
    not know means it and the service disagree about the vocabulary,
    and that deserves a failed row somebody looks at.
    """
    invoice = await _make_invoice(client, db_session)
    resp = await client.post(
        _URL,
        json=_event(invoice, status="awaiting_confirmations"),
        headers={"X-Payments-Secret": configured_secret},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# product_ref: the three axes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_product_ref_is_accepted_without_crediting(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """WRONG-SHAPE AXIS ON product_ref: a valid uuid matching no row.

    200 on purpose. No retry can make a row appear that was never
    written -- the likely cause is a creation call that timed out after
    the service had already committed -- and spending the delivery
    budget on it would end with an outbox row in `failed` for an event
    nobody could ever have processed.

    The event is still RECORDED, so re-deliveries stop being reprocessed
    and the case is findable with a query rather than a log search.
    """
    orphan_ref = uuid4()
    orphan_invoice_id = uuid4()

    resp = await client.post(
        _URL,
        json={
            "invoice_id": str(orphan_invoice_id),
            "product_ref": str(orphan_ref),
            "status": "confirmed",
            "credited_amount_cents": 5000,
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers={"X-Payments-Secret": configured_secret},
    )

    assert resp.status_code == 200
    assert resp.json()["outcome"] == WebhookOutcome.NO_INVOICE.value

    result = await db_session.execute(
        select(CryptoWebhookEvent).where(
            CryptoWebhookEvent.invoice_id == orphan_invoice_id
        )
    )
    row = result.scalar_one()
    assert row.outcome == WebhookOutcome.NO_INVOICE.value
    assert row.payment_id is None


@pytest.mark.asyncio
async def test_unknown_product_ref_is_deduplicated_too(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """REPEAT AXIS ON product_ref, for the unresolvable case.

    Without a recorded row, every re-delivery of an event for an unknown
    product_ref would be reprocessed for as long as the service kept
    trying.
    """
    body = {
        "invoice_id": str(uuid4()),
        "product_ref": str(uuid4()),
        "status": "stalled",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    headers = {"X-Payments-Secret": configured_secret}

    first = await client.post(_URL, json=body, headers=headers)
    second = await client.post(_URL, json=body, headers=headers)

    assert first.json()["outcome"] == WebhookOutcome.NO_INVOICE.value
    assert second.json()["outcome"] == "duplicate"


@pytest.mark.asyncio
async def test_missing_and_malformed_product_ref_are_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """EMPTINESS AND WRONG-SHAPE AXES ON product_ref.

    Absent, empty string and non-uuid are all schema failures. They are
    422 because a body missing its routing key is not one this receiver
    can act on at all.
    """
    invoice = await _make_invoice(client, db_session)
    headers = {"X-Payments-Secret": configured_secret}
    base = _event(invoice, credited_amount_cents=100)

    no_key = {k: v for k, v in base.items() if k != "product_ref"}
    empty = {**base, "product_ref": ""}
    not_a_uuid = {**base, "product_ref": "not-a-uuid"}
    null_ref = {**base, "product_ref": None}

    for body in (no_key, empty, not_a_uuid, null_ref):
        resp = await client.post(_URL, json=body, headers=headers)
        assert resp.status_code == 422, body

    assert await _payments_of(db_session, invoice.user_id) == []


@pytest.mark.asyncio
async def test_event_whose_invoice_id_contradicts_the_row_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """The two identifiers in one body must agree.

    product_ref resolves to a row that was issued for a DIFFERENT
    service invoice: one of the two fields is wrong and there is no safe
    way to pick. Crediting on the strength of whichever we trusted more
    would move money on a body known to be inconsistent.
    """
    invoice = await _make_invoice(client, db_session)
    body = _event(invoice, credited_amount_cents=20000)
    body["invoice_id"] = str(uuid4())

    resp = await client.post(
        _URL, json=body, headers={"X-Payments-Secret": configured_secret}
    )

    assert resp.status_code == 422
    assert await _payments_of(db_session, invoice.user_id) == []


# ---------------------------------------------------------------------------
# Body: emptiness and wrong shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_and_malformed_bodies_are_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """EMPTINESS AXIS ON THE BODY.

    An empty object, and a body missing each required key in turn.
    """
    invoice = await _make_invoice(client, db_session)
    headers = {"X-Payments-Secret": configured_secret}
    base = _event(invoice, credited_amount_cents=100)

    bodies: list[dict[str, object]] = [{}]
    for key in ("invoice_id", "status", "occurred_at"):
        bodies.append({k: v for k, v in base.items() if k != key})

    for body in bodies:
        resp = await client.post(_URL, json=body, headers=headers)
        assert resp.status_code == 422, body


@pytest.mark.asyncio
async def test_wrong_types_are_refused_and_unknown_keys_are_ignored(
    client: AsyncClient,
    db_session: AsyncSession,
    configured_secret: str,
) -> None:
    """WRONG-SHAPE AXIS ON THE BODY, both directions.

    A wrongly-typed known key is a refusal. An UNKNOWN key is not: the
    service may add a field, and a receiver that answered 422 to an
    unrecognised one would stop processing every event on the day that
    happened -- taking the money behind them with it.
    """
    invoice = await _make_invoice(client, db_session)
    headers = {"X-Payments-Secret": configured_secret}

    bad_amount = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents="a lot"),
        headers=headers,
    )
    bad_time = await client.post(
        _URL,
        json=_event(invoice, credited_amount_cents=100, occurred_at="yesterday"),
        headers=headers,
    )
    assert bad_amount.status_code == 422
    assert bad_time.status_code == 422

    with_extra = await client.post(
        _URL,
        json=_event(
            invoice,
            credited_amount_cents=7000,
            some_future_field="the service added this",
        ),
        headers=headers,
    )
    assert with_extra.status_code == 200
    assert with_extra.json()["outcome"] == WebhookOutcome.CREDITED.value
