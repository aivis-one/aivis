# =============================================================================
# AIVIS.ONE Backend -- Test Helpers (post iter 2.5 mini-fix #3)
# =============================================================================
#
# This module used to contain ~400 lines of cleanup_test_users and friends
# -- functions whose only job was hand-deleting rows in the right order
# from a shared dev database that tests had polluted. After the conftest
# rewrite moved tests to per-worker ephemeral databases, those cleanups
# are dead code: the whole DB disappears in pytest_unconfigure.
#
# What remains here is the small set of HTTP / auth helpers that test
# bodies actually call. These are honest helpers, not cleanup glue.
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from urllib.parse import urlencode

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session_factory
from app.modules.documents.constants import AGENT_INTEGRATOR_AGREEMENT_TYPE
from app.modules.documents.models import Document, DocumentSigning, DocumentStatus
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.referrals.models import ReferralLink
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS
from app.modules.staff.models import StaffProfile
from app.modules.users.models import (
    KYCStatus,
    OnboardingStep,
    User,
    UserRole,
)


# ---------------------------------------------------------------------------
# Telegram initData fabrication
# ---------------------------------------------------------------------------

# Same dev-only token as tests/test_auth_telegram.py historical default.
# A real token in production is enforced by config validation.
BOT_TOKEN = settings.telegram_bot_token or "TEST"

# Monotonic counter so back-to-back build_init_data() calls do not
# produce duplicate auth_date / hash collisions inside a single test.
_init_data_counter = 0


def build_init_data(
    telegram_id: int,
    first_name: str = "Test",
    last_name: str = "User",
    username: str | None = None,
    language: str = "en",
    auth_date: int | None = None,
) -> str:
    """Forge a Telegram WebApp initData string signed with BOT_TOKEN.

    Mirrors the algorithm the real client uses: build a sorted
    key=value\n list of all fields except `hash`, sign with
    HMAC-SHA256(secret_key, payload), where secret_key =
    HMAC-SHA256("WebAppData", bot_token).
    """
    global _init_data_counter
    _init_data_counter += 1

    # auth_date uniqueness across rapid back-to-back calls is not needed:
    # query_id below already includes _init_data_counter, so the
    # data-check-string and its sha256 anti-replay key differ on every
    # call even if auth_date collides on the same wall-clock second.
    auth_date = auth_date or int(time.time())
    user_obj = {
        "id": telegram_id,
        "first_name": first_name,
        "last_name": last_name,
        "language_code": language,
    }
    if username is not None:
        user_obj["username"] = username

    # Compact JSON, no spaces -- this is what real Telegram sends.
    user_json = json.dumps(user_obj, separators=(",", ":"))

    parts = {
        "user": user_json,
        "auth_date": str(auth_date),
        "query_id": f"q{telegram_id}_{_init_data_counter}",
    }

    data_check_string = "\n".join(
        f"{k}={parts[k]}" for k in sorted(parts.keys())
    )

    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    signature = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return urlencode({**parts, "hash": signature})


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------


