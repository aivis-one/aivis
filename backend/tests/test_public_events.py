# =============================================================================
# CBSHOME Backend -- Public Events List Tests (iter 2.7b A)
# =============================================================================
#
# HTTP-level coverage for the 2.7b extensions to the PUBLIC events
# surface (posts/router.py events_router):
#   GET /api/v1/events?upcoming=true|false   -- time-window split
#   GET /api/v1/events           (no param)  -- backward-compat (DESC)
#   GET /api/v1/events/upcoming?limit=N      -- next N, soonest first
#
# Distinct from test_staff_content_list.py, which covers the STAFF
# events surface (drafts, content_manage gate). These tests exercise
# the anonymous public reader.
#
# Robustness contract (mirrors test_staff_content_list.py):
#   * The dev DB is shared and accumulates rows across runs. We never
#     assert "every item has X" -- only positive / negative probes on
#     specific row ids this test just created, plus RELATIVE ordering
#     between two of our own rows (never absolute list order, which
#     pre-existing rows would break).
#   * Titles are UUID-suffixed so a row is findable uniquely.
#   * Events are soft-deleted at most; once created they live until the
#     dev DB is wiped, so assertions stay scoped to this test's ids.
#
# Event creation goes through the staff POST endpoint (same as the
# staff-content tests) -- there is no public create path. is_published
# defaults vary per test; ends_at is omitted so the schema's
# ends_at > starts_at validator is side-stepped.
# =============================================================================

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


async def _admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Create an admin staff user and return their session token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_event(
    client: AsyncClient,
    admin_token: str,
    *,
    is_published: bool,
    starts_at: datetime,
    title: str | None = None,
) -> dict:
    """POST /api/v1/staff/events -> created EventResponse dict.

    `ends_at` is intentionally omitted (the schema only enforces
    ends_at > starts_at when both are present). Title is UUID-suffixed.
    """
    if title is None:
        title = f"PublicEvtTest {uuid.uuid4().hex[:10]}"
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


async def _walk_event_pages(
    client: AsyncClient,
    *,
    url: str,
) -> list[dict]:
    """Walk every page of the paginated public /events list.

    Returns the items in order across pages (so relative ordering of
    two known ids can be checked). Anonymous -- no headers. `url`
    carries any filter query string already; page/per_page appended.
    """
    items: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        resp = await client.get(f"{url}{sep}page={page}&per_page=100")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items.extend(body["items"])
        if len(body["items"]) < 100 or page * 100 >= body["total"]:
            break
        page += 1
    return items


def _index_of(items: list[dict], event_id: str) -> int:
    """Position of event_id in items, or -1 if absent."""
    for i, item in enumerate(items):
        if item["id"] == event_id:
            return i
    return -1


# ---------------------------------------------------------------------------
# 1: GET /events?upcoming=true -> future in (ASC), past out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_events_upcoming_true_future_only_asc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?upcoming=true returns only future published events, soonest
    first.

    Two future events with distinct starts_at probe ordering: the
    nearer one must appear BEFORE the farther one. A past event must
    not appear at all. Relative-order check is robust against any
    pre-existing rows between ours.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    near = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=5),
    )
    far = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=40),
    )
    past = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now - timedelta(days=5),
    )

    items = await _walk_event_pages(
        client, url="/api/v1/events?upcoming=true"
    )
    ids = {i["id"] for i in items}

    assert near["id"] in ids
    assert far["id"] in ids
    assert past["id"] not in ids, (
        f"Past event {past['id']} leaked into ?upcoming=true"
    )
    # ASC: near (+5d) must precede far (+40d).
    assert _index_of(items, near["id"]) < _index_of(items, far["id"]), (
        "upcoming=true must order ascending (nearer event first)"
    )


# ---------------------------------------------------------------------------
# 2: GET /events?upcoming=false -> past in (DESC), future out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_events_upcoming_false_past_only_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?upcoming=false returns only past published events, most recent
    first.

    Two past events probe DESC ordering: the more recent past event
    must appear BEFORE the older one. A future event must not appear.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    recent_past = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now - timedelta(days=5),
    )
    old_past = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now - timedelta(days=40),
    )
    future = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=5),
    )

    items = await _walk_event_pages(
        client, url="/api/v1/events?upcoming=false"
    )
    ids = {i["id"] for i in items}

    assert recent_past["id"] in ids
    assert old_past["id"] in ids
    assert future["id"] not in ids, (
        f"Future event {future['id']} leaked into ?upcoming=false"
    )
    # DESC: recent_past (-5d) must precede old_past (-40d).
    assert _index_of(items, recent_past["id"]) < _index_of(
        items, old_past["id"]
    ), "upcoming=false must order descending (more recent past first)"


