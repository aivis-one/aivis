# =============================================================================
# AIVIS.ONE Backend -- Crypto deposit invoice tests (H7)
# =============================================================================
#
# THIS FILE REPLACES test_crypto_deposits.py IN PLACE, by rename rather
# than by deletion, because three of its tests survived the contour they
# were written against. What did not survive: the stub deposit address
# (there is no per-user address any more) and the stub webhook (removed
# with it -- the receiver for the real service is H8). Those are not
# weakened here, they are gone, and what replaced them is asserted
# below instead.
#
# WHAT IS COVERED:
#   1:  the retired surfaces are actually retired -- and the new ones
#       exist, which is the pair that makes "X is gone" meaningful
#   2:  amount validation, all three axes
#   3:  ownership: another user's invoice is 404, not 403
#   4:  no payments service configured -> 503, never a 500
#   5:  the client's handling of every service outcome, by axis
#   6:  payment history and get_payment (carried over, rebuilt without
#       the webhook that used to create their fixtures)
#
# httpx is faked at the module boundary (app.core.payments_client.httpx)
# following test_comms_client.py: what is under test is behaviour per
# outcome, and the outcomes include ones a live service cannot be asked
# for on demand.
#
# NOT COVERED HERE, AND SAID OUT LOUD RATHER THAN IMPLIED: no test in
# this file drives a real payments service. The full suite was not run
# by the author either (it needs Postgres and MinIO). See the delivery
# report.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import payments_client
from app.core.config import settings
from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.models import CryptoInvoice, Payment
from app.modules.payments.service import get_payment
from tests.helpers import auth_headers, register_user

_NETWORK = "USDT-TRC20"
_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


async def _create_user(client: AsyncClient) -> tuple[str, str]:
    """Register a user, return (user_id, session_token)."""
    data = await register_user(client)
    return data["user"]["id"], data["session_token"]


def _make_payment(user_id: UUID) -> Payment:
    """A Payment row built directly.

    THE WEBHOOK USED TO BUILD THESE AND NO LONGER EXISTS. Constructing
    the row is what test_payment_confirmation.py already does, so this
    follows the sibling rather than inventing a third way.
    """
    return Payment(
        user_id=user_id,
        amount_cents=20000,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider="crypto_usdt_trc20",
        status=PaymentStatus.FROZEN,
        provider_data={"tx_hash": f"0x_h7_{uuid4().hex[:8]}"},
    )


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self, status_code: int, body: object = None, *, raw: str | None = None
    ):
        self.status_code = status_code
        self._body = body
        self.text = raw if raw is not None else ""
        self._raw = raw

    def json(self) -> object:
        if self._raw is not None:
            raise ValueError("not json")
        return self._body


class _FakeClient:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls: list[tuple[str, str, object]] = []

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def request(
        self, method: str, url: str, *, json: object = None, headers: object = None
    ) -> _FakeResponse:
        self.calls.append((method, url, json))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        if callable(self._outcome):
            return self._outcome(method, url, json)
        assert isinstance(self._outcome, _FakeResponse)
        return self._outcome


@pytest.fixture
def fake_payments(monkeypatch: pytest.MonkeyPatch):
    """Point the payments client at a fake transport and a fake address.

    The URL and token are set because payments_configured() gates every
    call on the URL: without it the client short-circuits and no fake
    would ever be reached.
    """

    def _install(outcome: object) -> _FakeClient:
        holder = _FakeClient(outcome)
        monkeypatch.setattr(settings, "payments_api_url", "http://payments.test")
        monkeypatch.setattr(settings, "payments_service_token", "h7-token")
        monkeypatch.setattr(
            payments_client.httpx, "AsyncClient", lambda **_: holder
        )
        return holder

    return _install


