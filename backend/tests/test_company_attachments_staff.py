# =============================================================================
# CBSHOME Backend -- Company Attachments Staff-Flow Tests
#                     (Refactor 2 iter 2.2, D3 + G1.staff)
# =============================================================================
#
# Integration tests for the staff-flow attachments router:
#   GET    /api/v1/staff/companies/{id}/attachments
#   POST   /api/v1/staff/companies/{id}/attachments              (multipart)
#   PATCH  /api/v1/staff/companies/{id}/attachments/{att_id}     (json)
#   PATCH  /api/v1/staff/companies/{id}/attachments/{att_id}/replace
#                                                                 (multipart)
#   DELETE /api/v1/staff/companies/{id}/attachments/{att_id}
#   DELETE /api/v1/staff/companies/{id}/attachments/{att_id}/hard (admin only)
#
# Coverage:
#   - Staff list ignores publish flags and (with include_deleted) shows
#     soft-deleted rows.
#   - StaffAttachmentResponse exposes the operational triple
#     (storage_key, created_by_id, is_deleted) hidden in
#     AttachmentResponse.
#   - Multipart upload happy path (POST + replace).
#   - MIME whitelist enforcement (POST 400 on application/zip).
#   - PATCH metadata updates only the supplied fields.
#   - Soft delete flips is_deleted.
#   - Hard delete admin-only: 204 for admin, 403 for non-admin staff.
#
# 100MB upload size limit is intentionally NOT tested here -- enforced
# at the Nginx layer (R2 Q-ATT-3, technical-debt-tracked).
#
# Email prefix: "atts_" -- distinct from "att_" / "attp_" used by the
# auth-flow / public-flow tests.
# =============================================================================

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import delete_object, list_objects
from app.modules.companies.models import CompanyAttachment
from app.modules.companies.schemas import AttachmentInboxMetadata
from app.modules.companies.service import create_attachment
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    create_staff_user,
)

EMAIL_PREFIX = "atts_"
TEST_BUCKET = "cbshome-attachments-test"
VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def use_test_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[None, None]:
    """Point storage at the dedicated test bucket and drain it before each test."""
    monkeypatch.setattr(settings, "minio_bucket", TEST_BUCKET)
    keys = await list_objects("")
    for key in keys:
        await delete_object(key)
    yield


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users (and dependent attachments / companies / etc.)."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_user_and_token(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[User, str]:
    """Admin staff (every permission True). Returns (ORM User, token)."""
    data, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    user_id = UUID(data["user"]["id"])
    staff_user = await db_session.get(User, user_id)
    assert staff_user is not None
    return staff_user, token


