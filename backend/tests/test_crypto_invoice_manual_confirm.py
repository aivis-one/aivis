# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices: manual confirmation (DB-free)
# =============================================================================
#
# Checks the list query, the filters, the routes and guards, the request
# schema and the confirmation's writes and refusals against a fake session.
# Run with:
#   pytest --noconftest tests/test_crypto_invoice_manual_confirm.py
# =============================================================================

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.constants import LedgerReason
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.payments import manual_confirm
from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.crypto_invoices_staff_router import router
from app.modules.payments.schemas import ConfirmCryptoInvoiceRequest


def _sql(statement) -> str:  # type: ignore[no-untyped-def]
    return str(statement.compile(dialect=postgresql.dialect()))


# --- the list query -----------------------------------------------------------


def test_filters_add_one_condition_each() -> None:
    assert manual_confirm.build_invoice_filters() == []
    both = manual_confirm.build_invoice_filters(user_id=uuid4(), status="created")
    assert len(both) == 2
    sql = _sql(manual_confirm.build_list_statement(both, page=1, per_page=20))
    assert "crypto_invoices.user_id =" in sql
    assert "crypto_invoices.status =" in sql


def test_statement_is_newest_first_paged_and_joins_the_user() -> None:
    stmt = manual_confirm.build_list_statement([], page=3, per_page=25)
    sql = _sql(stmt)
    assert "ORDER BY crypto_invoices.created_at DESC" in sql
    assert "JOIN users" in sql
    params = stmt.compile(dialect=postgresql.dialect()).params.values()
    assert 50 in params and 25 in params


def test_user_name_and_manual_mark() -> None:
    assert (
        manual_confirm.user_name({"first_name": "Ann", "last_name": "Lee"})
        == "Ann Lee"
    )
    assert manual_confirm.user_name(None) is None
    assert manual_confirm.is_manual({"manual": True}) is True
    assert manual_confirm.is_manual({"manual": "true"}) is False
    assert manual_confirm.is_manual(None) is False


# --- routes and guards --------------------------------------------------------


def _route(method: str, path: str):  # type: ignore[no-untyped-def]
    for route in router.routes:
        if route.path == path and method in route.methods:
            return route
    raise AssertionError(f"{method} {path} is not routed")


def test_both_routes_exist_with_the_financial_operations_guard() -> None:
    for method, path in (
        ("GET", "/api/v1/staff/crypto-invoices"),
        ("POST", "/api/v1/staff/crypto-invoices/{invoice_id}/confirm"),
    ):
        route = _route(method, path)
        names = [d.call.__name__ for d in route.dependant.dependencies]
        assert "require_financial_operations" in names


def test_list_filters_are_user_id_status_and_paging() -> None:
    route = _route("GET", "/api/v1/staff/crypto-invoices")
    names = {p.name for p in route.dependant.query_params}
    assert {"user_id", "invoice_status", "page", "per_page"} <= names
    status_param = next(
        p for p in route.dependant.query_params if p.name == "invoice_status"
    )
    assert status_param.field_info.alias == "status"


def test_admin_check_runs_before_any_work_in_both_endpoints() -> None:
    from app.modules.payments import crypto_invoices_staff_router as mod

    confirm_src = inspect.getsource(mod.confirm_crypto_invoice_endpoint)
    assert confirm_src.index("require_admin(staff, session)") < confirm_src.index(
        "confirm_crypto_invoice("
    )
    list_src = inspect.getsource(mod.list_crypto_invoices_endpoint)
    assert list_src.index("require_admin(staff, session)") < list_src.index(
        "list_crypto_invoices("
    )


# --- the request --------------------------------------------------------------


def test_reason_is_required_three_to_five_hundred() -> None:
    with pytest.raises(ValidationError):
        ConfirmCryptoInvoiceRequest()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ConfirmCryptoInvoiceRequest(reason="ab")
    with pytest.raises(ValidationError):
        ConfirmCryptoInvoiceRequest(reason="  a  ")
    with pytest.raises(ValidationError):
        ConfirmCryptoInvoiceRequest(reason="x" * 501)
    assert ConfirmCryptoInvoiceRequest(reason=" paid by bank ").reason == "paid by bank"
    assert len(ConfirmCryptoInvoiceRequest(reason="x" * 500).reason) == 500


# --- the confirmation, on a fake session ----------------------------------------


