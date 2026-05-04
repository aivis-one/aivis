# =============================================================================
# CBSHOME Backend -- Onboarding Flow Tests (F2.3, updated by 0024, 0025, F5.1 BP-15)
# =============================================================================
#
# Tests cover the full onboarding pipeline:
#   1: Full flow: register → verify → profile → role → kyc → docs → complete
#   2: Profile update without required fields → step stays email_verified
#   3: Select role when step != profile_complete → 400
#   4: Select invalid role (staff) → 422
#   5: Select role success → step = role_selected, role changed
#   6: KYC approval keeps step at kyc_done (non-blocking + docs pending)
#   7: Signing all docs advances step to onboarding_complete
#   8: KYC submit with zero required docs → onboarding_complete (BP-15)
#   9: KYC submit with required docs → step stays kyc_done (regression guard)
#
# Email prefix: "onb_" -- unique to this test file, cleaned up in fixture.
#
# The cleanup fixture also wipes documents + document_signings. Otherwise
# the rows seeded by install_cbshome.sh would (a) clash with active docs
# this test tries to create and (b) skew the onboarding_complete assertion.
#
# F5.1 BP-15 NOTE.
#   submit_kyc() now calls maybe_complete_onboarding() right after the
#   step advance. That means tests asserting kyc_done after submit MUST
#   create the role's required documents BEFORE submitting -- otherwise
#   the no-docs branch fires and the user lands on onboarding_complete.
#   This matches production reality: documents are seeded by
#   seed_documents.py during cbshome update, long before any user
#   reaches the KYC step.
# =============================================================================

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.documents.models import Document, DocumentSigning
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_staff_user,
    register_user,
)

EMAIL_PREFIX = "onb_"


def webhook_headers() -> dict[str, str]:
    """Build headers with KYC webhook secret."""
    return {"X-Webhook-Secret": settings.kyc_webhook_secret}


async def _cleanup_documents(session: AsyncSession) -> None:
    """Wipe documents + signings. Seed rows from install_cbshome.sh would
    otherwise collide with active documents these tests create and also
    skew the onboarding_complete assertion."""
    await session.execute(delete(DocumentSigning))
    await session.execute(delete(Document))
    await session.commit()


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean docs + test users before and after each test."""
    await _cleanup_documents(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await _cleanup_documents(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_verification_code(
    db_session: AsyncSession, email: str
) -> str:
    """Read verification code from user credentials in DB."""
    await db_session.rollback()
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    return user.credentials["onboarding"]["email_token"]


async def _get_step(client: AsyncClient, token: str) -> str:
    """Get current onboarding_step via GET /users/me."""
    resp = await client.get(
        "/api/v1/users/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    return resp.json()["onboarding_step"]


async def _create_active_doc(
    client: AsyncClient,
    staff_token: str,
    doc_type: str,
    version: int = 1,
    language: str = "en",
    required_for_roles: list[str] | None = None,
) -> str:
    """Create + publish a document, return its id."""
    if required_for_roles is None:
        required_for_roles = ["investor"]

    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": doc_type,
            "title": f"Test {doc_type} v{version}",
            "language": language,
            "version": version,
            "required_for_roles": required_for_roles,
        },
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    resp2 = await client.patch(
        f"/api/v1/staff/documents/{doc_id}",
        json={"status": "active"},
        headers=auth_headers(staff_token),
    )
    assert resp2.status_code == 200
    return doc_id


# ---------------------------------------------------------------------------
# Full flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_onboarding_flow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Complete onboarding: register → verify → profile → role → kyc → docs → complete.

    BP-15 layout: documents are seeded BEFORE the user reaches KYC, mirroring
    the production flow where seed_documents.py populates the legal table
    during cbshome update -- long before any user clicks "Start verification".
    """
    email = f"{EMAIL_PREFIX}full@example.com"

    # -- 0. Pre-seed required documents (analogous to seed_documents.py). --
    # Investor requires: privacy_policy, terms_of_service, investment_agreement.
    # Helper defaults language="en" and required_for_roles=["investor"].
    _, staff_token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )
    doc_ids = []
    for doc_type in ["privacy_policy", "terms_of_service", "investment_agreement"]:
        doc_id = await _create_active_doc(client, staff_token, doc_type)
        doc_ids.append(doc_id)

    # -- 1. Register --
    data = await register_user(client, email=email)
    token = data["session_token"]
    user_id = data["user"]["id"]
    assert data["user"]["onboarding_step"] == "registered"

    # -- 2. Verify email --
    code = await _get_verification_code(db_session, email)
    resp = await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["onboarding_step"] == "email_verified"

    # -- 3. Fill profile --
    resp = await client.patch(
        "/api/v1/users/me",
        json={
            "profile": {
                "first_name": "Test",
                "last_name": "User",
                "country": "DE",
                "phone": "+491234567890",
            }
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["onboarding_step"] == "profile_complete"

    # -- 4. Select role --
    resp = await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "investor"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "investor"
    assert resp.json()["onboarding_step"] == "role_selected"

    # -- 5. KYC submit + approve --
    resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(token)
    )
    assert resp.status_code == 201

    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "approved"},
        headers=webhook_headers(),
    )
    assert resp.status_code == 200

    # Docs exist for the role -> step stays at kyc_done.
    step = await _get_step(client, token)
    assert step == "kyc_done"

    # -- 6. Sign all required docs --
    for doc_id in doc_ids:
        resp = await client.post(
            f"/api/v1/documents/{doc_id}/sign",
            headers=auth_headers(token),
        )
        assert resp.status_code == 201

    # -- 7. Verify onboarding complete --
    step = await _get_step(client, token)
    assert step == "onboarding_complete"