async def _create_company_via_api(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co",
) -> UUID:
    """POST /staff/companies; return company_id."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    return UUID(resp.json()["id"])


async def _create_attachment_direct(
    db_session: AsyncSession,
    company_id: UUID,
    staff_user: User,
    *,
    title: str = "Doc",
    category: str = "legal/incorporation",
    language: str | None = "en",
    is_published: bool = True,
    is_public: bool = False,
    file_bytes: bytes = b"hello",
    original_filename: str = "doc.pdf",
    content_type: str = "application/pdf",
) -> CompanyAttachment:
    """Insert via service layer for setup of read-side tests."""
    metadata = AttachmentInboxMetadata(
        title=title,
        category=category,
        language=language,
        is_published=is_published,
        is_public=is_public,
    )
    attachment = await create_attachment(
        session=db_session,
        company_id=company_id,
        staff=staff_user,
        # Round 4 (PERF-01): service signature now takes file_data
        # (bytes or stream) plus an explicit file_size_bytes.
        file_data=file_bytes,
        file_size_bytes=len(file_bytes),
        original_filename=original_filename,
        content_type=content_type,
        metadata=metadata,
    )
    await db_session.commit()
    return attachment


def _multipart_upload_args(
    *,
    metadata: dict,
    file_bytes: bytes = b"pdf body",
    filename: str = "doc.pdf",
    content_type: str = "application/pdf",
) -> dict:
    """Build kwargs for httpx.AsyncClient.post(...) with multipart payload."""
    return {
        "files": {"file": (filename, file_bytes, content_type)},
        "data": {"metadata": json.dumps(metadata)},
    }


# ---------------------------------------------------------------------------
# Test 1: list returns all (regardless of publish flags), include_deleted=true
# surfaces soft-deleted rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_all_and_include_deleted_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff sees published, draft, private, and (when asked) deleted rows."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    await _create_attachment_direct(
        db_session, company_id, staff_user,
        title="Pub", is_published=True, is_public=True,
    )
    await _create_attachment_direct(
        db_session, company_id, staff_user,
        title="Draft", category="other", is_published=False, is_public=False,
    )
    deleted = await _create_attachment_direct(
        db_session, company_id, staff_user,
        title="Trashed", category="trash", is_published=True,
    )
    deleted.is_deleted = True
    await db_session.commit()

    # Default: deleted hidden, but draft + published visible.
    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/attachments",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert {item["title"] for item in items} == {"Pub", "Draft"}

    # include_deleted=true surfaces the trash.
    resp_all = await client.get(
        f"/api/v1/staff/companies/{company_id}/attachments",
        params={"include_deleted": "true"},
        headers=auth_headers(admin_token),
    )
    assert resp_all.status_code == 200
    titles_all = {item["title"] for item in resp_all.json()}
    assert titles_all == {"Pub", "Draft", "Trashed"}


# ---------------------------------------------------------------------------
# Test 2: StaffAttachmentResponse exposes storage_key, created_by_id, is_deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_response_includes_operational_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The staff list payload includes the three fields hidden from
    AttachmentResponse: storage_key, created_by_id, is_deleted."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    await _create_attachment_direct(db_session, company_id, staff_user)

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/attachments",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()[0]

    assert "storage_key" in item
    assert item["storage_key"].startswith(f"companies/{company_id}/attachments/")
    assert "is_deleted" in item
    assert item["is_deleted"] is False
    # Pydantic alias: ORM column `created_by` exposed at API as `created_by_id`.
    assert "created_by_id" in item
    assert item["created_by_id"] == str(staff_user.id)


# ---------------------------------------------------------------------------
# Test 3: POST multipart creates an attachment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_multipart_creates_attachment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Happy-path multipart upload: 201 + DB row + storage_key shape."""
    _, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    payload = b"freshly minted pdf bytes"
    args = _multipart_upload_args(
        metadata={
            "title": "Pitch Deck",
            "category": "marketing/presentations",
            "language": "en",
            "is_published": True,
            "is_public": True,
        },
        file_bytes=payload,
        filename="pitch.pdf",
        content_type="application/pdf",
    )

    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/attachments",
        headers=auth_headers(admin_token),
        **args,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Pitch Deck"
    assert body["category"] == "marketing/presentations"
    assert body["original_filename"] == "pitch.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["file_size_bytes"] == len(payload)
    assert body["is_published"] is True
    assert body["is_public"] is True
    assert body["storage_key"].endswith("/pitch.pdf")


