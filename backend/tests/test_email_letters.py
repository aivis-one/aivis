# =============================================================================
# AIVIS.ONE Backend -- e-mail letters: the variables each emitter sends
# =============================================================================
#
# comms renders an e-mail from comms-profile/templates/<locale>.yaml with
# str.format_map over the request's `action_data`. A template naming a
# variable the emitter did not send prints "{name}" in the letter, so what is
# pinned here is the emitter's side of that contract: the shared addresses
# (core/email_vars.py) and each type's own fields.
#
# No database and no network: emit_event is replaced by a recorder and the
# stubs carry only the attributes the emitters read. comms-profile/ is not in
# the test image (see test_comms_profile.py), so the templates' side of the
# contract is checked where the profile lives, by comms's own loader.
# =============================================================================

import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

import app
from app.core.config import settings
from app.core.email_vars import email_action_data
from app.modules.auth import service as auth_service
from app.modules.purchases import agreement_service, ownership_certificate_service
from app.modules.withdrawals import service as withdrawal_service
from app.modules.withdrawals.constants import WithdrawalStatus

_APP = Path(app.__file__).resolve().parent

SHARED = {"support_url", "support_email", "cabinet_url", "site_url", "logo_url"}

EMAIL_TYPES = {
    "auth.verification_code",
    "auth.password_reset",
    "auth.telegram_link_code",
    "auth.telegram_linked",
    "purchase.agreement",
    "ownership.certificate",
    "withdrawal.processing",
    "withdrawal.completed",
    "withdrawal.rejected",
    "withdrawal.failed",
    "installment.tranche_overdue",
    "installment.plan_defaulted",
}


