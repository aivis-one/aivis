# =============================================================================
# CBSHOME Backend -- Posts + Events Tests (Sprint 9.1)
# =============================================================================
#
# Tests cover:
#   1:  Staff creates platform post -> 201
#   2:  Staff creates company post -> 201, owner_id validated
#   3:  Staff creates post with non-existent company -> 404
#   4:  PATCH post -> 200, partial update
#   5:  DELETE post -> 204, soft delete (is_deleted=True)
#   6:  GET /posts -> 200, only published + not deleted
#   7:  GET /posts?owner_type=company&company_id=X -> filtered
#   8:  GET /posts/{id} -> 200
#   9:  POST /posts/{id}/dismiss -> 204, is_dismissed=True in listing
#   10: Staff creates event -> 201
#   11: GET /events/upcoming -> only next 30 days
#   12: Without content_manage -> 403
#
# Email prefix: "s91_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.posts.models import Event, Post, PostDismiss
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    create_staff_user,
    register_user,
)

EMAIL_PREFIX = "s91_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test data before and after each test."""
    await _cleanup_posts(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await _cleanup_posts(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _cleanup_posts(session: AsyncSession) -> None:
    """Delete all test posts/events (by title prefix)."""
    from sqlalchemy import delete

    # Posts.
    stmt = select(Post.id).where(Post.title.startswith("Test:"))
    result = await session.execute(stmt)
    post_ids = [row[0] for row in result.all()]

    if post_ids:
        await session.execute(
            delete(PostDismiss).where(PostDismiss.post_id.in_(post_ids))
        )
        await session.execute(
            delete(Post).where(Post.id.in_(post_ids))
        )

    # Events.
    await session.execute(
        delete(Event).where(Event.title.startswith("Test:"))
    )

    await session.commit()


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company(
    client: AsyncClient, admin_token: str, suffix: str = "co1"
) -> dict:
    """Helper: create a company via staff endpoint.

    Sprint 4.3 (B2.1 hotfix): total_supply / shares_per_option are now
    required by CreateCompanyRequest. test_posts.py never creates products
    against these companies, so no OptionPool is needed -- supply fields
    alone unblock the schema.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": 10000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            # Sprint 4.3:
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# 1: Staff creates platform post -> 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_platform_post(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/posts -> 201 for platform post."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: platform news",
            "body": "Platform announcement body",
            "is_published": True,
            "is_banner": True,
            "tags": ["news", "platform"],
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner_type"] == "platform"
    assert body["owner_id"] is None
    assert body["title"] == "Test: platform news"
    assert body["is_published"] is True
    assert body["is_banner"] is True
    assert body["published_at"] is not None
    assert body["tags"] == ["news", "platform"]


# ---------------------------------------------------------------------------
# 2: Staff creates company post -> 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_company_post(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/posts -> 201 for company post with valid owner_id."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    company_id = company["id"]

    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "company",
            "owner_id": company_id,
            "title": "Test: company blog",
            "body": "Company news body",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner_type"] == "company"
    assert body["owner_id"] == company_id


# ---------------------------------------------------------------------------
# 3: Company post with non-existent company -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_post_invalid_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/posts -> 404 when owner_id references non-existent company."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "company",
            "owner_id": str(uuid4()),
            "title": "Test: invalid company",
            "body": "Should fail",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4: PATCH post -> 200, partial update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_post(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH /staff/posts/{id} -> 200, partial update works."""
    admin_token = await _admin_token(client, db_session)

    # Create.
    create_resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: before update",
            "body": "Original body",
        },
        headers=auth_headers(admin_token),
    )
    post_id = create_resp.json()["id"]

    # Update title only.
    resp = await client.patch(
        f"/api/v1/staff/posts/{post_id}",
        json={"title": "Test: after update"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Test: after update"
    assert body["body"] == "Original body"  # Unchanged.


# ---------------------------------------------------------------------------
# 5: DELETE post -> 204, soft delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_post_soft(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE /staff/posts/{id} -> 204, is_deleted=True in DB."""
    admin_token = await _admin_token(client, db_session)

    create_resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: to delete",
            "body": "Will be soft-deleted",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    post_id = create_resp.json()["id"]

    # Delete.
    resp = await client.delete(
        f"/api/v1/staff/posts/{post_id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Verify in DB.
    stmt = select(Post).where(Post.id == UUID(post_id))
    result = await db_session.execute(stmt)
    post = result.scalar_one()
    assert post.is_deleted is True

    # Public GET should not find it.
    get_resp = await client.get(f"/api/v1/posts/{post_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 6: GET /posts -> only published + not deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_posts_published_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /posts -> 200, only published and not deleted posts."""
    admin_token = await _admin_token(client, db_session)

    # Create published post.
    await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: published",
            "body": "Visible",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    # Create unpublished post.
    await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: draft",
            "body": "Hidden",
            "is_published": False,
        },
        headers=auth_headers(admin_token),
    )

    resp = await client.get("/api/v1/posts")
    assert resp.status_code == 200
    body = resp.json()

    titles = [item["title"] for item in body["items"]]
    assert "Test: published" in titles
    assert "Test: draft" not in titles


# ---------------------------------------------------------------------------
# 7: GET /posts with filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_posts_filtered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /posts?owner_type=company&company_id=X -> filtered results."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, suffix="filter1")
    company_id = company["id"]

    # Create company post.
    await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "company",
            "owner_id": company_id,
            "title": "Test: company filtered",
            "body": "Company post",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    # Create platform post.
    await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: platform filtered",
            "body": "Platform post",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )

    # Filter by company.
    resp = await client.get(
        f"/api/v1/posts?owner_type=company&company_id={company_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["owner_type"] == "company"
        assert item["owner_id"] == company_id


# ---------------------------------------------------------------------------
# 8: GET /posts/{id} -> 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_post_detail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /posts/{id} -> 200 with full post data."""
    admin_token = await _admin_token(client, db_session)

    create_resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: detail view",
            "body": "Detailed body content",
            "is_published": True,
            "tags": ["detail"],
        },
        headers=auth_headers(admin_token),
    )
    post_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/posts/{post_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == post_id
    assert body["title"] == "Test: detail view"
    assert body["is_dismissed"] is False


# ---------------------------------------------------------------------------
# 9: POST /posts/{id}/dismiss -> 204, is_dismissed in listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_post(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /posts/{id}/dismiss -> 204. Listing shows is_dismissed=True."""
    admin_token = await _admin_token(client, db_session)

    # Create banner post.
    create_resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: dismissable banner",
            "body": "Banner body",
            "is_published": True,
            "is_banner": True,
        },
        headers=auth_headers(admin_token),
    )
    post_id = create_resp.json()["id"]

    # Register an investor to dismiss.
    investor_data = await register_user(
        client, email=f"{EMAIL_PREFIX}dismiss1@example.com"
    )
    investor_token = investor_data["session_token"]

    # Dismiss.
    resp = await client.post(
        f"/api/v1/posts/{post_id}/dismiss",
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 204

    # Verify in listing.
    list_resp = await client.get(
        "/api/v1/posts",
        headers=auth_headers(investor_token),
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    dismissed_post = next((p for p in items if p["id"] == post_id), None)
    assert dismissed_post is not None
    assert dismissed_post["is_dismissed"] is True

    # Idempotent: second dismiss also 204.
    resp2 = await client.post(
        f"/api/v1/posts/{post_id}/dismiss",
        headers=auth_headers(investor_token),
    )
    assert resp2.status_code == 204


# ---------------------------------------------------------------------------
# 10: Staff creates event -> 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/events -> 201."""
    admin_token = await _admin_token(client, db_session)

    starts_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()

    resp = await client.post(
        "/api/v1/staff/events",
        json={
            "title": "Test: webinar",
            "description": "Monthly webinar",
            "starts_at": starts_at,
            "location": "Zoom",
            "url": "https://zoom.us/meeting",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Test: webinar"
    assert body["location"] == "Zoom"
    assert body["is_published"] is True


# ---------------------------------------------------------------------------
# 11: GET /events/upcoming -> only next 30 days
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upcoming_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /events/upcoming -> only events within 30 days."""
    admin_token = await _admin_token(client, db_session)

    # Event in 5 days (should appear).
    soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    await client.post(
        "/api/v1/staff/events",
        json={
            "title": "Test: soon event",
            "starts_at": soon,
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    # Event in 60 days (should NOT appear).
    far = (datetime.now(UTC) + timedelta(days=60)).isoformat()
    await client.post(
        "/api/v1/staff/events",
        json={
            "title": "Test: far event",
            "starts_at": far,
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )

    resp = await client.get("/api/v1/events/upcoming")
    assert resp.status_code == 200
    titles = [e["title"] for e in resp.json()]
    assert "Test: soon event" in titles
    assert "Test: far event" not in titles


# ---------------------------------------------------------------------------
# 12: Without content_manage -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_content_manage_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff without content_manage -> 403 on POST /staff/posts."""
    # Create staff with content_manage=False.
    _, token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}noperm@example.com"
    )

    # Override permission in DB.
    from app.modules.staff.models import StaffProfile
    stmt = select(StaffProfile).where(
        StaffProfile.user_id == UUID(
            (await client.get(
                "/api/v1/users/me",
                headers=auth_headers(token),
            )).json()["id"]
        )
    )
    result = await db_session.execute(stmt)
    profile = result.scalar_one()
    perms = dict(profile.permissions)
    perms["content_manage"] = False
    profile.set_jsonb("permissions", perms)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": "Test: should fail",
            "body": "No permission",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