class _Result:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeSession:
    def __init__(self, invoice: object) -> None:
        self.invoice = invoice
        self.added: list[object] = []

    async def execute(self, _stmt: object) -> _Result:
        return _Result(self.invoice)

    def add(self, obj: object) -> None:
        obj.id = uuid4()  # type: ignore[attr-defined]
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _invoice() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        service_invoice_id=uuid4(),
        network="USDT-TRC20",
        invoice_amount_cents=12345,
        status="expired",
    )


@pytest.fixture
def writes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    calls: dict[str, list] = {"ledger": [], "txn": [], "audit": [], "events": []}

    async def ledger(session, **kw):  # type: ignore[no-untyped-def]
        calls["ledger"].append(kw)

    async def txn(session, **kw):  # type: ignore[no-untyped-def]
        calls["txn"].append(kw)

    async def audit(**kw):  # type: ignore[no-untyped-def]
        calls["audit"].append(kw)

    async def event(session, event_type, data):  # type: ignore[no-untyped-def]
        calls["events"].append(data)

    monkeypatch.setattr(manual_confirm, "record_active_ledger", ledger)
    monkeypatch.setattr(manual_confirm, "record_transaction", txn)
    monkeypatch.setattr(manual_confirm, "record_audit", audit)
    monkeypatch.setattr(manual_confirm, "emit_event", event)
    monkeypatch.setattr(manual_confirm, "comms_configured", lambda: True)
    return calls


async def test_confirm_writes_a_confirmed_payment_ledger_history_audit(
    monkeypatch: pytest.MonkeyPatch, writes: dict[str, list]
) -> None:
    async def none_credited(_s, _ids):  # type: ignore[no-untyped-def]
        return {}

    monkeypatch.setattr(manual_confirm, "credited_map", none_credited)
    invoice = _invoice()
    session = _FakeSession(invoice)
    staff_id = uuid4()

    payment = await manual_confirm.confirm_crypto_invoice(
        invoice.id, staff_id, "paid by bank", session  # type: ignore[arg-type]
    )

    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.payment_type == PaymentType.CRYPTO
    assert payment.provider == "manual"
    assert payment.amount_cents == 12345
    assert payment.frozen_until is None
    assert payment.provider_data["manual"] is True
    assert payment.provider_data["confirmed_by"] == str(staff_id)
    assert payment.provider_data["reason"] == "paid by bank"
    assert payment.provider_data["service_invoice_id"] == str(
        invoice.service_invoice_id
    )
    assert payment.provider_data["invoice_id"] == str(invoice.id)

    (ledger,) = writes["ledger"]
    assert ledger["status"] == "confirmed"
    assert ledger["amount_cents"] == 12345
    assert ledger["reason"] == LedgerReason.DEPOSIT_MANUAL.format(
        payment_id=payment.id
    )
    assert ledger["reason"].startswith("deposit:manual:")
    assert ledger["origin_payment_id"] == payment.id
    assert "frozen_until" not in ledger

    assert [t["type"] for t in writes["txn"]] == [
        "deposit:received",
        "deposit:confirmed",
    ]
    (audit,) = writes["audit"]
    assert audit["event"] == "payment.manual_confirmed"
    assert audit["target_id"] == payment.id
    assert audit["actor_id"] == staff_id
    assert writes["events"][0]["idempotency_key"] == f"deposit-confirmed:{payment.id}"
    # The cached status column is untouched.
    assert invoice.status == "expired"


@pytest.mark.parametrize("who", ["manual", "service"])
async def test_confirm_is_refused_when_the_invoice_is_already_credited(
    monkeypatch: pytest.MonkeyPatch, writes: dict[str, list], who: str
) -> None:
    invoice = _invoice()

    async def credited(_s, ids):  # type: ignore[no-untyped-def]
        return {invoice.service_invoice_id: (who, uuid4())}

    monkeypatch.setattr(manual_confirm, "credited_map", credited)
    session = _FakeSession(invoice)
    with pytest.raises(ConflictError) as exc:
        await manual_confirm.confirm_crypto_invoice(
            invoice.id, uuid4(), "again", session  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409
    assert session.added == []
    assert not any(writes.values())


async def test_confirm_of_an_unknown_invoice_is_404(
    writes: dict[str, list],
) -> None:
    with pytest.raises(NotFoundError):
        await manual_confirm.confirm_crypto_invoice(
            uuid4(), uuid4(), "none", _FakeSession(None)  # type: ignore[arg-type]
        )


def test_the_invoice_row_is_locked_for_the_check() -> None:
    src = inspect.getsource(manual_confirm.confirm_crypto_invoice)
    assert ".with_for_update()" in src
    assert src.index("with_for_update") < src.index("credited_map(")
