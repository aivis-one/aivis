# =============================================================================
# CBSHOME Backend -- Company Attachments Public-Flow Tests
#                     (Refactor 2 iter 2.2, D2 + G1.public)
# =============================================================================
#
# Integration tests for the public-flow attachments router:
#   GET /api/v1/public/companies/{id}/attachments
#   GET /api/v1/public/companies/{id}/attachments/{att_id}/download
#
# Coverage:
#   - Visibility predicate: public AND published AND NOT deleted.
#   - 404 (not 403) for any failing component (R2 §3.4).
#   - Cross-company leak protection.
#   - Per-IP rate limit on both endpoints (overridden via monkeypatch
#     so the test runs in seconds, not minutes).
#
# FIXTURES:
#   use_test_bucket             -- shared pattern; drains the test bucket.
#   cleanup                     -- cleanup_test_users(EMAIL_PREFIX).
#   clear_public_rate_limits    -- wipes the two Redis counter keys for
#                                  127.0.0.1 between tests so an earlier
#                                  test doesn't poison the next one.
#
# Email prefix: "attp_" -- intentionally distinct from "att_" used by
# the auth-flow tests; "attp_" does NOT start with "att_" (4th char "p"
# vs "_") so the two cleanup_test_users sweeps do not collide if both
# files run in the same session.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
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

EMAIL_PREFIX = "attp_"
TEST_BUCKET = "cbshome-attachments-test"
VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _clear_public_rate_limits() -> None:
    """Wipe the rate-limit Redis counters used by the public router for
    the test client IP (127.0.0.1 via ASGITransport)."""
    from app.core.redis import get_redis
    try:
        redis = get_redis()
        await redis.delete("public_attach_list:127.0.0.1")
        await redis.delete("public_attach_dl:127.0.0.1")
    except RuntimeError:
        pass


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


@pytest.fixture(autouse=True)
async def clear_rate_limits() -> AsyncGenerator[None, None]:
    """Reset Redis rate-limit counters between tests."""
    await _clear_public_rate_limits()
    yield
    await _clear_public_rate_limits()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_user_and_token(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[User, str]:
    """Create an admin staff user; return ORM User + session token."""
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
    category: str = "marketing/presentations",
    language: str | None = "en",
    is_published: bool = True,
    is_public: bool = True,
    file_bytes: bytes = b"public payload",
    original_filename: str = "doc.pdf",
    content_type: str = "application/pdf",
) -> CompanyAttachment:
    """Insert an attachment via service.

    Defaults are public + published so most tests can call this without
    arguments and rely on the visibility flags being on.
    """
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
        file_bytes=file_bytes,
        original_filename=original_filename,
        content_type=content_type,
        metadata=metadata,
    )
    await db_session.commit()
    return attachment


# ---------------------------------------------------------------------------
# Test 1: list returns only public + published + not-deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_only_public_published_not_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Visibility predicate: only rows that pass all three flags appear."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    # Visible: public + published + not deleted.
    await _create_attachment(
        db_session, company_id, staff_user,
        title="Visible", category="marketing/onepagers",
    )
    # Hidden: public but not published.
    await _create_attachment(
        db_session, company_id, staff_user,
        title="Draft", category="marketing/draft",
        is_public=True, is_published=False,
    )
    # Hidden: published but not public.
    await _create_attachment(
        db_session, company_id, staff_user,
        title="Private", category="legal/incorporation",
        is_public=False, is_published=True,
    )
    # Hidden: public + published but soft-deleted.
    deleted = await _create_attachment(
        db_session, company_id, staff_user,
        title="Gone", category="other",
    )
    deleted.is_deleted = True
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments"
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "Visible"

    # Operational fields must not leak through the public response model.
    sample = items[0]
    assert "storage_key" not in sample
    assert "created_by" not in sample
    assert "is_deleted" not in sample


