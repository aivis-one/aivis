# =============================================================================
# AIVIS.ONE Backend -- Staff Content List Tests (iter 2.6c B4)
# =============================================================================
#
# HTTP-level smoke coverage for two new endpoints:
#   GET /api/v1/staff/posts
#   GET /api/v1/staff/events
#
# Tests cover:
#   1: GET /staff/posts surfaces drafts; public /posts does not
#   2: ?is_published=false filter -- positive + negative probes
#   3: GET /staff/events surfaces drafts; public /events does not
#   4: ?upcoming filter splits future / past correctly
#   5: GET /staff/posts forbidden for investor (no content_manage)
#   6: GET /staff/events forbidden for investor (no content_manage)
#
# Robustness contract (mirrors B1 / B2 / B3 notes):
#   * The dev DB is shared across runs. We never assert "every item has
#     X" -- only positive + negative probes on specific row ids.
#   * All titles are UUID-suffixed so no test collides with another
#     test's body / lookup.
#   * Post and Event are soft-deleted at most -- once created in a
#     test run they live until install_aivis.sh wipes the dev DB,
#     so we MUST scope assertions to rows this test just made.
#
# Email prefix:
#   Investor probe -- default "test_<uuid>" from register_user.
# =============================================================================

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin staff user and return their session token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_post(
    client: AsyncClient,
    admin_token: str,
    *,
    is_published: bool,
    title: str | None = None,
) -> dict:
    """POST /api/v1/staff/posts. Returns the created PostResponse.

    Owner type is platform (no company FK needed for these tests).
    Title carries a UUID suffix so we can find the row uniquely.
    """
    if title is None:
        title = f"StaffListPost {uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": title,
            "body": "Body content for staff list test.",
            "is_published": is_published,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_event(
    client: AsyncClient,
    admin_token: str,
    *,
    is_published: bool,
    starts_at: datetime,
    title: str | None = None,
) -> dict:
    """POST /api/v1/staff/events. Returns the created EventResponse.

    `starts_at` is passed through as an ISO-8601 string. `ends_at`
    is intentionally omitted -- the schema validator only enforces
    ends_at > starts_at when both are supplied, so we side-step the
    constraint by leaving ends_at NULL.
    """
    if title is None:
        title = f"StaffListEvent {uuid.uuid4().hex[:10]}"
    resp = await client.post(
        "/api/v1/staff/events",
        json={
            "title": title,
            "starts_at": starts_at.isoformat(),
            "is_published": is_published,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _walk_pages(
    client: AsyncClient,
    *,
    url: str,
    headers: dict[str, str],
) -> set[str]:
    """Walk every page of a paginated GET; collect item ids.

    `url` is the base URL with any filter query string already in
    place. We append `page=N&per_page=100` -- the dev DB may already
    hold hundreds of staff-side posts / events from prior runs, so
    walking all pages is the only way to be sure a specific row is
    or isn't on the list.
    """
    found: set[str] = set()
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        resp = await client.get(
            f"{url}{sep}page={page}&per_page=100",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        found.update(item["id"] for item in body["items"])
        if len(body["items"]) < 100 or page * 100 >= body["total"]:
            break
        page += 1
    return found


# ---------------------------------------------------------------------------
# 1: GET /staff/posts surfaces drafts; /posts (public) does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_posts_includes_drafts_public_excludes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stage one published post and one draft. Staff sees both, public
    sees only the published one.

    Positive + negative probe on the draft.id is the contract:
      * staff list contains draft.id;
      * public list does NOT contain draft.id.
    This is what differentiates the new endpoint from the public one.
    """
    admin_token = await _admin_token(client, db_session)

    published = await _create_post(
        client, admin_token, is_published=True
    )
    draft = await _create_post(
        client, admin_token, is_published=False
    )

    staff_ids = await _walk_pages(
        client,
        url="/api/v1/staff/posts",
        headers=auth_headers(admin_token),
    )
    assert published["id"] in staff_ids
    assert draft["id"] in staff_ids, (
        f"Draft post {draft['id']} missing from /staff/posts -- "
        f"staff endpoint should not filter on is_published"
    )

    # Public endpoint -- anonymous; published only.
    public_ids = await _walk_pages(
        client,
        url="/api/v1/posts",
        headers={},
    )
    assert published["id"] in public_ids
    assert draft["id"] not in public_ids, (
        f"Draft post {draft['id']} leaked into the public /posts "
        f"list -- public router should filter is_published=True"
    )


# ---------------------------------------------------------------------------
# 2: ?is_published=false returns only drafts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_posts_filter_is_published_false(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?is_published=false includes the draft, excludes the published.

    Positive + negative probe on our own ids -- robust against any
    pre-existing draft / published rows in the dev DB.
    """
    admin_token = await _admin_token(client, db_session)

    published = await _create_post(
        client, admin_token, is_published=True
    )
    draft = await _create_post(
        client, admin_token, is_published=False
    )

    draft_ids = await _walk_pages(
        client,
        url="/api/v1/staff/posts?is_published=false",
        headers=auth_headers(admin_token),
    )
    assert draft["id"] in draft_ids
    assert published["id"] not in draft_ids, (
        f"Published post {published['id']} leaked into "
        f"?is_published=false page"
    )


# ---------------------------------------------------------------------------
# 3: GET /staff/events surfaces drafts; /events (public) does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_events_includes_drafts_public_excludes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Same shape as test 1 but for events.

    starts_at is anchored in the near future so neither event drops
    off any time-based filter that other tests might monkey-patch.
    """
    admin_token = await _admin_token(client, db_session)
    starts_at = datetime.now(UTC) + timedelta(days=7)

    published = await _create_event(
        client, admin_token, is_published=True, starts_at=starts_at
    )
    draft = await _create_event(
        client, admin_token, is_published=False, starts_at=starts_at
    )

    staff_ids = await _walk_pages(
        client,
        url="/api/v1/staff/events",
        headers=auth_headers(admin_token),
    )
    assert published["id"] in staff_ids
    assert draft["id"] in staff_ids, (
        f"Draft event {draft['id']} missing from /staff/events -- "
        f"staff endpoint should not filter on is_published"
    )

    public_ids = await _walk_pages(
        client,
        url="/api/v1/events",
        headers={},
    )
    assert published["id"] in public_ids
    assert draft["id"] not in public_ids, (
        f"Draft event {draft['id']} leaked into the public /events "
        f"list -- public router should filter is_published=True"
    )


# ---------------------------------------------------------------------------
# 4: ?upcoming filter splits future / past
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_events_filter_upcoming_split(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?upcoming=true -> future event in, past event out.
       ?upcoming=false -> past in, future out.

    Two published events (one future, one past) keep the assertion
    robust against any pre-existing rows: we only check that OUR ids
    fall on the correct side of the split. Note that the public
    /events endpoint orders by starts_at DESC -- staff endpoint with
    upcoming=true orders ASC, but we are not asserting ordering
    here, only membership.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)
    future = await _create_event(
        client,
        admin_token,
        is_published=True,
        starts_at=now + timedelta(days=14),
    )
    past = await _create_event(
        client,
        admin_token,
        is_published=True,
        starts_at=now - timedelta(days=14),
    )

    # upcoming=true: future must be present, past must not.
    upcoming_ids = await _walk_pages(
        client,
        url="/api/v1/staff/events?upcoming=true",
        headers=auth_headers(admin_token),
    )
    assert future["id"] in upcoming_ids
    assert past["id"] not in upcoming_ids, (
        f"Past event {past['id']} leaked into ?upcoming=true page"
    )

    # upcoming=false: past must be present, future must not.
    past_ids = await _walk_pages(
        client,
        url="/api/v1/staff/events?upcoming=false",
        headers=auth_headers(admin_token),
    )
    assert past["id"] in past_ids
    assert future["id"] not in past_ids, (
        f"Future event {future['id']} leaked into ?upcoming=false page"
    )


# ---------------------------------------------------------------------------
# 5: GET /staff/posts forbidden for non-staff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_posts_forbidden_for_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor with no staff profile -> 403 on GET /staff/posts.

    require_staff_permission("content_manage") fails fast at the
    dependency layer; no list query runs.
    """
    inv_data = await register_user(client)
    inv_token = inv_data["session_token"]

    resp = await client.get(
        "/api/v1/staff/posts",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 6: GET /staff/events forbidden for non-staff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_events_forbidden_for_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor with no staff profile -> 403 on GET /staff/events."""
    inv_data = await register_user(client)
    inv_token = inv_data["session_token"]

    resp = await client.get(
        "/api/v1/staff/events",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403, resp.text