class Recorder:
    """Stands in for emit_event: keeps every payload it is handed."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def __call__(
        self, session: Any, event_type: str, data: dict[str, Any]
    ) -> None:
        self.payloads.append(data)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    for module in (
        auth_service,
        agreement_service,
        ownership_certificate_service,
        withdrawal_service,
    ):
        monkeypatch.setattr(module, "emit_event", rec)
        monkeypatch.setattr(module, "comms_configured", lambda: True)
    return rec


def _assert_wire_safe(action_data: dict[str, Any]) -> None:
    """comms accepts scalars only as template variables."""
    assert set(action_data) >= SHARED
    for key, value in action_data.items():
        assert isinstance(value, (str, int, float, bool)), key


# ---------------------------------------------------------------------------
# The shared variables
# ---------------------------------------------------------------------------


def test_shared_addresses_come_from_the_frontend_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app/")
    data = email_action_data(code="123456")
    assert data["cabinet_url"] == "https://example.com/app"
    assert data["site_url"] == "https://example.com"
    assert data["logo_url"] == "https://example.com/email/logo.png"
    assert data["code"] == "123456"
    # nothing configured: the letter points at the site and at hello@ on its host
    monkeypatch.setattr(settings, "support_url", "")
    monkeypatch.setattr(settings, "telegram_bot_url", "")
    monkeypatch.setattr(settings, "support_email", "")
    data = email_action_data()
    assert data["support_url"] == "https://example.com"
    assert data["support_email"] == "hello@example.com"


def test_configured_support_addresses_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    monkeypatch.setattr(settings, "support_url", "https://t.example.org/bot")
    monkeypatch.setattr(settings, "support_email", "help@example.org")
    data = email_action_data()
    assert data["support_url"] == "https://t.example.org/bot"
    assert data["support_email"] == "help@example.org"


def test_support_url_falls_back_to_the_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    monkeypatch.setattr(settings, "support_url", "")
    monkeypatch.setattr(settings, "telegram_bot_url", "https://t.example.org/bot")
    assert email_action_data()["support_url"] == "https://t.example.org/bot"


def test_a_none_field_never_prints_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    assert email_action_data(reason=None)["reason"] == ""


def test_no_logo_without_a_site_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "")
    data = email_action_data()
    assert data["site_url"] == ""
    assert data["logo_url"] == ""


# ---------------------------------------------------------------------------
# The emitters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_code_sends_code_and_minutes(recorder: Recorder) -> None:
    await auth_service._request_verification_email(
        None,
        uuid4(),
        "482915",
        datetime.now(UTC),  # type: ignore[arg-type]
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == "auth.verification_code"
    _assert_wire_safe(payload["action_data"])
    assert payload["action_data"]["code"] == "482915"
    ttl = auth_service._VERIFICATION_CODE_TTL_MINUTES
    assert payload["action_data"]["minutes"] == ttl
    # the stored body stays as the fallback and keeps the code
    assert "482915" in payload["body"]


@pytest.mark.asyncio
async def test_telegram_link_code_sends_the_code_the_minutes_and_the_name(
    recorder: Recorder,
) -> None:
    await auth_service._request_telegram_link_code_email(
        None, uuid4(), "654321", datetime.now(UTC), "@alice"
    )
    payload = recorder.payloads[0]
    assert payload["type"] == "auth.telegram_link_code"
    data = payload["action_data"]
    _assert_wire_safe(data)
    assert data["code"] == "654321"
    assert data["minutes"] == 10
    assert data["telegram_name"] == "@alice"


@pytest.mark.asyncio
async def test_telegram_linked_notice_sends_the_name(recorder: Recorder) -> None:
    await auth_service._request_telegram_linked_email(None, uuid4(), "@alice")
    payload = recorder.payloads[0]
    assert payload["type"] == "auth.telegram_linked"
    _assert_wire_safe(payload["action_data"])
    assert payload["action_data"]["telegram_name"] == "@alice"


@pytest.mark.asyncio
async def test_password_reset_sends_the_link_and_minutes(recorder: Recorder) -> None:
    await auth_service._request_password_reset_email(
        None,
        uuid4(),
        "tok123",
        datetime.now(UTC),  # type: ignore[arg-type]
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == "auth.password_reset"
    _assert_wire_safe(payload["action_data"])
    assert payload["action_data"]["reset_url"] == (
        "https://example.com/app/password-reset/confirm?token=tok123"
    )
    ttl = auth_service._PASSWORD_RESET_TOKEN_TTL_MINUTES
    assert payload["action_data"]["minutes"] == ttl


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        WithdrawalStatus.PROCESSING,
        WithdrawalStatus.COMPLETED,
        WithdrawalStatus.REJECTED,
        WithdrawalStatus.FAILED,
    ],
)
async def test_withdrawal_sends_the_amount(
    recorder: Recorder, status: WithdrawalStatus
) -> None:
    withdrawal = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), amount_cents=25_000, status=status
    )
    await withdrawal_service._notify_withdrawal(
        None,
        withdrawal,
        reason="Wallet address is invalid",  # type: ignore[arg-type]
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == f"withdrawal.{status}"
    _assert_wire_safe(payload["action_data"])
    assert payload["action_data"]["amount"] == "250.00"
    assert payload["action_data"]["reason"] == "Wallet address is invalid"


@pytest.mark.asyncio
async def test_withdrawal_without_a_reason_sends_an_empty_one(
    recorder: Recorder,
) -> None:
    withdrawal = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        amount_cents=1_000,
        status=WithdrawalStatus.COMPLETED,
    )
    await withdrawal_service._notify_withdrawal(None, withdrawal)  # type: ignore[arg-type]
    assert recorder.payloads[-1]["action_data"]["reason"] == ""


@pytest.mark.asyncio
async def test_agreement_sends_its_rows_and_the_link(recorder: Recorder) -> None:
    purchase = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), units=12, paid_cents=150_000
    )
    data = SimpleNamespace(
        purchase=purchase,
        investor_name="Anna Ivanova",
        investor_email="anna@example.com",
        company=SimpleNamespace(id=uuid4(), name="Acme Robotics"),
        product=SimpleNamespace(name="Seed round"),
    )
    await agreement_service.request_agreement_email(data, None)  # type: ignore[arg-type]
    payload = recorder.payloads[-1]
    assert payload["type"] == "purchase.agreement"
    action = payload["action_data"]
    _assert_wire_safe(action)
    assert action["investor_name"] == "Anna Ivanova"
    assert action["company"] == "Acme Robotics"
    assert action["product"] == "Seed round"
    assert action["units"] == 12
    assert action["total_paid"] == "1,500.00"
    assert action["agreement_number"] in payload["title"]
    assert action["documents_url"].startswith("https://example.com/app/portfolio/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "as_of"),
    [("en", "October 23, 2026"), ("ru", "23 октября 2026 \u0433.")],
)
async def test_certificate_date_follows_the_investors_language(
    recorder: Recorder, language: str, as_of: str
) -> None:
    investor_id = uuid4()
    data = SimpleNamespace(
        investor_id=investor_id,
        investor_language=language,
        investor_name="Anna Ivanova",
        investor_email="anna@example.com",
        company=SimpleNamespace(id=uuid4(), name="Acme Robotics"),
        total_units=40,
        current_value_cents=2_000_000,
        as_of_date=datetime(2026, 10, 23, tzinfo=UTC),
    )
    await ownership_certificate_service.request_ownership_email(data, None)  # type: ignore[arg-type]
    payload = recorder.payloads[-1]
    assert payload["type"] == "ownership.certificate"
    action = payload["action_data"]
    _assert_wire_safe(action)
    assert action["as_of"] == as_of
    assert action["total_units"] == 40
    assert action["current_value"] == "20,000.00"
    assert "?doc=ownership" in action["documents_url"]


# ---------------------------------------------------------------------------
# Every emitter of an e-mail type carries action_data (source scan)
# ---------------------------------------------------------------------------


def test_every_email_type_emitter_carries_action_data() -> None:
    """A dict literal that names one of the e-mail types must also carry
    `action_data`, or its template would print raw {names}. The pair of
    "none missing": the scan found every type it is about."""
    found: set[str] = set()
    missing: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value: v
                for k, v in zip(node.keys, node.values, strict=True)
                if isinstance(k, ast.Constant)
            }
            type_node = keys.get("type")
            if type_node is None:
                continue
            literal: set[str] = set()
            if isinstance(type_node, ast.Constant) and type_node.value in EMAIL_TYPES:
                literal.add(type_node.value)
            elif (
                isinstance(type_node, ast.JoinedStr)
                and path.name == "service.py"
                and "withdrawals" in path.parts
            ):
                literal.update(t for t in EMAIL_TYPES if t.startswith("withdrawal."))
            if not literal:
                continue
            found |= literal
            if "action_data" not in keys:
                missing.append(f"{path.relative_to(_APP).as_posix()}:{node.lineno}")
    assert found == EMAIL_TYPES
    assert missing == []
