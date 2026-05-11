# =============================================================================
# CBSHOME Backend -- Company Attachments Auth-Flow Tests
#                     (Refactor 2 iter 2.2, D1 + G1.auth)
# =============================================================================
#
# Integration tests for the auth-flow attachments router:
#   GET /api/v1/companies/{id}/attachments
#   GET /api/v1/companies/{id}/attachments/{att_id}/download
#
# Public-flow and staff-flow tests live in separate files added in
# subsequent iteration batches.
#
# FIXTURES:
#   use_test_bucket  -- monkeypatches settings.minio_bucket to the
#                       dedicated `cbshome-attachments-test` bucket and
#                       drains it before each test. Mirrors test_storage.py.
#   cleanup          -- removes test users (and their cascading
#                       attachments / companies / pools / posts / ...) via
#                       cleanup_test_users(EMAIL_PREFIX).
#
# SETUP PATTERN:
#   _admin_user_and_token() -- staff with all permissions True; used as
#                              `staff` argument to service.create_attachment
#                              while the staff router is not yet wired
#                              (D3 lands later in this iteration).
#   _investor_token()       -- registered investor user, default role.
#   _create_company_via_api -- POST /staff/companies with admin credentials.
#   _create_attachment      -- bypass POST-multipart by calling
#                              service.create_attachment directly. The
#                              service is the same code path that the
#                              future staff router will hit, so we don't
#                              lose coverage by short-circuiting.
#
# Email prefix: "att_" -- unique to this test file; all test users share
# it so cleanup_test_users matches them in one query.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
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
    register_user,
)

EMAIL_PREFIX = "att_"
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
    """Clean test users (and their dependent attachments / companies / etc.)
    before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_user_and_token(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[User, str]:
    """Create an admin staff user; return ORM User + session token.

    The ORM User is needed by service.create_attachment as the `staff`
    arg (audit + created_by FK).
    """
    data, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    user_id = UUID(data["user"]["id"])
    staff_user = await db_session.get(User, user_id)
    assert staff_user is not None
    return staff_user, token


async def _investor_token(
    client: AsyncClient, suffix: str = "investor"
) -> str:
    """Register an investor user; return session token."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return data["session_token"]


async def _create_company_via_api(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co",
) -> UUID:
    """Create a company via POST /staff/companies; return company_id."""
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


async def _create_attachment(
    db_session: AsyncSession,
    company_id: UUID,
    staff_user: User,
    *,
    title: str = "Doc",
    category: str = "legal/incorporation",
    # iter 2.4-post mini-fix: attachments.language is NOT NULL with
    # default 'en'. Helper signature reflects that -- pass an explicit
    # ISO code, or omit to land on the universal English fallback.
    language: str = "en",
    is_published: bool = True,
    is_public: bool = False,
    file_bytes: bytes = b"hello world",
    original_filename: str = "doc.pdf",
    content_type: str = "application/pdf",
) -> CompanyAttachment:
    """Insert an attachment via service (bypasses staff router not yet wired)."""
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


# ---------------------------------------------------------------------------
# Test 1: List returns only published, non-deleted attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_only_published_not_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Auth-flow list filters out unpublished and soft-deleted rows."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)

    # 2 published.
    await _create_attachment(
        db_session, company_id, staff_user,
        title="Pub 1", category="legal/incorporation",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="Pub 2", category="marketing/presentations",
    )
    # 1 draft (not published).
    await _create_attachment(
        db_session, company_id, staff_user,
        title="Draft", category="patents", is_published=False,
    )
    # 1 soft-deleted.
    deleted = await _create_attachment(
        db_session, company_id, staff_user,
        title="Gone", category="other",
    )
    deleted.is_deleted = True
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments",
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    titles = {item["title"] for item in items}
    assert titles == {"Pub 1", "Pub 2"}

    # Operational fields hidden from auth-flow consumers.
    sample = items[0]
    assert "storage_key" not in sample
    assert "created_by" not in sample
    assert "created_by_id" not in sample
    assert "is_deleted" not in sample


# ---------------------------------------------------------------------------
# Test 2: ?category= exact match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_category(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?category= returns only attachments with the exact category path."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)

    await _create_attachment(
        db_session, company_id, staff_user,
        title="A", category="legal/incorporation",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="B", category="marketing/presentations",
    )

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments",
        params={"category": "legal/incorporation"},
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "A"


# ---------------------------------------------------------------------------
# Test 3: ?category_prefix= prefix match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_category_prefix(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?category_prefix= returns rows whose category starts with the prefix."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)

    await _create_attachment(
        db_session, company_id, staff_user,
        title="P", category="marketing/presentations",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="O", category="marketing/onepagers",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="L", category="legal/incorporation",
    )

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments",
        params={"category_prefix": "marketing/"},
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    titles = {item["title"] for item in items}
    assert titles == {"P", "O"}


# ---------------------------------------------------------------------------
# Test 4: ?language= exact match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_language(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?language= returns only rows with that ISO 639-1 code."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)

    # Same category, different languages -- guarantees the filter is the
    # only thing distinguishing them.
    await _create_attachment(
        db_session, company_id, staff_user,
        title="EN", category="marketing/presentations", language="en",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="DE", category="marketing/presentations", language="de",
    )

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments",
        params={"language": "de"},
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "DE"


