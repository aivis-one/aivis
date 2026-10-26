# =============================================================================
# AIVIS.ONE Backend -- Crypto invoices: the client's manual-confirmation
# request and the administrator's notes (DB-free)
# =============================================================================
#
# Checks the routes and guards, the note schema, the SQL of the open-request
# filter and count, the request's rules and the notes' writes against a fake
# session, and how the staff list marks a request, a reason and the notes.
# Run with:
#   pytest --noconftest tests/test_crypto_invoice_manual_requests.py
# The DB-backed half is test_crypto_invoice_manual_requests_db.py.
# =============================================================================

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.payments import manual_confirm, manual_requests
from app.modules.payments.crypto_invoices_staff_router import router as staff_router
from app.modules.payments.router import router as client_router
from app.modules.payments.schemas import (
    AddInvoiceNoteRequest,
    InvoiceResponse,
    StaffInvoiceNote,
)

_AT = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def _sql(statement) -> str:  # type: ignore[no-untyped-def]
    return str(statement.compile(dialect=postgresql.dialect()))


def _route(router, method: str, path: str):  # type: ignore[no-untyped-def]
    for route in router.routes:
        if route.path == path and method in route.methods:
            return route
    raise AssertionError(f"{method} {path} is not routed")


def _dependency_names(route) -> list[str]:  # type: ignore[no-untyped-def]
    names = []
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        names.append(getattr(dep.call, "__name__", ""))
        stack.extend(dep.dependencies)
    return names


# --- routes and guards --------------------------------------------------------


def test_the_client_route_takes_the_owner_and_refuses_avatar_mode() -> None:
    route = _route(
        client_router, "POST", "/api/v1/payments/invoices/{invoice_id}/manual-request"
    )
    names = _dependency_names(route)
    assert "get_current_user_write" in names
    assert "_forbid_avatar" in names or any("avatar" in n for n in names)


def test_the_notes_route_has_the_confirmations_guard() -> None:
    route = _route(
        staff_router, "POST", "/api/v1/staff/crypto-invoices/{invoice_id}/notes"
    )
    names = [d.call.__name__ for d in route.dependant.dependencies]
    assert "require_financial_operations" in names
    from app.modules.payments import crypto_invoices_staff_router as mod

    src = inspect.getsource(mod.add_crypto_invoice_note_endpoint)
    assert src.index("require_admin(staff, session)") < src.index("add_note(")


def test_the_list_takes_the_open_request_filter() -> None:
    route = _route(staff_router, "GET", "/api/v1/staff/crypto-invoices")
    names = {p.name for p in route.dependant.query_params}
    assert "open_request" in names


def test_the_client_invoice_carries_no_staff_field() -> None:
    fields = set(InvoiceResponse.model_fields)
    assert {"manual_requested_at", "manually_credited"} <= fields
    assert not fields & {"notes", "confirm_reason"}


# --- the note's body ------------------------------------------------------------


def test_note_text_is_three_to_five_hundred() -> None:
    with pytest.raises(ValidationError):
        AddInvoiceNoteRequest()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        AddInvoiceNoteRequest(text="ab")
    with pytest.raises(ValidationError):
        AddInvoiceNoteRequest(text="  a  ")
    with pytest.raises(ValidationError):
        AddInvoiceNoteRequest(text="x" * 501)
    assert AddInvoiceNoteRequest(text=" called him ").text == "called him"


# --- the SQL of the filter and the count -------------------------------------------


def test_open_request_filter_reads_the_audit_log_and_excludes_credited() -> None:
    (cond,) = manual_confirm.build_invoice_filters(open_request=True)
    sql = _sql(manual_confirm.build_list_statement([cond], page=1, per_page=20))
    assert "audit_log.event" in sql
    assert "audit_log.target_id = crypto_invoices.id" in sql
    assert "AND NOT ((EXISTS" in sql
    assert "crypto_webhook_events" in sql
    assert manual_confirm.build_invoice_filters(open_request=False) == []


