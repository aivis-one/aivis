# =============================================================================
# AIVIS.ONE Backend -- Company Self-Service Roadmap Tests (TASK-30)
# =============================================================================
#
# GET/POST /api/v1/company/roadmap and PATCH/DELETE
# /api/v1/company/roadmap/{item_id} (+ /reorder, + /cover) did not exist
# before this delivery -- see companies/roadmap_company_router.py. These
# tests exercise the real endpoints end-to-end (never call
# companies/service.py functions directly), because the isolation
# guarantee ("company A cannot touch company B's roadmap item") is a
# route/auth-dependency property, not just a service-layer one. Mirrors
# tests/test_company_posts.py's structure exactly.
#
# COMPANY LOGIN: POST /staff/companies (admin-only) creates a User with
# role=company plus a CompanyProfile in one call and returns the id;
# the email/password passed in are real login credentials -- login_user()
# authenticates as that company exactly like a real company rep would.
#
# ROBUSTNESS: the dev/test DB can carry rows from other tests in the same
# run. Every assertion here is a positive/negative probe on this test's
# own row ids (never "the list has N items"), same convention as
# test_company_posts.py.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user, login_user


async def _create_company(client: AsyncClient, admin_token: str) -> tuple[str, str, str]:
    """POST /staff/companies -- returns (company_id, email, password)."""
    email = f"coroad_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"CoRoadCo {uuid.uuid4().hex[:8]}",
            "description": "Company roadmap test company",
            "price_per_unit_cents": 10_000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], email, password


async def _login_company(client: AsyncClient, email: str, password: str) -> str:
    data = await login_user(client, email=email, password=password)
    return data["session_token"]