# ---------------------------------------------------------------------------
# Test 5: List without auth -> 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_without_auth_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Auth-flow list requires authentication."""
    _, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    resp = await client.get(f"/api/v1/companies/{company_id}/attachments")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 6: Download published -> 302 with working presigned URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_published_returns_302_with_working_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Download endpoint issues a 302 to a presigned URL that fetches
    the original bytes."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)
    payload = b"investor deck v3 -- attachments smoke"
    attachment = await _create_attachment(
        db_session, company_id, staff_user,
        file_bytes=payload, content_type="application/pdf",
    )

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments/{attachment.id}/download",
        headers=auth_headers(investor_token),
        follow_redirects=False,
    )
    assert resp.status_code == 302, resp.text
    location = resp.headers.get("location")
    assert location and location.startswith("http")

    # Round 4 (SEC-01): the presigned URL must instruct the browser to
    # download the file rather than render it inline. boto3 surfaces
    # ResponseContentDisposition as a `response-content-disposition`
    # query parameter on the signed URL; MinIO echoes it back in the
    # Content-Disposition header when the browser fetches the URL.
    assert "response-content-disposition" in location.lower()
    assert "attachment" in location.lower()

    # The presigned URL must be self-sufficient -- no auth headers added.
    async with httpx.AsyncClient() as http:
        follow = await http.get(location)
    assert follow.status_code == 200
    assert follow.content == payload
    # And the actual response carries Content-Disposition: attachment.
    cd = follow.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert "doc.pdf" in cd


# ---------------------------------------------------------------------------
# Test 7: Download unpublished -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_unpublished_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hidden (unpublished) attachments cannot be pulled by URL guessing."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment(
        db_session, company_id, staff_user, is_published=False,
    )

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments/{attachment.id}/download",
        headers=auth_headers(investor_token),
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: Download soft-deleted -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_soft_deleted_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Soft-deleted attachments are invisible to the auth-flow download."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment(
        db_session, company_id, staff_user,
    )
    attachment.is_deleted = True
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments/{attachment.id}/download",
        headers=auth_headers(investor_token),
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 9: Download under wrong company -> 404 (cross-company leak protection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_other_company_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An attachment_id leaked from company A cannot be queried under company B."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    investor_token = await _investor_token(client)
    company_a = await _create_company_via_api(client, admin_token, suffix="coA")
    company_b = await _create_company_via_api(client, admin_token, suffix="coB")
    attachment_a = await _create_attachment(
        db_session, company_a, staff_user,
    )

    resp = await client.get(
        f"/api/v1/companies/{company_b}/attachments/{attachment_a.id}/download",
        headers=auth_headers(investor_token),
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 10: AttachmentInboxMetadata defaults language to 'en' when omitted
# ---------------------------------------------------------------------------
#
# iter 2.4-post mini-fix: schema default lands explicit-or-omitted on the
# universal English fallback rather than NULL. Sidecar JSON files in
# attachments-inbox no longer need to carry "language": "en" -- omitting
# the field gives the same result.


def test_inbox_metadata_language_defaults_to_en() -> None:
    """AttachmentInboxMetadata.language has a required-with-default of 'en'.

    Validating a payload that omits the language field should produce
    a model whose .language is 'en' -- the universal English fallback
    that replaced the old NULL semantic.
    """
    metadata = AttachmentInboxMetadata.model_validate({"title": "Investor Brief"})
    assert metadata.language == "en"


# ---------------------------------------------------------------------------
# Test 11: AttachmentInboxMetadata rejects explicit null language
# ---------------------------------------------------------------------------


def test_inbox_metadata_rejects_null_language() -> None:
    """An inbox cbsmeta.json that carries `"language": null` must fail.

    The column is NOT NULL post-migration 0034; null in the wire payload
    has no valid landing on the row. Pydantic's Literal validation
    blocks it before the orphan/replace logic in reconcile_attachments
    is reached.
    """
    with pytest.raises(ValidationError):
        AttachmentInboxMetadata.model_validate(
            {"title": "Investor Brief", "language": None}
        )


# ---------------------------------------------------------------------------
# Test 12: AttachmentPatchBody — language omit vs explicit null
# ---------------------------------------------------------------------------
#
# iter 2.4-post mini-fix: the PATCH wire-shape distinguishes "field
# absent" (no change) from "field present and null" (would clear a
# NOT NULL column -> rejected). A field_validator on PatchBody
# enforces the distinction; without it, an explicit null would survive
# exclude_unset and crash on flush with an IntegrityError.


def test_patch_body_omits_language_keeps_default_and_excluded() -> None:
    """Omitting language leaves the dump empty -- PATCH treats it as no-op."""
    from app.modules.companies.schemas import AttachmentPatchBody

    body = AttachmentPatchBody.model_validate({})
    # exclude_unset drops the absent field entirely -- the service's
    # `setattr` loop never touches `language`.
    assert body.model_dump(exclude_unset=True) == {}


def test_patch_body_rejects_explicit_null_language() -> None:
    """`{"language": null}` is rejected at validation time, not flush time."""
    from app.modules.companies.schemas import AttachmentPatchBody

    with pytest.raises(ValidationError):
        AttachmentPatchBody.model_validate({"language": None})