# ---------------------------------------------------------------------------
# Individual step tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_incomplete_no_advance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Profile update without required fields does not advance step."""
    email = f"{EMAIL_PREFIX}partial@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Verify email first.
    code = await _get_verification_code(db_session, email)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )

    # Update with only first_name (missing last_name, country).
    resp = await client.patch(
        "/api/v1/users/me",
        json={"profile": {"first_name": "Only"}},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["onboarding_step"] == "email_verified"


@pytest.mark.asyncio
async def test_select_role_wrong_step(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Select role when step != profile_complete → 400."""
    email = f"{EMAIL_PREFIX}wrongstep@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Step is "registered", not "profile_complete".
    resp = await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "investor"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_select_role_invalid_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Select staff or platform role → 422 (schema validation)."""
    email = f"{EMAIL_PREFIX}badrole@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Advance to profile_complete first.
    code = await _get_verification_code(db_session, email)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )
    await client.patch(
        "/api/v1/users/me",
        json={
            "profile": {
                "first_name": "T",
                "last_name": "U",
                "country": "DE",
            }
        },
        headers=auth_headers(token),
    )

    # Try staff role.
    resp = await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "staff"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_select_role_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Select agent role → 200, role changed, step advanced."""
    email = f"{EMAIL_PREFIX}agent@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Advance to profile_complete.
    code = await _get_verification_code(db_session, email)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )
    await client.patch(
        "/api/v1/users/me",
        json={
            "profile": {
                "first_name": "A",
                "last_name": "G",
                "country": "AT",
            }
        },
        headers=auth_headers(token),
    )

    # Select agent.
    resp = await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "agent"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "agent"
    assert resp.json()["onboarding_step"] == "role_selected"


@pytest.mark.asyncio
async def test_kyc_approval_advances_step(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """KYC submit moves role_selected -> kyc_done; webhook approval keeps it.

    submit_kyc() advances step to kyc_done immediately (non-blocking KYC).
    The webhook only updates kyc_status, never onboarding_step. With at
    least one required document present for the role, BP-15 does NOT fire,
    so the user stays on kyc_done as expected.
    """
    email = f"{EMAIL_PREFIX}kyc@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]
    user_id = data["user"]["id"]

    # Pre-seed an active doc so BP-15 (no-docs auto-complete) does not fire.
    _, staff_token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )
    await _create_active_doc(client, staff_token, "privacy_policy")

    # Fast-track to role_selected.
    code = await _get_verification_code(db_session, email)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )
    await client.patch(
        "/api/v1/users/me",
        json={
            "profile": {
                "first_name": "K",
                "last_name": "Y",
                "country": "CH",
            }
        },
        headers=auth_headers(token),
    )
    await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "investor"},
        headers=auth_headers(token),
    )

    # Submit KYC.
    await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(token)
    )

    # Approve via webhook.
    await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "approved"},
        headers=webhook_headers(),
    )

    step = await _get_step(client, token)
    assert step == "kyc_done"


# ---------------------------------------------------------------------------
# BP-15: KYC submit must auto-complete when role has zero required docs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kyc_submit_no_docs_auto_completes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """BP-15: submit_kyc() with zero required docs -> onboarding_complete.

    Reproduces the production hang where the legal table held no active
    rows for the user's role. Before BP-15, the user advanced to kyc_done,
    landed on /onboarding/docs with an empty list, and was bounced back
    by the router guard on every Sign-documents click. After BP-15,
    submit_kyc() detects the empty list and advances straight to
    onboarding_complete.
    """
    email = f"{EMAIL_PREFIX}nodocs@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Cleanup fixture wipes the documents table at test start, so the role
    # has zero active required documents -- exactly the BP-15 trigger.

    # Fast-track to role_selected.
    code = await _get_verification_code(db_session, email)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )
    await client.patch(
        "/api/v1/users/me",
        json={
            "profile": {
                "first_name": "N",
                "last_name": "D",
                "country": "DE",
            }
        },
        headers=auth_headers(token),
    )
    await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "investor"},
        headers=auth_headers(token),
    )

    # Submit KYC -- with no active docs, step must auto-advance to complete.
    resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(token)
    )
    assert resp.status_code == 201

    step = await _get_step(client, token)
    assert step == "onboarding_complete"


@pytest.mark.asyncio
async def test_kyc_submit_with_docs_stays_kyc_done(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression guard: with required docs present, submit_kyc() must NOT
    auto-complete -- user must reach the docs page and sign them.

    Pairs with test_kyc_submit_no_docs_auto_completes to lock the BP-15
    branch behaviour: the helper differentiates on the documents table,
    not on a global flag.
    """
    email = f"{EMAIL_PREFIX}withdocs@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Pre-seed an active investor doc -- BP-15 must NOT fire.
    _, staff_token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )
    await _create_active_doc(client, staff_token, "privacy_policy")

    # Fast-track to role_selected.
    code = await _get_verification_code(db_session, email)
    await client.post(
        "/api/v1/auth/verify-email",
        json={"code": code},
        headers=auth_headers(token),
    )
    await client.patch(
        "/api/v1/users/me",
        json={
            "profile": {
                "first_name": "W",
                "last_name": "D",
                "country": "DE",
            }
        },
        headers=auth_headers(token),
    )
    await client.post(
        "/api/v1/users/me/select-role",
        json={"role": "investor"},
        headers=auth_headers(token),
    )

    # Submit KYC -- doc exists, so step must NOT auto-advance to complete.
    resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(token)
    )
    assert resp.status_code == 201

    step = await _get_step(client, token)
    assert step == "kyc_done"