# ---------------------------------------------------------------------------
# 1: C1 -- create / edit / reorder / delete its own roadmap, changes visible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_roadmap_full_crud_and_reorder_cycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A project creates two roadmap items, edits one, reorders both,
    then deletes one -- every change is immediately visible on
    GET /company/roadmap, which is the real read path this UI will use.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    # Starts empty.
    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # Create item 1 (milestone).
    title_1 = f"Milestone one {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/company/roadmap",
        json={"kind": "milestone", "title": title_1},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    item_1 = resp.json()
    assert item_1["kind"] == "milestone"
    assert item_1["status"] == "planned"
    assert item_1["order"] == 0

    # Create item 2 (announcement -- dateless, no status).
    title_2 = f"Announcement two {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/company/roadmap",
        json={"kind": "announcement", "title": title_2},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    item_2 = resp.json()
    assert item_2["order"] == 1

    # Both visible on the list, in order.
    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    ids_in_order = [row["id"] for row in resp.json()]
    assert ids_in_order == [item_1["id"], item_2["id"]]

    # Edit item 1's title + status.
    resp = await client.patch(
        f"/api/v1/company/roadmap/{item_1['id']}",
        json={"title": "Milestone one, updated", "status": "in_progress"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Milestone one, updated"
    assert resp.json()["status"] == "in_progress"

    # Reorder: item 2 first, item 1 second.
    resp = await client.patch(
        "/api/v1/company/roadmap/reorder",
        json={"item_ids": [item_2["id"], item_1["id"]]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    reordered_ids = [row["id"] for row in resp.json()]
    assert reordered_ids == [item_2["id"], item_1["id"]]

    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    ids_in_order = [row["id"] for row in resp.json()]
    assert ids_in_order == [item_2["id"], item_1["id"]]

    # Delete item 2 -- soft-deleted, disappears from the list.
    resp = await client.delete(
        f"/api/v1/company/roadmap/{item_2['id']}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204, resp.text

    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    remaining_ids = {row["id"] for row in resp.json()}
    assert remaining_ids == {item_1["id"]}


# ---------------------------------------------------------------------------
# 2: C4 isolation -- company A cannot touch company B's roadmap items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_cannot_edit_delete_or_reorder_another_companys_roadmap(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Company B's PATCH/DELETE/reorder against company A's roadmap item
    is refused with 404 (matching the attachments-router / company-posts
    isolation contract, never 403 -- existence of the row is not
    confirmed to B), and A's item is left completely untouched.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a_id, email_a, password_a = await _create_company(client, admin_token)
    company_b_id, email_b, password_b = await _create_company(client, admin_token)
    token_a = await _login_company(client, email_a, password_a)
    token_b = await _login_company(client, email_b, password_b)

    original_title = f"A's own milestone {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/company/roadmap",
        json={"kind": "milestone", "title": original_title},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 201, resp.text
    item_a = resp.json()

    # B tries to edit A's item.
    resp = await client.patch(
        f"/api/v1/company/roadmap/{item_a['id']}",
        json={"title": "Hijacked by B"},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to delete A's item.
    resp = await client.delete(
        f"/api/v1/company/roadmap/{item_a['id']}",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to upload a cover onto A's item.
    resp = await client.put(
        f"/api/v1/company/roadmap/{item_a['id']}/cover",
        files={"file": ("cover.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to reorder using A's item id mixed with nothing of its own
    # -- rejected as a set mismatch (400), not a silent success, and
    # definitely not able to move A's item.
    resp = await client.patch(
        "/api/v1/company/roadmap/reorder",
        json={"item_ids": [item_a["id"]]},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 400, resp.text

    # A's item is untouched: title unchanged, still present in A's own
    # list, still at order 0, no cover.
    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token_a))
    assert resp.status_code == 200, resp.text
    items_a = resp.json()
    assert len(items_a) == 1
    assert items_a[0]["id"] == item_a["id"]
    assert items_a[0]["title"] == original_title
    assert items_a[0]["cover_url"] is None

    # B's own list does not contain A's item.
    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token_b))
    assert resp.status_code == 200, resp.text
    ids_b = {row["id"] for row in resp.json()}
    assert item_a["id"] not in ids_b


# ---------------------------------------------------------------------------
# 3: per-kind validation still applies (schema is reused as-is, not
#    re-derived) -- a smoke check, full per-kind coverage already lives
#    in the staff-side roadmap tests since it's the SAME Pydantic schema.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_roadmap_event_requires_dates_in_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """kind=event without valid_until is rejected 422 (schema-level,
    CreateRoadmapItemRequest._check_kind_rules) -- confirms the company
    surface really is bound to the same schema as the staff surface,
    not a re-derived copy that could drift.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    resp = await client.post(
        "/api/v1/company/roadmap",
        json={"kind": "event", "title": "Missing dates", "target_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text

    # A well-formed event succeeds.
    resp = await client.post(
        "/api/v1/company/roadmap",
        json={
            "kind": "event",
            "title": "Well-formed event",
            "target_date": "2026-01-01",
            "valid_until": "2026-01-10",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "event"


# ---------------------------------------------------------------------------
# 4: audit -- keyed to the company, so it surfaces in the admin feed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_roadmap_write_appears_in_company_audit_feed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A company creating its own roadmap item writes an AuditLog row
    with target_type="company", target_id=<own company_id> (not
    target_type="roadmap_item") -- so
    GET /api/v1/staff/audit/companies?company_id=<id> (project_manage-
    gated) surfaces "what did this project write about itself", matching
    the convention update_own_company and posts/company_router.py both
    established for this feature.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    resp = await client.post(
        "/api/v1/company/roadmap",
        json={"kind": "milestone", "title": "Audited milestone"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    item_id = resp.json()["id"]

    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    matching = [
        row for row in resp.json()["items"] if row["event"] == "company.roadmap_item_created"
    ]
    assert len(matching) == 1, resp.json()["items"]
    row = matching[0]
    assert row["company_id"] == company_id
    assert row["data"]["item_id"] == item_id
    assert row["actor_type"] == "user"