# ---------------------------------------------------------------------------
# Test 4: POST with non-whitelisted MIME -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_invalid_mime_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Round 4 (SEC-01 / QC-02): MIME is resolved by filename extension,
    not by the multipart Content-Type header.

    Sub-case A: bad extension (.zip) -> 400, regardless of content_type.
    Sub-case B: spoofed header (claims application/pdf) on a clearly
        non-whitelisted extension (.html) -> still 400. This is the
        explicit XSS attack vector the SEC-01 fix closes: the header
        is now untrusted input.
    """
    _, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    # Sub-case A: extension outside the whitelist.
    args = _multipart_upload_args(
        metadata={"title": "Archive"},
        file_bytes=b"PK\x03\x04...",
        filename="bundle.zip",
        content_type="application/zip",
    )
    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/attachments",
        headers=auth_headers(admin_token),
        **args,
    )
    assert resp.status_code == 400, resp.text
    msg = resp.json().get("message", "")
    assert "MIME" in msg or "mime" in msg

    # Sub-case B: header spoof. evil.html with a polite content_type
    # claim must NOT bypass the extension whitelist.
    args = _multipart_upload_args(
        metadata={"title": "Spoofed"},
        file_bytes=b"<html><body>boom</body></html>",
        filename="evil.html",
        content_type="application/pdf",  # lying header
    )
    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/attachments",
        headers=auth_headers(admin_token),
        **args,
    )
    assert resp.status_code == 400, resp.text
    msg = resp.json().get("message", "")
    assert "MIME" in msg or "mime" in msg


# ---------------------------------------------------------------------------
# Test 5: PATCH metadata updates only supplied fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_metadata_partial_update(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH with {is_published: false} flips only that flag."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment_direct(
        db_session, company_id, staff_user,
        title="Original", is_published=True, is_public=False,
    )

    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}/attachments/{attachment.id}",
        json={"is_published": False, "title": "Renamed"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_published"] is False
    assert body["title"] == "Renamed"
    # Untouched fields stay put.
    assert body["is_public"] is False
    assert body["category"] == "legal/incorporation"


# ---------------------------------------------------------------------------
# Test 6: PATCH /replace swaps the file bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_replace_swaps_file_bytes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Replace endpoint updates storage_key + original_filename + size."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment_direct(
        db_session, company_id, staff_user,
        original_filename="v1.pdf",
        file_bytes=b"old",
    )

    new_payload = b"brand new bytes" * 10
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}/attachments/{attachment.id}/replace",
        files={"file": ("v2.pdf", new_payload, "application/pdf")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["original_filename"] == "v2.pdf"
    assert body["file_size_bytes"] == len(new_payload)
    assert body["storage_key"].endswith("/v2.pdf")


# ---------------------------------------------------------------------------
# Test 7: soft DELETE flips is_deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_flips_is_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE returns 204; the row stays with is_deleted=true."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment_direct(db_session, company_id, staff_user)

    resp = await client.delete(
        f"/api/v1/staff/companies/{company_id}/attachments/{attachment.id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Confirm via DB read -- row exists, is_deleted=True.
    # NOTE: a plain `select` would return the stale instance from
    # db_session's Identity Map (the row was committed to the DB by the
    # app's separate session, but db_session still has its pre-DELETE
    # snapshot cached). Use refresh() to force an UPDATE-from-DB.
    await db_session.refresh(attachment)
    assert attachment.is_deleted is True


# ---------------------------------------------------------------------------
# Test 8: hard DELETE drops the row + the MinIO object (admin)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_delete_admin_drops_row_and_object(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admin hard-delete: 204 + row gone from DB + object gone from MinIO."""
    from app.core.storage import object_exists

    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment_direct(db_session, company_id, staff_user)
    storage_key = attachment.storage_key

    # Sanity: object is in the test bucket.
    assert await object_exists(storage_key) is True

    resp = await client.delete(
        f"/api/v1/staff/companies/{company_id}/attachments/{attachment.id}/hard",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Row gone.
    refreshed = (
        await db_session.execute(
            select(CompanyAttachment).where(CompanyAttachment.id == attachment.id)
        )
    ).scalar_one_or_none()
    assert refreshed is None

    # Object gone.
    assert await object_exists(storage_key) is False


# ---------------------------------------------------------------------------
# Test 9: hard DELETE by non-admin staff -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_delete_non_admin_returns_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Default staff (DEFAULT_STAFF_PERMISSIONS) has company_manage but
    is_admin = False (translation_edit defaults to False), so hard-delete
    is forbidden."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment_direct(db_session, company_id, staff_user)

    # Non-admin staff with default permissions.
    _, non_admin_token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )

    resp = await client.delete(
        f"/api/v1/staff/companies/{company_id}/attachments/{attachment.id}/hard",
        headers=auth_headers(non_admin_token),
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Test 10: 404 on cross-company patch (defence in depth)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_on_other_company_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Patching attachment_id from company A under company B's URL -> 404."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_a = await _create_company_via_api(client, admin_token, suffix="coA")
    company_b = await _create_company_via_api(client, admin_token, suffix="coB")
    attachment_a = await _create_attachment_direct(db_session, company_a, staff_user)

    resp = await client.patch(
        f"/api/v1/staff/companies/{company_b}/attachments/{attachment_a.id}",
        json={"title": "Hijacked"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404, resp.text
