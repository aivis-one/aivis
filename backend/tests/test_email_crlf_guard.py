# =============================================================================
# AIVIS.ONE Backend -- SMTP Header-Injection Guard Tests (TASK-22 / finding 16)
# =============================================================================
#
# WHY THIS FILE EXISTS -- and the risk it covers is NOT the CVE:
#   CVE-2026-53533 (aiosmtplib CR/LF SMTP command injection; installed 3.0.2,
#   vulnerable <= 5.1.0) is MITIGATED here, not absent. Measured 2026-08-14:
#   every recipient on all five send paths comes from one of exactly two
#   EmailStr fields, and TWO independent gates stand in front of the socket:
#
#     gate 1  EmailStr / email_validator -- rejects an address with an
#             embedded CR or LF outright
#     gate 2  EmailMessage.__setitem__   -- raises on a header value carrying
#             CR/LF, before send_smtp is ever reached
#
#   NOT ONE TEST ASSERTED EITHER OF THEM. That is the actual risk: add a
#   third write path to a stored email address without EmailStr and the
#   mitigation disappears with nothing failing. The cheap guard is a test,
#   not an upgrade -- the fixed version is two majors above the declared cap
#   `aiosmtplib>=3.0.0,<4.0`, so taking it changes what installs, which is
#   exactly what decision 65 chose option B to avoid.
#
#   Pure tests: no DB, no Redis, no SMTP. They exercise the two gates
#   directly, which is the only way to assert a mitigation that works by
#   REFUSING rather than by doing something observable.
# =============================================================================

import pytest
from pydantic import ValidationError

from app.core.email import build_message
from app.modules.auth.schemas import EmailLoginRequest, EmailRegisterRequest
from app.modules.companies.schemas import CreateCompanyRequest

# One header-injection payload per shape. The interesting half is that the
# folded forms (\r\n followed by whitespace) are legal header continuations
# in RFC 5322 -- they are the ones a deny-list of "\n" alone would miss.
CRLF_PAYLOADS = [
    "victim@example.com\r\nBcc: attacker@evil.test",
    "victim@example.com\nBcc: attacker@evil.test",
    "victim@example.com\rBcc: attacker@evil.test",
    "victim@example.com\r\n\tBcc: attacker@evil.test",
    "victim@example.com\r\n Subject: injected",
]


# ---------------------------------------------------------------------------
# GATE 1 -- the two EmailStr fields, which are where every recipient
# in the system originates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", CRLF_PAYLOADS)
def test_gate1_register_email_rejects_crlf(payload: str) -> None:
    """auth/schemas.py:26 -- EmailRegisterRequest.email is EmailStr."""
    with pytest.raises(ValidationError):
        EmailRegisterRequest(email=payload, password="correct horse 12")


@pytest.mark.parametrize("payload", CRLF_PAYLOADS)
def test_gate1_login_email_rejects_crlf(payload: str) -> None:
    """auth/schemas.py:47 -- EmailLoginRequest.email is EmailStr."""
    with pytest.raises(ValidationError):
        EmailLoginRequest(email=payload, password="x")


@pytest.mark.parametrize("payload", CRLF_PAYLOADS)
def test_gate1_company_email_rejects_crlf(payload: str) -> None:
    """companies/schemas.py:101 -- the second of the two fields."""
    with pytest.raises(ValidationError):
        CreateCompanyRequest(name="Acme", email=payload)


def test_gate1_control_a_valid_address_is_accepted() -> None:
    """MUST-FIRE CONTROL for gate 1.

    Every assertion above is that something is REFUSED, so all of them
    would still pass if EmailStr rejected everything. This is the case
    that proves the gate is a filter and not a wall.
    """
    assert EmailRegisterRequest(
        email="Legit.User@Example.COM", password="correct horse 12"
    ).email
    assert EmailLoginRequest(email="legit@example.com", password="x").email


# ---------------------------------------------------------------------------
# GATE 2 -- EmailMessage.__setitem__, which stands even if gate 1 is ever
# bypassed by a future write path that does not use EmailStr
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", CRLF_PAYLOADS)
def test_gate2_build_message_refuses_injected_recipient(payload: str) -> None:
    """core/email.py:73 -- msg["To"] = recipient raises before send_smtp.

    This is the gate that matters for the CVE, because it does not depend
    on where the address came from. It is asserted separately from gate 1
    on purpose: they are two independent layers, and a test that only
    covered gate 1 would go green on the day someone adds a write path
    that skips it.
    """
    with pytest.raises(ValueError):
        build_message(
            from_email="noreply@aivis.one",
            recipient=payload,
            subject="Hello",
            body="body",
        )


def test_gate2_refuses_injected_subject_too() -> None:
    """The subject is a header as well, and is attacker-influenced in
    several templates. Same gate, different field."""
    with pytest.raises(ValueError):
        build_message(
            from_email="noreply@aivis.one",
            recipient="victim@example.com",
            subject="Hi\r\nBcc: attacker@evil.test",
            body="body",
        )


def test_gate2_control_a_clean_message_builds() -> None:
    """MUST-FIRE CONTROL for gate 2 -- and it checks the headers landed,
    not merely that nothing raised."""
    msg = build_message(
        from_email="noreply@aivis.one",
        recipient="victim@example.com",
        subject="Hello",
        body="body",
    )
    assert msg["To"] == "victim@example.com"
    assert msg["Subject"] == "Hello"
    assert "Bcc" not in msg


# ---------------------------------------------------------------------------
# THE LOOKALIKE -- pinned because finding 16 names it explicitly and because
# the next reader will otherwise assume it is the control
# ---------------------------------------------------------------------------


def test_aiosmtplib_cap_is_still_declared() -> None:
    """The `aiosmtplib>=3.0.0,<4.0` cap in pyproject.toml is DELIBERATE,
    and this pins the declaration so that lifting it is a visible act.

    Decision 65 chose option B: do NOT take the CVE fix, because 5.1.1 is
    two majors above the cap and taking it changes what installs. That
    decision is defensible only while the two gates above hold, which is
    what the rest of this file makes checkable.

    ⚠ IT ASSERTS THE DECLARATION, NOT `aiosmtplib.__version__`, AND THE
    REASON IS A MEASUREMENT: the first draft asserted the installed version
    and FAILED here at 5.1.2 -- because the authoring box's ambient
    environment had been provisioned ad hoc, not from this file. An
    installed-version assertion tests how the machine was set up; the
    declaration is what the product actually ships. The container is built
    from pyproject.toml, so that is the thing worth pinning.
    """
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    assert "aiosmtplib>=3.0.0,<4.0" in text, (
        "the aiosmtplib cap changed. That is a real choice, not a "
        "dependency refresh: read STAGE-III finding 16 and decision 65 "
        "before lifting it, and check the two gates above still hold."
    )


def test_strip_lower_is_not_a_crlf_control() -> None:
    """`.strip().lower()` at auth/service.py:288 looks like a guard and is
    not one: it removes CR/LF at the EDGES and leaves an EMBEDDED one
    completely intact.

    Asserted rather than written in a comment so that nobody later deletes
    an EmailStr annotation on the grounds that "the service strips it
    anyway". The assertion is that the lookalike FAILS to help.
    """
    embedded = "victim@example.com\r\nBcc: attacker@evil.test"
    assert "\r\n" in embedded.strip().lower(), (
        "strip() removed an embedded CRLF -- if this ever becomes true, "
        "re-read finding 16 before relying on it: the reasoning there "
        "assumes it does not"
    )
