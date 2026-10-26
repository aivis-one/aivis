# =============================================================================
# AIVIS.ONE Backend -- e-mail letters: what each emitter puts in its request
# =============================================================================
#
# Since H43 the backend builds every letter itself (app/letters) and the
# request carries it whole in its `email` block; comms sends exactly that.
# What is pinned here is the emitter's side: each of the twelve e-mail
# types carries the block, built in the person's language from the type's
# own data, plus the title and body comms requires (the bell's words for a
# type that lands in the cabinet); no other type carries a block; and the
# shared addresses (core/email_vars.py letter_vars) a letter shows.
#
# No database and no network: emit_event is replaced by a recorder, the
# person's language is read from a stand-in session, and the stubs carry
# only the attributes the emitters read. The builder itself -- every type in
# both languages, escaping, the loader -- is tests/test_letters.py.
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
from app.core.email_vars import letter_vars
from app.letters import LetterError
from app.modules.auth import service as auth_service
from app.modules.installments import service as installment_service
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


class Session:
    """Stands in for the caller's session: the one read an emitter makes is
    the person's users.language (app/letters recipient_language)."""

    def __init__(self, language: str = "en") -> None:
        self.language = language

    async def execute(self, statement: Any) -> Any:
        return SimpleNamespace(scalar_one=lambda: self.language)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    for module in (
        auth_service,
        agreement_service,
        ownership_certificate_service,
        withdrawal_service,
        installment_service,
    ):
        monkeypatch.setattr(module, "emit_event", rec)
        monkeypatch.setattr(module, "comms_configured", lambda: True)
    return rec


def _letter(payload: dict[str, Any]) -> dict[str, str]:
    """The request's letter, held to comms' form: subject and text non-blank,
    html non-blank, no action_data any more (nothing renders it)."""
    assert "action_data" not in payload
    letter = payload["email"]
    assert set(letter) == {"subject", "text", "html"}
    for part in ("subject", "text", "html"):
        assert letter[part].strip(), part
    assert payload["title"].strip()
    assert payload["body"].strip()
    return letter


# ---------------------------------------------------------------------------
# The shared variables
# ---------------------------------------------------------------------------


def test_shared_addresses_come_from_the_frontend_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app/")
    data = letter_vars()
    assert set(data) == SHARED
    assert data["cabinet_url"] == "https://example.com/app"
    assert data["site_url"] == "https://example.com"
    assert data["logo_url"] == "https://example.com/email/logo.png"
    # nothing configured: the letter points at the site and at hello@ on its host
    monkeypatch.setattr(settings, "support_url", "")
    monkeypatch.setattr(settings, "telegram_bot_url", "")
    monkeypatch.setattr(settings, "support_email", "")
    data = letter_vars()
    assert data["support_url"] == "https://example.com"
    assert data["support_email"] == "hello@example.com"


def test_configured_support_addresses_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    monkeypatch.setattr(settings, "support_url", "https://t.example.org/bot")
    monkeypatch.setattr(settings, "support_email", "help@example.org")
    data = letter_vars()
    assert data["support_url"] == "https://t.example.org/bot"
    assert data["support_email"] == "help@example.org"


def test_support_url_falls_back_to_the_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    monkeypatch.setattr(settings, "support_url", "")
    monkeypatch.setattr(settings, "telegram_bot_url", "https://t.example.org/bot")
    assert letter_vars()["support_url"] == "https://t.example.org/bot"


def test_no_logo_without_a_site_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "")
    data = letter_vars()
    assert data["site_url"] == ""
    assert data["logo_url"] == ""


# ---------------------------------------------------------------------------
# The emitters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "word"), [("en", "Verification code"), ("ru", "Код подтверждения")]
)
async def test_verification_code_letter_carries_the_code_in_the_persons_language(
    recorder: Recorder, language: str, word: str
) -> None:
    await auth_service._request_verification_email(
        Session(language),  # type: ignore[arg-type]
        uuid4(),
        "482915",
        datetime.now(UTC),
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == "auth.verification_code"
    letter = _letter(payload)
    ttl = str(auth_service._VERIFICATION_CODE_TTL_MINUTES)
    for part in ("text", "html"):
        assert "482915" in letter[part]
        assert word in letter[part]
        assert ttl in letter[part]
    # e-mail only: title and body are the subject and the heading, and the
    # code is in neither
    assert payload["title"] == letter["subject"]
    assert payload["body"] == word
    assert "482915" not in payload["title"] + payload["body"]


@pytest.mark.asyncio
async def test_telegram_link_code_letter_names_the_telegram_account(
    recorder: Recorder,
) -> None:
    await auth_service._request_telegram_link_code_email(
        Session("ru"),  # type: ignore[arg-type]
        uuid4(),
        "654321",
        datetime.now(UTC),
        "@alice",
    )
    payload = recorder.payloads[0]
    assert payload["type"] == "auth.telegram_link_code"
    letter = _letter(payload)
    for part in ("text", "html"):
        assert "654321" in letter[part]
        assert "@alice" in letter[part]
        assert "Привязка Telegram" in letter[part]


@pytest.mark.asyncio
async def test_telegram_linked_letter_names_the_account(recorder: Recorder) -> None:
    await auth_service._request_telegram_linked_email(
        Session(), uuid4(), "@alice"  # type: ignore[arg-type]
    )
    payload = recorder.payloads[0]
    assert payload["type"] == "auth.telegram_linked"
    letter = _letter(payload)
    assert "@alice" in letter["text"]
    assert "@alice" in letter["html"]


@pytest.mark.asyncio
async def test_password_reset_letter_carries_the_link(recorder: Recorder) -> None:
    await auth_service._request_password_reset_email(
        Session(),  # type: ignore[arg-type]
        uuid4(),
        "tok123",
        datetime.now(UTC),
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == "auth.password_reset"
    letter = _letter(payload)
    link = "https://example.com/app/password-reset/confirm?token=tok123"
    assert link in letter["text"]
    assert f'href="{link}"' in letter["html"]
    ttl = str(auth_service._PASSWORD_RESET_TOKEN_TTL_MINUTES)
    assert ttl in letter["text"]
    assert link not in payload["title"] + payload["body"]


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
async def test_withdrawal_letter_and_bell_carry_the_amount(
    recorder: Recorder, status: WithdrawalStatus
) -> None:
    withdrawal = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), amount_cents=25_000, status=status
    )
    rejected = status == WithdrawalStatus.REJECTED
    reason = "Wallet address is invalid" if rejected else None
    await withdrawal_service._notify_withdrawal(
        Session("ru"),  # type: ignore[arg-type]
        withdrawal,  # type: ignore[arg-type]
        reason=reason,
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == f"withdrawal.{status}"
    letter = _letter(payload)
    assert "250.00 $" in letter["text"]
    assert "250.00 $" in payload["body"]
    assert "Вывод средств" in payload["title"]
    if reason is not None:
        assert reason in letter["text"]
        assert reason in payload["body"]


@pytest.mark.asyncio
async def test_a_rejection_without_a_reason_is_refused(recorder: Recorder) -> None:
    """The rejection's letter prints the reason; one without it is a defect
    of the caller, and the builder refuses it rather than print nothing
    (owner ruling, H43: a missing value is an error, an empty one is not)."""
    withdrawal = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), amount_cents=1_000,
        status=WithdrawalStatus.REJECTED,
    )
    with pytest.raises(LetterError, match="reason"):
        await withdrawal_service._notify_withdrawal(Session(), withdrawal)  # type: ignore[arg-type]
    assert recorder.payloads == []