def test_the_count_is_over_crypto_invoices_with_an_open_request() -> None:
    src = inspect.getsource(manual_requests.count_open_requests)
    assert "open_request_condition()" in src
    stmt = (
        manual_requests.select(manual_requests.func.count())
        .select_from(manual_requests.CryptoInvoice)
        .where(manual_requests.open_request_condition())
    )
    sql = _sql(stmt)
    assert "FROM crypto_invoices" in sql and "audit_log" in sql


# --- the request and the notes, on a fake session -----------------------------------


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        return self._value

    def all(self) -> Any:
        return self._value


class _FakeSession:
    """Answers each execute with the next prepared value."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.statements: list[str] = []

    async def execute(self, stmt: Any) -> _Result:
        self.statements.append(_sql(stmt))
        return _Result(self.answers.pop(0))

    async def refresh(self, obj: Any, attribute_names: Any = None) -> None:
        obj.created_at = _AT


def _invoice(status: str = "created") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        service_invoice_id=uuid4(),
        network="USDT-TRC20",
        invoice_amount_cents=12345,
        status=status,
    )


@pytest.fixture
def audits(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def audit(**kw: Any) -> SimpleNamespace:
        calls.append(kw)
        return SimpleNamespace(
            id=uuid4(), actor_id=kw["actor_id"], data=kw["data"], created_at=None
        )

    monkeypatch.setattr(manual_requests, "record_audit", audit)
    return calls


async def test_a_request_is_written_once_with_amount_and_network(
    audits: list[dict[str, Any]],
) -> None:
    invoice = _invoice()
    # the invoice, not credited, no request yet
    session = _FakeSession(invoice, False, [])
    result = await manual_requests.request_manual_confirmation(
        invoice.id,
        invoice.user_id,
        session,  # type: ignore[arg-type]
    )
    assert result.already_requested is False
    assert result.requested_at == _AT
    (audit,) = audits
    assert audit["event"] == "deposit.manual_requested"
    assert audit["target_type"] == "crypto_invoice"
    assert audit["target_id"] == invoice.id
    assert audit["actor_id"] == invoice.user_id
    assert audit["data"]["amount_cents"] == 12345
    assert audit["data"]["network"] == "USDT-TRC20"
    # the owner is in the WHERE clause, and the row is locked
    assert "crypto_invoices.user_id =" in session.statements[0]
    assert "FOR UPDATE" in session.statements[0]


async def test_a_repeat_returns_the_existing_request_and_writes_nothing(
    audits: list[dict[str, Any]],
) -> None:
    invoice = _invoice()
    session = _FakeSession(invoice, False, [(invoice.id, _AT)])
    result = await manual_requests.request_manual_confirmation(
        invoice.id,
        invoice.user_id,
        session,  # type: ignore[arg-type]
    )
    assert result.already_requested is True
    assert result.requested_at == _AT
    assert audits == []


async def test_a_credited_invoice_is_409(audits: list[dict[str, Any]]) -> None:
    invoice = _invoice()
    with pytest.raises(ConflictError) as exc:
        await manual_requests.request_manual_confirmation(
            invoice.id,
            invoice.user_id,
            _FakeSession(invoice, True),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409
    assert audits == []


async def test_an_expired_invoice_may_still_be_requested(
    audits: list[dict[str, Any]],
) -> None:
    invoice = _invoice(status="expired")
    result = await manual_requests.request_manual_confirmation(
        invoice.id,
        invoice.user_id,
        _FakeSession(invoice, False, []),  # type: ignore[arg-type]
    )
    assert result.already_requested is False
    assert len(audits) == 1


async def test_somebody_elses_or_no_invoice_is_404(
    audits: list[dict[str, Any]],
) -> None:
    with pytest.raises(NotFoundError):
        await manual_requests.request_manual_confirmation(
            uuid4(),
            uuid4(),
            _FakeSession(None),  # type: ignore[arg-type]
        )
    assert audits == []


async def test_a_note_is_an_audit_event_by_the_staff_member(
    audits: list[dict[str, Any]],
) -> None:
    invoice_id = uuid4()
    staff = SimpleNamespace(
        id=uuid4(), email="admin@example.com", profile={"first_name": "Ann"}
    )
    note = await manual_requests.add_note(
        invoice_id,
        staff,
        "called the client",
        _FakeSession(invoice_id),  # type: ignore[arg-type]
    )
    (audit,) = audits
    assert audit["event"] == "deposit.manual_note"
    assert audit["actor_type"] == "staff"
    assert audit["actor_id"] == staff.id
    assert audit["target_id"] == invoice_id
    assert audit["data"] == {"text": "called the client"}
    assert note.text == "called the client"
    assert note.author_name == "Ann"
    assert note.created_at == _AT


async def test_a_note_on_no_invoice_is_404(audits: list[dict[str, Any]]) -> None:
    staff = SimpleNamespace(id=uuid4(), email="a@example.com", profile={})
    with pytest.raises(NotFoundError):
        await manual_requests.add_note(uuid4(), staff, "text", _FakeSession(None))  # type: ignore[arg-type]
    assert audits == []


# --- the staff list's marks ----------------------------------------------------------


async def test_the_list_marks_open_requests_reasons_and_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_open = _invoice()
    requested_paid = _invoice()
    plain = _invoice()
    user = SimpleNamespace(email="ada@example.com", profile={})
    payment_id = uuid4()
    note = StaffInvoiceNote(
        id=uuid4(), text="checked", author_id=uuid4(), author_name="Ann", created_at=_AT
    )

    async def credited(_s, _ids):  # type: ignore[no-untyped-def]
        return {requested_paid.service_invoice_id: ("manual", payment_id)}

    async def requested(_s, _ids):  # type: ignore[no-untyped-def]
        return {requested_open.id: _AT, requested_paid.id: _AT}

    async def notes(_s, _ids):  # type: ignore[no-untyped-def]
        return {requested_open.id: [note]}

    async def reasons(_s, ids):  # type: ignore[no-untyped-def]
        assert ids == [payment_id]
        return {payment_id: "paid by bank"}

    monkeypatch.setattr(manual_confirm, "credited_map", credited)
    monkeypatch.setattr(manual_confirm, "requested_at_map", requested)
    monkeypatch.setattr(manual_confirm, "notes_map", notes)
    monkeypatch.setattr(manual_confirm, "confirm_reason_map", reasons)
    for inv in (requested_open, requested_paid, plain):
        inv.created_at = _AT
        inv.expires_at = _AT
    session = _FakeSession(
        3, [(requested_open, user), (requested_paid, user), (plain, user)]
    )
    items, total = await manual_confirm.list_crypto_invoices(session)  # type: ignore[arg-type]
    assert total == 3
    by_id = {item.id: item for item in items}

    first = by_id[requested_open.id]
    assert first.manual_requested_at == _AT and first.manual_request_open is True
    assert first.notes == [note] and first.confirm_reason is None

    second = by_id[requested_paid.id]
    assert second.manual_request_open is False
    assert second.confirm_reason == "paid by bank"

    third = by_id[plain.id]
    assert third.manual_requested_at is None and third.manual_request_open is False
    assert third.notes == []


async def test_manual_state_tells_a_hand_credit_from_a_service_one() -> None:
    invoice = _invoice()
    by_hand = await manual_requests.manual_state(
        _FakeSession([(invoice.id, _AT)], [({"manual": True},)]),
        invoice,  # type: ignore[arg-type]
    )
    assert by_hand == (_AT, True)
    by_service = await manual_requests.manual_state(
        _FakeSession([], [({"service_invoice_id": "x"},)]),
        invoice,  # type: ignore[arg-type]
    )
    assert by_service == (None, False)
