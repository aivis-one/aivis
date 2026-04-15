# =============================================================================
# CBSHOME Backend -- Onboarding Flow Tests (F2.3)
# =============================================================================
#
# Tests cover the full onboarding pipeline:
#   1: Full flow: register → verify → profile → role → kyc → docs → complete
#   2: Profile update without required fields → step stays email_verified
#   3: Select role when step != profile_complete → 400
#   4: Select invalid role (staff) → 422
#   5: Select role success → step = role_selected, role changed
#   6: KYC approval advances step to kyc_done
#   7: Signing all docs advances step to onboarding_complete
#
# Email prefix: "onb_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
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
) -> str:
    """Create + publish a document, return its id."""
    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": doc_type,
            "title": f"Test {doc_type} v{version}",
            "content_url": f"https://docs.example.com/{doc_type}/v{version}",
            "version": version,
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
    """Complete onboarding: register → verify → profile → role → kyc → docs → complete."""
    email = f"{EMAIL_PREFIX}full@example.com"

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

    step = await _get_step(client, token)
    assert step == "kyc_done"

    # -- 6. Create and sign all required docs --
    _, staff_token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )

    # Investor requires: privacy_policy, terms_of_service, investment_agreement.
    doc_ids = []
    for doc_type in ["privacy_policy", "terms_of_service", "investment_agreement"]:
        doc_id = await _create_active_doc(client, staff_token, doc_type)
        doc_ids.append(doc_id)

    # Sign all documents.
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
    """KYC webhook approved advances step from role_selected to kyc_done."""
    email = f"{EMAIL_PREFIX}kyc@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]
    user_id = data["user"]["id"]

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