# ---------------------------------------------------------------------------
# 3: GET /events (no param) -> backward-compat: both, DESC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_events_no_param_backward_compat_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Omitting ?upcoming reproduces pre-2.7b behaviour: published
    events regardless of time, ordered starts_at DESC.

    A future and a past event must BOTH appear, and the future event
    (later starts_at) must precede the past one under DESC.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    future = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=20),
    )
    past = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now - timedelta(days=20),
    )

    items = await _walk_event_pages(client, url="/api/v1/events")
    ids = {i["id"] for i in items}

    assert future["id"] in ids, "future event missing from unfiltered list"
    assert past["id"] in ids, "past event missing from unfiltered list"
    # DESC overall: future (+20d) precedes past (-20d).
    assert _index_of(items, future["id"]) < _index_of(items, past["id"]), (
        "unfiltered list must order starts_at DESC"
    )


# ---------------------------------------------------------------------------
# 4: GET /events?upcoming=true excludes drafts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_events_upcoming_excludes_drafts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A future DRAFT event must not appear in the public ?upcoming=true
    list -- the public surface filters is_published=True regardless of
    the time window.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    published = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=3),
    )
    draft = await _create_event(
        client, admin_token, is_published=False,
        starts_at=now + timedelta(days=3),
    )

    items = await _walk_event_pages(
        client, url="/api/v1/events?upcoming=true"
    )
    ids = {i["id"] for i in items}

    assert published["id"] in ids
    assert draft["id"] not in ids, (
        f"Draft event {draft['id']} leaked into public ?upcoming=true"
    )


# ---------------------------------------------------------------------------
# 5: GET /events/upcoming?limit=N -> next N, future-only, ASC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upcoming_endpoint_limit_future_only_asc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /events/upcoming?limit=N returns at most N future published
    events, soonest first.

    With limit large enough to include both our future events, the
    nearer must precede the farther, and a past event must be absent.
    A bare list (no pagination envelope) is returned.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    near = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=2),
    )
    far = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=50),
    )
    past = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now - timedelta(days=2),
    )

    # limit=50 (the ceiling) so both our future events fit regardless
    # of how many other rows the dev DB carries within that bound.
    resp = await client.get("/api/v1/events/upcoming?limit=50")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list), "upcoming endpoint returns a bare list"

    ids = [i["id"] for i in items]
    assert near["id"] in ids
    assert past["id"] not in ids, (
        f"Past event {past['id']} leaked into /events/upcoming"
    )
    # far may or may not be within the first 50 depending on dev-DB
    # volume; only assert relative order when both are present.
    if far["id"] in ids:
        assert ids.index(near["id"]) < ids.index(far["id"]), (
            "/events/upcoming must order ascending"
        )


# ---------------------------------------------------------------------------
# 6: GET /events/upcoming?limit=100 -> clamped to 50 (not 422)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upcoming_endpoint_limit_clamped_to_50(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """limit above the ceiling is clamped to 50, not rejected.

    The request must succeed (200, not 422) and return no more than
    50 items. We seed a couple of future events so the list is
    non-empty, but the assertion is purely on the cap + status.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=1),
    )
    await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(days=2),
    )

    resp = await client.get("/api/v1/events/upcoming?limit=100")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) <= 50, (
        f"limit=100 must clamp to 50, got {len(items)} items"
    )


# ---------------------------------------------------------------------------
# 7: GET /events/upcoming (no limit) -> default 3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upcoming_endpoint_default_limit_three(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """With no ?limit, the endpoint defaults to 3 items, and the
    earliest future event is among them.

    OBS-43-01: asserting only `len <= 3` is too weak -- if the dev DB
    already holds 3+ future events, all of this test's seeds could be
    pushed past the limit and the test would pass while verifying
    nothing about our own rows. To make the assertion meaningful we
    seed one event anchored just after now() (`near`), which under the
    ASC ordering is the earliest future event there can be (nothing
    realistic is scheduled in the next couple of minutes), so it is
    guaranteed to occupy one of the first 3 slots. The remaining seeds
    (further out) only exist to make the list longer than the cap.

    ANCHOR SLACK (flake fix): the anchor used to be now+1s, and on a
    loaded box the four HTTP round-trips between creating it and the
    GET took longer than that -- `near` slipped into the past, dropped
    out of /upcoming, and leftover future events from earlier tests
    filled the top-3. +2 minutes keeps it the earliest realistic
    future row (prior runs' anchors are already past, their fillers
    are days out) while giving the test ample execution slack.
    """
    admin_token = await _admin_token(client, db_session)
    now = datetime.now(UTC)

    # Earliest-future anchor with execution slack (see docstring).
    near = await _create_event(
        client, admin_token, is_published=True,
        starts_at=now + timedelta(minutes=2),
    )
    # Fillers further out so the unbounded list exceeds the default cap.
    for d in (2, 3, 4):
        await _create_event(
            client, admin_token, is_published=True,
            starts_at=now + timedelta(days=d),
        )

    resp = await client.get("/api/v1/events/upcoming")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) <= 3, (
        f"default limit must be 3, got {len(items)} items"
    )
    # The earliest future event must be in the (ASC) default page.
    assert near["id"] in [i["id"] for i in items], (
        "earliest future event missing from the default upcoming page -- "
        "default limit or ASC ordering is wrong"
    )
