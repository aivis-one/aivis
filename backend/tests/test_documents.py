# =============================================================================
# CBSHOME Backend -- Document Tests (Sprint 2.2, updated by 0024, 0025)
# =============================================================================
#
# Tests cover:
#   1:  Staff creates document -> 201, status=draft
#   2:  Non-staff creates document -> 403
#   3:  Status flow: draft -> active -> archived (+ invalid transition)
#   4:  Delete draft document -> 204
#   5:  Delete active document -> 400
#   6:  List documents by role (investor sees own package)
#   7:  Sign active document -> 201
#   8:  Sign same document again -> 409
#   9:  Update document title and required_for_roles
#   10: Sign archived document -> 400
#
# Email prefix: "s22_" -- unique to this test file, cleaned up in fixture.
#
# The cleanup fixture also wipes the whole documents + document_signings
# tables, because seed_documents.py populates them at install time and
# those seed rows would otherwise clash with active documents the tests
# try to create.
# =============================================================================

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import (
    auth_headers,
    create_staff_user,
    register_user,
)

EMAIL_PREFIX = "s22_"


async def _staff_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create and return a staff user's session token."""
    _, token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )
    return token


async def _create_active_document(
    client: AsyncClient,
    staff_token: str,
    doc_type: str = "privacy_policy",
    version: int = 1,
    language: str = "en",
    required_for_roles: list[str] | None = None,
) -> dict:
    """Helper: create a document and publish it (draft -> active)."""
    if required_for_roles is None:
        required_for_roles = ["investor"]

    # Create draft.
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
    doc = resp.json()

    # Publish: draft -> active.
    resp2 = await client.patch(
        f"/api/v1/staff/documents/{doc['id']}",
        json={"status": "active"},
        headers=auth_headers(staff_token),
    )
    assert resp2.status_code == 200
    return resp2.json()


# ---------------------------------------------------------------------------
# Staff CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_document_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff creates a document -> 201, status=draft."""
    token = await _staff_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": "privacy_policy",
            "title": "Privacy Policy v1",
            "language": "en",
            "version": 1,
            "required_for_roles": ["investor", "agent"],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()

    assert body["type"] == "privacy_policy"
    assert body["version"] == 1
    assert body["language"] == "en"
    assert body["status"] == "draft"
    assert body["title"] == "Privacy Policy v1"
    assert body["required_for_roles"] == ["investor", "agent"]


@pytest.mark.asyncio
async def test_create_document_non_staff(client: AsyncClient) -> None:
    """Non-staff user tries to create document -> 403."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}inv@example.com"
    )
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": "privacy_policy",
            "title": "Privacy Policy v1",
            "language": "en",
            "required_for_roles": ["investor"],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_document_status_flow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Status transitions: draft -> active -> archived + invalid."""
    token = await _staff_token(client, db_session)

    # Create draft.
    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": "terms_of_service",
            "title": "Terms v1",
            "language": "en",
            "required_for_roles": ["investor"],
        },
        headers=auth_headers(token),
    )
    doc_id = resp.json()["id"]
    assert resp.json()["status"] == "draft"

    # draft -> active.
    resp2 = await client.patch(
        f"/api/v1/staff/documents/{doc_id}",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "active"

    # active -> archived.
    resp3 = await client.patch(
        f"/api/v1/staff/documents/{doc_id}",
        json={"status": "archived"},
        headers=auth_headers(token),
    )
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "archived"

    # archived -> active (invalid transition).
    resp4 = await client.patch(
        f"/api/v1/staff/documents/{doc_id}",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    assert resp4.status_code == 400


@pytest.mark.asyncio
async def test_delete_draft_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Delete a draft document -> 204."""
    token = await _staff_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": "investment_agreement",
            "title": "Agreement v1",
            "language": "en",
            "required_for_roles": ["investor"],
        },
        headers=auth_headers(token),
    )
    doc_id = resp.json()["id"]

    resp2 = await client.delete(
        f"/api/v1/staff/documents/{doc_id}",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 204


@pytest.mark.asyncio
async def test_delete_active_document_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Delete an active document -> 400."""
    token = await _staff_token(client, db_session)

    doc = await _create_active_document(client, token, "agent_agreement")

    resp = await client.delete(
        f"/api/v1/staff/documents/{doc['id']}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# User: list + sign
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_by_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor sees docs with investor in required_for_roles; not agent-only."""
    staff_token = await _staff_token(client, db_session)

    # privacy_policy required for investor (and agent).
    await _create_active_document(
        client, staff_token, "privacy_policy",
        required_for_roles=["investor", "agent"],
    )
    # agent_agreement required for agent only.
    await _create_active_document(
        client, staff_token, "agent_agreement",
        required_for_roles=["agent"],
    )

    # Register investor.
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}list@example.com"
    )
    inv_token = inv_data["session_token"]

    resp = await client.get(
        "/api/v1/documents",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    docs = resp.json()

    doc_types = [d["type"] for d in docs]
    assert "privacy_policy" in doc_types
    # Investor should NOT see a doc that is only required for agents.
    assert "agent_agreement" not in doc_types


@pytest.mark.asyncio
async def test_sign_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sign an active document -> 201."""
    staff_token = await _staff_token(client, db_session)
    doc = await _create_active_document(client, staff_token, "privacy_policy")

    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}sign@example.com"
    )
    inv_token = inv_data["session_token"]

    resp = await client.post(
        f"/api/v1/documents/{doc['id']}/sign",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["document_id"] == doc["id"]
    assert "signed_at" in body


@pytest.mark.asyncio
async def test_sign_document_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sign the same document twice -> 409."""
    staff_token = await _staff_token(client, db_session)
    doc = await _create_active_document(
        client, staff_token, "terms_of_service"
    )

    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}sigdup@example.com"
    )
    inv_token = inv_data["session_token"]

    # First sign.
    resp1 = await client.post(
        f"/api/v1/documents/{doc['id']}/sign",
        headers=auth_headers(inv_token),
    )
    assert resp1.status_code == 201

    # Second sign -> conflict.
    resp2 = await client.post(
        f"/api/v1/documents/{doc['id']}/sign",
        headers=auth_headers(inv_token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_document_title_and_roles(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Update document title and required_for_roles."""
    token = await _staff_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": "company_agreement",
            "title": "Old Title",
            "language": "en",
            "required_for_roles": ["company"],
        },
        headers=auth_headers(token),
    )
    doc_id = resp.json()["id"]

    resp2 = await client.patch(
        f"/api/v1/staff/documents/{doc_id}",
        json={
            "title": "New Title",
            "required_for_roles": ["company", "agent"],
        },
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["title"] == "New Title"
    assert body["required_for_roles"] == ["company", "agent"]


@pytest.mark.asyncio
async def test_sign_archived_document_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sign an archived document -> 400."""
    staff_token = await _staff_token(client, db_session)

    # Create and activate document.
    doc = await _create_active_document(
        client, staff_token, "investment_agreement"
    )

    # Archive it: active -> archived.
    await client.patch(
        f"/api/v1/staff/documents/{doc['id']}",
        json={"status": "archived"},
        headers=auth_headers(staff_token),
    )

    # Investor tries to sign archived doc.
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}arch@example.com"
    )
    inv_token = inv_data["session_token"]

    resp = await client.post(
        f"/api/v1/documents/{doc['id']}/sign",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 400