@pytest.mark.asyncio
async def test_agreement_letter_carries_its_rows_and_the_link(
    recorder: Recorder,
) -> None:
    purchase = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), units=12, paid_cents=150_000
    )
    data = SimpleNamespace(
        purchase=purchase,
        investor_name="Anna Ivanova",
        investor_email="anna@example.com",
        company=SimpleNamespace(id=uuid4(), name="Acme Robotics", shares_per_option=25),
        product=SimpleNamespace(name="Seed round"),
    )
    await agreement_service.request_agreement_email(data, Session())  # type: ignore[arg-type]
    payload = recorder.payloads[-1]
    assert payload["type"] == "purchase.agreement"
    letter = _letter(payload)
    number = str(purchase.id).split("-")[0].upper()
    for value in ("Anna Ivanova", "Acme Robotics", "Seed round", "Units: 12",
                  "$1,500.00", number, "https://example.com/app/portfolio/"):
        assert value in letter["text"], value
    assert number in letter["subject"]
    assert number in payload["title"]
    assert "Seed round" in payload["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "as_of"),
    [
        ("en", "October 23, 2026"),
        ("ru", "23 октября 2026 \u0433."),
        ("ru-RU", "23 октября 2026 \u0433."),
    ],
)
async def test_certificate_date_follows_the_letters_language(
    recorder: Recorder, language: str, as_of: str
) -> None:
    data = SimpleNamespace(
        investor_id=uuid4(),
        investor_language=language,
        investor_name="Anna Ivanova",
        investor_email="anna@example.com",
        company=SimpleNamespace(id=uuid4(), name="Acme Robotics", shares_per_option=25),
        total_units=40,
        current_value_cents=2_000_000,
        as_of_date=datetime(2026, 10, 23, tzinfo=UTC),
    )
    await ownership_certificate_service.request_ownership_email(
        data, Session(language)  # type: ignore[arg-type]
    )
    payload = recorder.payloads[-1]
    assert payload["type"] == "ownership.certificate"
    letter = _letter(payload)
    assert as_of in letter["text"]
    assert "1000" in letter["text"]  # 40 lots of 25 parts
    assert "20,000.00" in letter["text"]
    assert "?doc=ownership" in letter["text"]
    assert "Acme Robotics" in payload["title"]


# ---------------------------------------------------------------------------
# Every e-mail type carries the letter, and no other type does (source scan)
# ---------------------------------------------------------------------------


def _letter_type(call: ast.Call, path: Path) -> set[str]:
    """The type(s) a letter_request(...) call builds: its literal first
    argument, or -- in the withdrawals service, which keys the type by the
    withdrawal's status -- the four withdrawal types."""
    first = call.args[0] if call.args else None
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return {first.value}
    if "withdrawals" in path.parts and path.name == "service.py":
        return {t for t in EMAIL_TYPES if t.startswith("withdrawal.")}
    return {"<not a literal>"}


def test_every_email_type_emitter_carries_the_letter_and_no_other_does() -> None:
    """Each request dict that builds a letter (**letter_request(...)) builds
    one of the twelve e-mail types, every one of the twelve is built
    somewhere, and no request names `email` by hand. comms refuses an
    `email` block on a type without e-mail, at intake (the pair: the scan
    found every type it is about)."""
    built: set[str] = set()
    hand_written: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if key is None and (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "letter_request"
                ):
                    built |= _letter_type(value, path)
                if isinstance(key, ast.Constant) and key.value == "email" and any(
                    isinstance(k, ast.Constant) and k.value == "type" for k in node.keys
                ):
                    hand_written.append(f"{path.relative_to(_APP).as_posix()}:{node.lineno}")
    assert built == EMAIL_TYPES
    assert hand_written == []