def _created_body(invoice_id: str | None = None, **overrides: object) -> dict:
    body = {
        "id": invoice_id or str(uuid4()),
        "network": _NETWORK,
        "address": _ADDRESS,
        "invoice_amount_cents": 10000,
        "status": "created",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# 1. The retired surfaces are retired, and the new ones exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retired_routes_are_gone_and_replaced(client: AsyncClient) -> None:
    """The stub deposit contour answers 404; the invoice contour does not.

    BOTH HALVES ON PURPOSE. "The old route is gone" passes just as
    happily when the whole router failed to load, when the app is
    broken, or when somebody deleted more than they meant to. Pairing it
    with "and the new one is reachable" is what makes the first half
    mean what it is supposed to mean.

    A 401 from the new routes is the pass condition: it proves the path
    is registered and guarded. Any 2xx here would mean an unauthenticated
    caller can open invoices.
    """
    gone = await client.post(
        "/api/v1/payments/crypto-address", json={"network": "TRC20"}
    )
    assert gone.status_code == 404

    webhook = await client.post("/api/v1/payments/crypto/webhook", json={})
    assert webhook.status_code == 404

    for method, path in (
        ("POST", "/api/v1/payments/invoices"),
        ("GET", f"/api/v1/payments/invoices/current?network={_NETWORK}"),
        ("GET", f"/api/v1/payments/invoices/{uuid4()}"),
        ("POST", f"/api/v1/payments/invoices/{uuid4()}/txid"),
    ):
        resp = await client.request(method, path, json={})
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"


@pytest.mark.asyncio
async def test_current_is_not_swallowed_by_the_parameterised_route(
    client: AsyncClient, fake_payments
) -> None:
    """/invoices/current resolves to its own route, not to /{invoice_id}.

    Route order is load-bearing and invisible: declared the other way
    round, FastAPI matches "current" as an invoice_id, fails to parse it
    as a UUID, and answers 422 -- a working endpoint made unreachable by
    a line's position. A 422 here is the failure this pins.
    """
    fake_payments(_FakeResponse(200, {}))
    _, token = await _create_user(client)

    resp = await client.get(
        f"/api/v1/payments/invoices/current?network={_NETWORK}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json() is None


# ---------------------------------------------------------------------------
# 2. Amount -- REPEAT / EMPTY / SHORTFALL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_amount_empty_and_short_are_refused_before_the_service(
    client: AsyncClient, fake_payments
) -> None:
    """Zero, negative and missing amounts never reach the wire.

    EMPTY and SHORTFALL on the amount input. The service floors the
    amount at one cent and would answer 422; refusing here is not a
    duplicate of its rule but the difference between a user reading
    "enter an amount" and a user reading a relayed schema error about a
    system they have never heard of.

    The fake records every call, so "did not reach the wire" is asserted
    rather than assumed.
    """
    wire = fake_payments(_FakeResponse(201, _created_body()))
    _, token = await _create_user(client)

    for body in (
        {"network": _NETWORK, "amount_cents": 0},
        {"network": _NETWORK, "amount_cents": -100},
        {"network": _NETWORK},
        {"amount_cents": 10000},
        {"network": "", "amount_cents": 10000},
    ):
        resp = await client.post(
            "/api/v1/payments/invoices", json=body, headers=auth_headers(token)
        )
        assert resp.status_code == 422, body

    assert wire.calls == []


@pytest.mark.asyncio
async def test_amount_above_the_ceiling_is_refused(
    client: AsyncClient, fake_payments
) -> None:
    """MAX_DEPOSIT_CENTS still bounds a deposit after the webhook died.

    The ceiling used to live on the webhook's amount field. Its only
    user was removed in this delivery, so without moving it the tree
    would have lost the guard while looking tidier.
    """
    wire = fake_payments(_FakeResponse(201, _created_body()))
    _, token = await _create_user(client)

    resp = await client.post(
        "/api/v1/payments/invoices",
        json={"network": _NETWORK, "amount_cents": 1_000_000_001},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert wire.calls == []


@pytest.mark.asyncio
async def test_second_create_returns_the_open_invoice_and_calls_once(
    client: AsyncClient, fake_payments
) -> None:
    """REPEAT on invoice creation: the second call opens nothing new.

    This is the whole of the idempotency narrowing. The service has no
    dedupe on product_ref, so a second POST would make a second invoice
    -- and a user paying the first would leave the product waiting on
    the second. What is pinned is that exactly one creation reaches the
    wire, not merely that the response looks the same.
    """
    invoice_id = str(uuid4())

    def _outcome(method: str, url: str, body: object) -> _FakeResponse:
        if method == "POST":
            return _FakeResponse(201, _created_body(invoice_id))
        return _FakeResponse(
            200,
            {
                "id": invoice_id,
                "status": "created",
                "network": _NETWORK,
                "address": _ADDRESS,
                "invoice_amount_cents": 10000,
                "attempts_remaining": 3,
            },
        )

    wire = fake_payments(_outcome)
    _, token = await _create_user(client)

    first = await client.post(
        "/api/v1/payments/invoices",
        json={"network": _NETWORK, "amount_cents": 10000},
        headers=auth_headers(token),
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/payments/invoices",
        json={"network": _NETWORK, "amount_cents": 55555},
        headers=auth_headers(token),
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    # The amount of the SECOND request is ignored: an open invoice has an
    # address and a deadline the user may already have acted on.
    assert second.json()["invoice_amount_cents"] == 10000

    creates = [c for c in wire.calls if c[0] == "POST"]
    assert len(creates) == 1


# ---------------------------------------------------------------------------
# 3. Ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_users_invoice_is_404_not_403(
    client: AsyncClient, db_session: AsyncSession, fake_payments
) -> None:
    """Someone else's invoice answers 404, and no service call is made.

    403 WOULD BE THE DEFECT, NOT A STYLE CHOICE: it confirms the id
    exists, which is the entire prize for anyone walking the id space.
    The absence of a wire call also matters -- a lookup that reached the
    service before checking ownership would leak existence through
    timing even while answering 404.
    """
    wire = fake_payments(_FakeResponse(200, {}))

    owner_id, _ = await _create_user(client)
    _, intruder_token = await _create_user(client)

    invoice = CryptoInvoice(
        user_id=UUID(owner_id),
        service_invoice_id=uuid4(),
        network=_NETWORK,
        address=_ADDRESS,
        invoice_amount_cents=10000,
        status="created",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(invoice)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/payments/invoices/{invoice.id}",
        headers=auth_headers(intruder_token),
    )
    assert resp.status_code == 404
    assert wire.calls == []

    await db_session.delete(invoice)
    await db_session.commit()


# ---------------------------------------------------------------------------
# 4. No payments service configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unconfigured_service_is_503_not_500(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty PAYMENTS_API_URL refuses cleanly.

    THIS IS THE PRODUCTION STATE UNTIL THE DEPLOY HAND-OVER LANDS, not
    an edge case: the service generates the token on its first install
    pass and cannot do that yet, so every box has an empty URL. A 500
    here would put an unhandled exception on the normal path of every
    deployment.
    """
    monkeypatch.setattr(settings, "payments_api_url", "")
    monkeypatch.setattr(settings, "payments_service_token", "")
    _, token = await _create_user(client)

    resp = await client.post(
        "/api/v1/payments/invoices",
        json={"network": _NETWORK, "amount_cents": 10000},
        headers=auth_headers(token),
    )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 5. The client, outcome by outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_is_distinguishable_from_down(
    fake_payments,
) -> None:
    """A timeout raises the subclass, a refused connection does not.

    They are told apart for one reason and it is not tidiness: a
    creating call that timed out may have left an invoice behind in the
    service, and a call that never connected cannot have. A caller that
    could not tell them apart could not decide whether retrying is safe.
    """
    import httpx as _httpx

    fake_payments(_httpx.ConnectTimeout("slow"))
    with pytest.raises(payments_client.PaymentsTimeoutError):
        await payments_client.create_invoice(
            product_ref=str(uuid4()), network=_NETWORK, invoice_amount_cents=10000
        )

    fake_payments(_httpx.ConnectError("down"))
    with pytest.raises(payments_client.PaymentsUnavailableError) as caught:
        await payments_client.create_invoice(
            product_ref=str(uuid4()), network=_NETWORK, invoice_amount_cents=10000
        )
    assert not isinstance(caught.value, payments_client.PaymentsTimeoutError)


@pytest.mark.asyncio
async def test_empty_and_incomplete_bodies_are_refused(fake_payments) -> None:
    """EMPTY and SHORTFALL on the service's own answer.

    A 201 carrying address="" passes a presence check and then puts an
    empty string on a payment screen -- the same class of defect this
    delivery exists to remove, a deposit surface that looks like it
    works. So emptiness is tested against None and "" rather than by
    key presence.

    Zero is deliberately NOT treated as empty: it is a legitimate value
    elsewhere in this contract (a dust transfer credits zero), and a
    falsiness check would have quietly rejected it.
    """
    for body in (
        {},
        _created_body(address=""),
        _created_body(address=None),
        {k: v for k, v in _created_body().items() if k != "expires_at"},
        {k: v for k, v in _created_body().items() if k != "id"},
    ):
        fake_payments(_FakeResponse(201, body))
        with pytest.raises(payments_client.PaymentsMalformedError):
            await payments_client.create_invoice(
                product_ref=str(uuid4()),
                network=_NETWORK,
                invoice_amount_cents=10000,
            )


@pytest.mark.asyncio
async def test_non_object_and_non_json_bodies_are_refused(fake_payments) -> None:
    """A list parses as JSON and is still not an answer.

    "It was JSON" is not "it was the object we asked for", and the two
    were checked separately because a list reaches `.get` and raises an
    AttributeError rather than a typed refusal.
    """
    fake_payments(_FakeResponse(201, ["not", "an", "object"]))
    with pytest.raises(payments_client.PaymentsMalformedError):
        await payments_client.get_invoice(uuid4())

    fake_payments(_FakeResponse(200, None, raw="<html>gateway</html>"))
    with pytest.raises(payments_client.PaymentsMalformedError):
        await payments_client.get_invoice(uuid4())


@pytest.mark.asyncio
async def test_service_refusals_keep_their_error_code(fake_payments) -> None:
    """The five 409 codes and the 400 arrive intact.

    The code is the only thing that says WHY, and the five refusals have
    genuinely different meanings to a user -- "somebody already claimed
    this slot" is not "your invoice expired". Collapsing them into one
    "rejected" would make the screen unable to say anything useful.
    """
    for status_code, code in (
        (409, "slot_occupied"),
        (409, "attempts_exhausted"),
        (409, "invoice_already_confirmed"),
        (409, "invoice_expired"),
        (409, "invoice_stalled"),
        (400, "network_not_supported"),
    ):
        fake_payments(_FakeResponse(status_code, {"error": code}))
        with pytest.raises(payments_client.PaymentsRejectedError) as caught:
            await payments_client.submit_txid(uuid4(), "0x" + "a" * 64)
        assert caught.value.error_code == code
        assert caught.value.status_code == status_code


@pytest.mark.asyncio
async def test_unauthorized_is_never_relayed_as_the_users_problem(
    fake_payments,
) -> None:
    """401/403 from the service becomes "unavailable", not "unauthorized".

    A wrong or empty service token fails every call identically and is a
    fact about this deployment. Relaying it would tell a user their
    session is broken and send them to log in again, repeatedly, over a
    misconfiguration they cannot touch.
    """
    for status_code in (401, 403):
        fake_payments(_FakeResponse(status_code, {"error": "unauthorized"}))
        with pytest.raises(payments_client.PaymentsUnavailableError) as caught:
            await payments_client.get_invoice(uuid4())
        assert not isinstance(caught.value, payments_client.PaymentsRejectedError)


@pytest.mark.asyncio
async def test_txid_repeat_and_empty_reach_the_service_unchanged(
    fake_payments,
) -> None:
    """REPEAT and EMPTY on the user's TXID.

    An empty hash is NOT a schema error and is not stopped by the
    client: the service answers 200 with result_code=invalid_format and
    spends no attempt, and turning that into a local refusal would cost
    the user the explanation that comes with it. The view stops an
    empty field before this layer, which is a different decision made in
    a different place for a different reason.

    A repeated hash is likewise handed over unchanged: repeating one's
    own TXID is an idempotent replay at the service, not a refusal, and
    a client-side guard would turn a legitimate retry into an error.
    """
    body = {
        "status": "created",
        "result_code": "invalid_format",
        "attempts_used": 0,
        "attempts_remaining": 3,
    }
    wire = fake_payments(_FakeResponse(200, body))

    first = await payments_client.submit_txid(uuid4(), "")
    second = await payments_client.submit_txid(uuid4(), "")

    assert first["result_code"] == "invalid_format"
    # The counter is untouched by a malformed hash. Asserted because a
    # screen that decremented here would show a budget the user has not
    # spent.
    assert first["attempts_remaining"] == 3
    assert second == first
    assert len(wire.calls) == 2


@pytest.mark.asyncio
async def test_txid_is_stripped_but_not_otherwise_judged(
    client: AsyncClient, db_session: AsyncSession, fake_payments
) -> None:
    """Surrounding whitespace goes; the hash itself is untouched.

    A hash pasted from a block explorer routinely arrives with a
    trailing newline, and the service would rightly call that malformed
    -- costing nothing but confusing everyone. Anything beyond stripping
    would be this product forming an opinion about a format the service
    owns, which is the service's to hold.

    Driven through the real route against a real row rather than by
    patching the module's own lookup: a test that replaces the function
    under the one it is testing proves the stripping happens somewhere,
    not that it happens on the path a user takes.
    """
    wire = fake_payments(
        _FakeResponse(
            200,
            {
                "status": "awaiting_confirmations",
                "result_code": "matched",
                "attempts_used": 1,
                "attempts_remaining": 2,
            },
        )
    )
    user_id, token = await _create_user(client)

    invoice = CryptoInvoice(
        user_id=UUID(user_id),
        service_invoice_id=uuid4(),
        network=_NETWORK,
        address=_ADDRESS,
        invoice_amount_cents=10000,
        status="created",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(invoice)
    await db_session.commit()

    hash_value = "0x" + "b" * 64
    resp = await client.post(
        f"/api/v1/payments/invoices/{invoice.id}/txid",
        json={"txid": f"  {hash_value}\n"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["result_code"] == "matched"
    # The counter comes back from the service, not from counting here.
    assert resp.json()["attempts_remaining"] == 2

    submitted = [c for c in wire.calls if c[0] == "POST"]
    assert submitted[-1][2] == {"txid": hash_value}

    await db_session.delete(invoice)
    await db_session.commit()


# ---------------------------------------------------------------------------
# 6. Payment history and get_payment -- carried over
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_payment_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payment history -> 200, contains the payment we created.

    CARRIED OVER FROM test_crypto_deposits.py AND REBUILT. The old
    version made its fixture by calling the stub webhook, which no
    longer exists; the assertion about history was never about the
    webhook and stays exactly as strong. The Payment row is now built
    directly, as test_payment_confirmation.py already does.
    """
    user_id, token = await _create_user(client)

    payment = _make_payment(UUID(user_id))
    db_session.add(payment)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/payments/history", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["total"] == 1
    assert body["page"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["amount_cents"] == 20000
    assert body["items"][0]["status"] == "frozen"

    await db_session.delete(payment)
    await db_session.commit()


@pytest.mark.asyncio
async def test_payment_history_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payment history for a user with no payments -> 200, empty."""
    _, token = await _create_user(client)

    resp = await client.get(
        "/api/v1/payments/history", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_get_payment_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """get_payment() returns the correct payment by ID.

    Carried over for the same reason as the history test: it asserts
    something about get_payment, and only its fixture depended on the
    removed webhook.
    """
    user_id, _ = await _create_user(client)

    payment = _make_payment(UUID(user_id))
    db_session.add(payment)
    await db_session.commit()

    loaded = await get_payment(payment.id, db_session)

    assert loaded.id == payment.id
    assert loaded.amount_cents == 20000
    assert loaded.status == PaymentStatus.FROZEN

    await db_session.delete(payment)
    await db_session.commit()