def auth_headers(token: str) -> dict[str, str]:
    """Build the standard Authorization header used by every test."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Email auth helpers
# ---------------------------------------------------------------------------


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Password123!",
    referral_code: str | None = None,
    verified: bool = True,
    email_confirmed: bool | None = None,
) -> dict:
    """POST /api/v1/auth/email/register and assert 201. Returns the
    response body (contains session_token and user details).

    If email is omitted, a UUID-suffixed unique email is generated. This
    is the default path -- tests that need a specific email (e.g. to
    check duplicate-rejection or to re-use the same address across two
    register calls) pass email= explicitly.

    VERIFIED BY DEFAULT SINCE H10, and the default is the point. The KYC
    gate closes buying, installment plans, withdrawals and the agent
    application to an unverified investor, and those are what a large
    part of the suite exists to exercise -- purchases, installments,
    reversals, commissions, withdrawals. A fixture that left every user
    unverified would have each of those tests fail with 402 on the way
    to whatever it was actually testing. This does not weaken the gate:
    it is enforced app-wide and tested directly in test_kyc_gate.py,
    which uses verified=False to build the state on purpose.

    The approval is written straight to the row rather than through the
    staff endpoint: a fixture should not need a staff account and a
    reason string to produce an ordinary user.
    """
    if email is None:
        email = f"test_{uuid.uuid4().hex[:12]}@example.com"
    payload: dict[str, str] = {"email": email, "password": password}
    if referral_code:
        payload["referral_code"] = referral_code

    resp = await client.post("/api/v1/auth/email/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Echo the email back into the response so callers that did not
    # pre-generate it can still find out what was used.
    body.setdefault("email", email)

    if verified:
        await set_kyc_status(body["user"]["id"], KYCStatus.APPROVED)

    # THE CONFIRMED E-MAIL IS KYC'S FIRST CONDITION.
    # A user registered with verified=False is the one a test is about to
    # send through POST /kyc/submit, so by default that user's e-mail is
    # confirmed; every other user keeps the unconfirmed address the real
    # registration leaves (the e-mail tests rely on it). Pass
    # email_confirmed explicitly to build the other combination.
    if email_confirmed is None:
        email_confirmed = not verified
    if email_confirmed:
        await confirm_email(body["user"]["id"])

    return body


async def confirm_email(user_id: str | uuid.UUID) -> None:
    """Mark a user's e-mail as confirmed, in its own transaction.

    The same JSONB flag the verification endpoint writes
    (credentials.email.verified); the code round trip is skipped.
    """
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
        ).scalar_one()
        creds = dict(user.credentials)
        creds["email"] = dict(creds["email"])
        creds["email"]["verified"] = True
        user.set_jsonb("credentials", creds)
        await session.commit()


async def set_kyc_status(user_id: str | uuid.UUID, status: str) -> None:
    """Write a user's kyc_status directly, in its own transaction.

    Opens a session of its own so callers that only hold an AsyncClient
    (most of them) do not have to grow a session parameter.
    """
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
        ).scalar_one()
        user.kyc_status = status
        await session.commit()


async def fund_user(user_id: str | uuid.UUID, amount_cents: int) -> None:
    """Give a user spendable balance, in its own transaction.

    A confirmed active-ledger credit -- the same shape a settled deposit
    leaves behind, which is what get_active_balance sums.
    """
    factory = get_session_factory()
    async with factory() as session:
        await record_active_ledger(
            session,
            user_id=uuid.UUID(str(user_id)),
            amount_cents=amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"test:funding:{uuid.uuid4()}",
        )
        await session.commit()


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = "Password123!",
) -> dict:
    """POST /api/v1/auth/email/login and assert 200."""
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Telegram auth helpers
# ---------------------------------------------------------------------------


async def telegram_entry(
    client: AsyncClient,
    *,
    telegram_id: int,
    first_name: str = "Test",
    last_name: str = "User",
    username: str | None = None,
    language: str = "en",
    referral_code: str | None = None,
) -> dict:
    """POST /api/v1/auth/telegram with forged initData. Asserts 200 and
    returns the body as it is: a session, `mfa_required`, or -- for a
    Telegram id no row holds -- `link_required` plus a `link_token`.
    """
    init_data = build_init_data(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        language=language,
    )
    payload: dict[str, str] = {"init_data": init_data}
    if referral_code:
        payload["referral_code"] = referral_code

    resp = await client.post("/api/v1/auth/telegram", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def read_telegram_link_code(link_token: str) -> str:
    """The e-mail code held in a link token's Redis record.

    The letter is an outbox row that tests do not deliver; the code is
    kept inside the link token record, which is where a
    test reads it.
    """
    from app.core.redis import get_redis

    raw = await get_redis().get(f"telegram_link:{link_token}")
    assert raw is not None, "link token record is gone"
    code = json.loads(raw)["code"]
    assert code, "no code was requested for this link token"
    return code


async def link_telegram_email(
    client: AsyncClient,
    link_token: str,
    email: str,
    *,
    consent_given: bool = True,
    referral_code: str | None = None,
) -> Any:
    """POST /api/v1/auth/telegram/link/email. Returns the response."""
    payload: dict[str, Any] = {
        "link_token": link_token,
        "email": email,
        "consent_given": consent_given,
    }
    if referral_code:
        payload["referral_code"] = referral_code
    return await client.post("/api/v1/auth/telegram/link/email", json=payload)


async def link_telegram_confirm(
    client: AsyncClient,
    link_token: str,
    code: str,
    *,
    second_code: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """POST /api/v1/auth/telegram/link/confirm. Returns the response."""
    payload: dict[str, str] = {"link_token": link_token, "code": code}
    if second_code:
        payload["second_code"] = second_code
    return await client.post(
        "/api/v1/auth/telegram/link/confirm", json=payload, headers=headers
    )


async def login_telegram(
    client: AsyncClient,
    *,
    telegram_id: int,
    first_name: str = "Test",
    last_name: str = "User",
    username: str | None = None,
    language: str = "en",
    referral_code: str | None = None,
    email: str | None = None,
) -> dict:
    """Enter through Telegram the way a person does, and return a session body.

    POST /api/v1/auth/telegram; when no row holds the Telegram id the
    server answers `link_required` and this helper goes on through the
    e-mail step and the code step (a fresh unique address unless `email`
    is given), so the returned body is always {user, session_token}.
    """
    body = await telegram_entry(
        client,
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        language=language,
        referral_code=referral_code,
    )
    if not body.get("link_required"):
        return body

    token = body["link_token"]
    address = email or f"tg_{uuid.uuid4().hex[:12]}@example.com"
    resp = await link_telegram_email(
        client, token, address, referral_code=referral_code
    )
    assert resp.status_code == 200, resp.text
    code = await read_telegram_link_code(token)
    resp = await link_telegram_confirm(client, token, code)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def login_legacy_telegram(
    client: AsyncClient,
    session: AsyncSession,
    *,
    telegram_id: int,
) -> dict:
    """A Telegram-only account of the OLD kind (no e-mail), then its login.

    No such account is born any more (POST /auth/telegram creates
    nothing); the few that exist are rows made before the change. The row
    is written straight to the database, and the session comes from the
    ordinary find-and-login path.
    """
    from app.modules.auth.service import get_platform_user_id

    platform_id = await get_platform_user_id(session)
    session.add(
        User(
            role=UserRole.INVESTOR,
            referred_by=platform_id,
            credentials={
                "telegram": {
                    "id": telegram_id,
                    "username": None,
                    "first_name": "Legacy",
                    "last_name": None,
                    "photo_url": None,
                    "language_code": "en",
                }
            },
            onboarding_step=OnboardingStep.ROLE_SELECTED,
        )
    )
    await session.commit()
    return await telegram_entry(client, telegram_id=telegram_id)


# ---------------------------------------------------------------------------
# Staff / admin factory helpers
# ---------------------------------------------------------------------------


async def create_staff_user(
    client: AsyncClient,
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str = "Password123!",
) -> tuple[User, str]:
    """Register a regular user, then promote to staff by inserting a
    StaffProfile. Returns (User, token).

    The created StaffProfile has the platform's DEFAULT_STAFF_PERMISSIONS
    (same as a real staff member created via POST /staff/users) and
    is_active=True. Tests that need full admin access should call
    create_admin_user instead -- it flips translation_edit (the only
    default-False permission) to True.

    If email is omitted, a UUID-suffixed unique email is generated.

    IDEMPOTENT: if a user with this email already exists (e.g. a previous
    test in the same run already created the same staff account), we
    skip registration, log them in, and ensure the staff promotion is
    in place. The dev DB is shared across tests, so the first call does
    the heavy lifting and the rest piggyback.
    """
    if email is None:
        email = f"staff_{uuid.uuid4().hex[:12]}@example.com"

    # Already present from a previous call? -- skip register, just login.
    existing = (
        await session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        data = await register_user(client, email=email, password=password)
        token = data["session_token"]
        user = (
            await session.execute(
                select(User).where(
                    User.credentials["email"]["email"].as_string() == email
                )
            )
        ).scalar_one()
    else:
        data = await login_user(client, email=email, password=password)
        token = data["session_token"]
        user = existing

    user.role = UserRole.STAFF
    user.onboarding_step = OnboardingStep.ONBOARDING_COMPLETE
    user.kyc_status = KYCStatus.APPROVED

    profile = (
        await session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    if profile is None:
        # Mirror the real create_staff() service: default permissions +
        # is_active=True. Without is_active the _get_verified_staff
        # dependency refuses the request with 403 "Staff profile
        # deactivated", which used to look like a permission failure
        # but is really a flag failure.
        profile = StaffProfile(
            id=uuid.uuid4(),
            user_id=user.id,
            permissions=dict(DEFAULT_STAFF_PERMISSIONS),
            is_active=True,
        )
        session.add(profile)
    else:
        # Ensure idempotent path also restores invariants in case an
        # earlier test mutated them.
        profile.is_active = True
        profile.set_jsonb("permissions", dict(DEFAULT_STAFF_PERMISSIONS))

    await session.commit()
    return user, token


async def create_admin_user(
    client: AsyncClient,
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str = "Password123!",
) -> tuple[User, str]:
    """Like create_staff_user, but every permission key in
    DEFAULT_STAFF_PERMISSIONS is True so is_admin() returns True.

    Note: StaffProfile.permissions is a single JSONB column holding a
    dict, NOT one bool column per permission. Earlier versions of this
    helper looped over __table__.columns looking for bool columns; that
    only touched is_active and left permissions untouched, so the
    "admin" had only the default-False keys missing -- not an admin.

    If email is omitted, a UUID-suffixed unique email is generated.
    """
    if email is None:
        email = f"admin_{uuid.uuid4().hex[:12]}@example.com"
    user, token = await create_staff_user(
        client, session, email=email, password=password
    )

    profile = (
        await session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one()

    # Build a dict where every known permission key is True. is_admin()
    # checks all keys in VALID_PERMISSION_KEYS are present and True;
    # using DEFAULT_STAFF_PERMISSIONS.keys() guarantees we cover them all
    # (and stay in sync if a new permission is added later).
    full_perms = {key: True for key in DEFAULT_STAFF_PERMISSIONS}
    profile.set_jsonb("permissions", full_perms)
    profile.is_active = True

    await session.commit()
    await session.refresh(profile)
    return user, token


# ---------------------------------------------------------------------------
# Agent factory helpers (Task 1 Block C)
# ---------------------------------------------------------------------------


async def sign_agent_agreement(user_id: str | uuid.UUID) -> None:
    """Record a signing of the integrator-agent agreement.

    POST /referrals/links is refused until a document of type
    agent_integrator_agreement is signed. The cabinet documents are data
    seeded from files, so the test database may not hold the type: this
    creates an active row for it when absent (required for no role, so no
    onboarding is affected), then writes the signing. Idempotent.
    """
    factory = get_session_factory()
    async with factory() as session:
        uid = uuid.UUID(str(user_id))
        document = (
            await session.execute(
                select(Document).where(
                    Document.type == AGENT_INTEGRATOR_AGREEMENT_TYPE,
                    Document.status == DocumentStatus.ACTIVE,
                )
            )
        ).scalars().first()
        if document is None:
            document = Document(
                type=AGENT_INTEGRATOR_AGREEMENT_TYPE,
                version=1,
                language="en",
                title="Integrator agreement (test)",
                required_for_roles=[],
                content_hash="",
                status=DocumentStatus.ACTIVE,
                created_by=uid,
            )
            session.add(document)
            await session.flush()
        already = (
            await session.execute(
                select(DocumentSigning.id).where(
                    DocumentSigning.user_id == uid,
                    DocumentSigning.document_id == document.id,
                )
            )
        ).first()
        if already is None:
            session.add(
                DocumentSigning(
                    user_id=uid,
                    document_id=document.id,
                    ip_address="127.0.0.1",
                    user_agent="tests",
                )
            )
        await session.commit()


async def create_agent_with_link(
    client: AsyncClient,
    session: AsyncSession,
    *,
    sign_agreement: bool = True,
) -> tuple[User, str, ReferralLink]:
    """Register a user, promote to agent, create one referral link.

    Returns (agent User, token, ReferralLink). Promotion is a direct
    role flip via the DB session -- the referrals router only checks
    user.role == AGENT (_require_agent), mirroring how create_staff_user
    promotes staff. The link is created through the real endpoint so
    the code-generation path stays covered.
    """
    data = await register_user(client)
    token = data["session_token"]

    user = (
        await session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string()
                == data["email"]
            )
        )
    ).scalar_one()
    user.role = UserRole.AGENT
    await session.commit()

    # The link is refused until the integrator agreement is signed.
    if sign_agreement:
        await sign_agent_agreement(user.id)

    resp = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    link_id = resp.json()["id"]

    link = (
        await session.execute(
            select(ReferralLink).where(ReferralLink.id == link_id)
        )
    ).scalar_one()
    return user, token, link


# ---------------------------------------------------------------------------
# KYC submission helpers (H12)
# ---------------------------------------------------------------------------
#
# POST /kyc/submit STOPPED ACCEPTING AN EMPTY BODY IN H12. It is now
# multipart carrying the identity documents, and four test files drive
# it. The multipart is built here rather than in each of them so that
# the next change to the document set edits one place instead of
# fourteen call sites -- and so that a test which wants to send a
# DELIBERATELY wrong set has to say so explicitly rather than differ
# from its neighbours by accident.


KYC_SUBMIT_URL = "/api/v1/kyc/submit"

# A JPEG HEAD FOLLOWED BY MARKER TEXT, and the head is not decoration.
# These bytes used to be ASCII only, on the stated ground that
# validation was by filename extension and nothing depended on the
# payload decoding as an image. H15 item 9 ended that: the submit path
# now compares the first bytes against the type the extension claims,
# so a fixture without the JPEG magic number is refused as a renamed
# file and every submit test built on it fails at the door.
#
# NOT A DECODABLE JPEG EITHER -- the signature is all the upload path
# reads, and no test opens these as images. The trailing text stays
# distinct per kind so the round-trip test can assert it got back THAT
# object rather than merely an object of the right length.
_JPEG_HEAD = b"\xff\xd8\xff\xe0"

KYC_FIXTURE_BYTES: dict[str, bytes] = {
    "front": _JPEG_HEAD + b"aivis-test-front-image-bytes",
    "back": _JPEG_HEAD + b"aivis-test-back-image-bytes",
    "selfie": _JPEG_HEAD + b"aivis-test-selfie-image-bytes",
}


def kyc_document_files(
    *,
    include_back: bool = False,
    extension: str = "jpg",
    content_type: str = "image/jpeg",
    omit: tuple[str, ...] = (),
) -> dict[str, tuple[str, bytes, str]]:
    """Build the multipart `files=` mapping for POST /kyc/submit.

    Defaults to a passport submission: front plus selfie, no back.
    `include_back` adds the reverse for an id_card or driving licence.
    `omit` drops parts on purpose, for the tests that assert an
    incomplete set is refused.
    """
    parts = {
        "front_image": "front",
        "selfie_image": "selfie",
    }
    if include_back:
        parts["back_image"] = "back"

    return {
        field: (
            f"{kind}.{extension}",
            KYC_FIXTURE_BYTES[kind],
            content_type,
        )
        for field, kind in parts.items()
        if field not in omit
    }


async def submit_kyc_application(
    client: AsyncClient,
    token: str,
    *,
    document_type: str = "passport",
    include_back: bool = False,
) -> Any:
    """POST a well-formed verification submission and return the response.

    Does NOT assert the status: callers check for 201, 400 or 409
    themselves, and a helper that asserted 201 could not be used by the
    tests about refusals.
    """
    return await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": document_type},
        files=kyc_document_files(include_back=include_back),
    )