# ---------------------------------------------------------------------------
# Test 2: list works without authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_no_auth_works(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public endpoint accepts requests with no Authorization header."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    await _create_attachment(db_session, company_id, staff_user)

    # No auth_headers passed.
    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments"
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 3: ?category= filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_category(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?category= returns only rows with the exact category path."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    await _create_attachment(
        db_session, company_id, staff_user,
        title="A", category="marketing/presentations",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="B", category="legal/incorporation",
    )

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments",
        params={"category": "legal/incorporation"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "B"


# ---------------------------------------------------------------------------
# Test 4: ?language= filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_language(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?language= returns only rows with that ISO code."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)

    await _create_attachment(
        db_session, company_id, staff_user,
        title="EN", category="marketing/presentations", language="en",
    )
    await _create_attachment(
        db_session, company_id, staff_user,
        title="DE", category="marketing/presentations", language="de",
    )

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments",
        params={"language": "de"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "DE"


# ---------------------------------------------------------------------------
# Test 5: download public returns 302 with working URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_public_returns_302(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public + published attachment -> 302 to a working presigned URL."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    payload = b"public deck bytes -- v1.2"
    attachment = await _create_attachment(
        db_session, company_id, staff_user,
        file_bytes=payload, content_type="application/pdf",
    )

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments/{attachment.id}/download",
        follow_redirects=False,
    )
    assert resp.status_code == 302, resp.text
    location = resp.headers.get("location")
    assert location and location.startswith("http")

    # Round 4 (SEC-01): Content-Disposition: attachment guard, same as
    # the auth-flow download test. Critical here because the public TTL
    # is 24h -- a leaked URL must not become a stored-XSS vector.
    assert "response-content-disposition" in location.lower()
    assert "attachment" in location.lower()

    async with httpx.AsyncClient() as http:
        follow = await http.get(location)
    assert follow.status_code == 200
    assert follow.content == payload
    cd = follow.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert "doc.pdf" in cd


# ---------------------------------------------------------------------------
# Test 6: download non-public -> 404 (not 403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_non_public_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Published but private attachment -> 404, not 403."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment(
        db_session, company_id, staff_user,
        is_public=False, is_published=True,
    )

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments/{attachment.id}/download",
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: download unpublished -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_unpublished_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public but unpublished attachment -> 404."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment(
        db_session, company_id, staff_user,
        is_public=True, is_published=False,
    )

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments/{attachment.id}/download",
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: download soft-deleted -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_deleted_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Public + published but soft-deleted -> 404 (filtered by get_attachment)."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment(db_session, company_id, staff_user)
    attachment.is_deleted = True
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments/{attachment.id}/download",
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 9: download under wrong company -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_other_company_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cross-company leak protection: A's attachment under B's URL -> 404."""
    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_a = await _create_company_via_api(client, admin_token, suffix="coA")
    company_b = await _create_company_via_api(client, admin_token, suffix="coB")
    attachment_a = await _create_attachment(db_session, company_a, staff_user)

    resp = await client.get(
        f"/api/v1/public/companies/{company_b}/attachments/{attachment_a.id}/download",
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 10: list rate-limit exceeded -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rate_limit_exceeded(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public list endpoint rejects with 400 once the per-IP cap is hit.

    Patches PUBLIC_LIST_RATE_LIMIT in the router module to (3, 60) so we
    only need 4 requests to prove the limiter fires. The autouse
    clear_rate_limits fixture wipes the Redis key beforehand, so the
    counter starts at zero for this test.
    """
    from app.modules.companies import attachments_public_router as pub
    monkeypatch.setattr(pub, "PUBLIC_LIST_RATE_LIMIT", (3, 60))

    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    await _create_attachment(db_session, company_id, staff_user)

    url = f"/api/v1/public/companies/{company_id}/attachments"

    # First three requests succeed.
    for i in range(3):
        resp = await client.get(url)
        assert resp.status_code == 200, f"request #{i + 1} failed: {resp.text}"

    # Fourth request -> 400 with the public-flow message.
    over = await client.get(url)
    assert over.status_code == 400, over.text
    body = over.json()
    assert "Too many requests" in body.get("message", "")


# ---------------------------------------------------------------------------
# Test 11: download rate-limit exceeded -> 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_rate_limit_exceeded(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public download endpoint rejects with 400 once the per-IP cap is hit."""
    from app.modules.companies import attachments_public_router as pub
    monkeypatch.setattr(pub, "PUBLIC_DOWNLOAD_RATE_LIMIT", (3, 60))

    staff_user, admin_token = await _admin_user_and_token(client, db_session)
    company_id = await _create_company_via_api(client, admin_token)
    attachment = await _create_attachment(db_session, company_id, staff_user)

    url = f"/api/v1/public/companies/{company_id}/attachments/{attachment.id}/download"

    for i in range(3):
        resp = await client.get(url, follow_redirects=False)
        assert resp.status_code == 302, f"request #{i + 1} failed: {resp.text}"

    over = await client.get(url, follow_redirects=False)
    assert over.status_code == 400, over.text
    body = over.json()
    assert "Too many requests" in body.get("message", "")
