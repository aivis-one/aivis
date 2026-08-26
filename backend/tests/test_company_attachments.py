# =============================================================================
# AIVIS.ONE Backend -- Company Self-Service Attachments Tests (TASK-30)
# =============================================================================
#
# GET/POST /api/v1/company/attachments and PATCH/DELETE
# /api/v1/company/attachments/{attachment_id} (+ /reorder, + /replace) did
# not exist before this delivery -- see
# companies/attachments_company_router.py. These tests exercise the real
# endpoints end-to-end (never call companies/service.py functions
# directly), because the isolation guarantee ("company A cannot touch
# company B's attachment") is a route/auth-dependency property, not just
# a service-layer one. Mirrors tests/test_company_roadmap.py's structure
# exactly.
#
# UPLOADS: the C1 happy-path test drives the real multipart POST endpoint
# (that IS the thing under test -- "project uploads its own attachment"),
# so it depends on a reachable MinIO the same way the roadmap cover
# upload flow does. The C4 isolation test needs exactly one real
# attachment (on company A, to attack from company B) and reuses the same
# real POST for it, mirroring test_company_roadmap.py's C4 test which
# creates its target row the same way. Every other setup need (the C4
# probes themselves, the hard-delete-route-absent check) touches no
# storage at all -- get_attachment's company_id scoping 404s before any
# MinIO call happens.
#
# COMPANY LOGIN: POST /staff/companies (admin-only) creates a User with
# role=company plus a CompanyProfile in one call and returns the id;
# the email/password passed in are real login credentials -- login_user()
# authenticates as that company exactly like a real company rep would.
#
# ROBUSTNESS: the dev/test DB can carry rows from other tests in the same
# run. Every assertion here is a positive/negative probe on this test's
# own row ids (never "the list has N items"), same convention as
# test_company_roadmap.py / test_company_posts.py.
# =============================================================================

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user, login_user


async def _create_company(client: AsyncClient, admin_token: str) -> tuple[str, str, str]:
    """POST /staff/companies -- returns (company_id, email, password)."""
    email = f"coatt_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"CoAttCo {uuid.uuid4().hex[:8]}",
            "description": "Company attachments test company",
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


async def _upload_attachment(
    client: AsyncClient,
    token: str,
    *,
    title: str,
    category: str = "legal/incorporation",
    order: int = 0,
    filename: str = "doc.pdf",
    content: bytes = b"%PDF-1.4\n%fake attachment for tests\n",
    content_type: str = "application/pdf",
    is_published: bool = False,
    is_public: bool = False,
):
    """POST /api/v1/company/attachments -- multipart create.

    Returns the raw httpx Response (not the parsed body) so callers can
    assert on status_code before calling .json() -- mirrors every other
    inline `resp = await client.post(...)` call site in this file rather
    than hiding the status check inside the helper.

    `order` is passed explicitly (rather than relying on the schema's
    default of 0) because the default lands every new upload at the TOP
    of its category (shift_orders_to_make_room pushes existing rows
    down) -- a stack, not a queue. Tests that create two attachments and
    expect them to land in creation order must set order=0 then order=1
    explicitly, or the second upload will push the first one down.
    """
    metadata = {
        "title": title,
        "category": category,
        "order": order,
        "is_published": is_published,
        "is_public": is_public,
    }
    resp = await client.post(
        "/api/v1/company/attachments",
        data={"metadata": json.dumps(metadata)},
        files={"file": (filename, content, content_type)},
        headers=auth_headers(token),
    )
    return resp


# ---------------------------------------------------------------------------
# 1: C1 -- upload / edit / reorder / replace / soft-delete its own attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_attachments_full_crud_and_reorder_cycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A project uploads two attachments in one category, edits one's
    metadata, reorders both, replaces the other's file, then soft-deletes
    one -- every change is immediately visible on GET /company/attachments,
    the real read path this UI will use.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    # Starts empty.
    resp = await client.get("/api/v1/company/attachments", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # Upload attachment 1 (order=0).
    title_1 = f"Cert of incorporation {uuid.uuid4().hex[:8]}"
    resp = await _upload_attachment(client, token, title=title_1, order=0)
    assert resp.status_code == 201, resp.text
    att_1 = resp.json()
    assert att_1["title"] == title_1
    assert att_1["category"] == "legal/incorporation"
    assert att_1["language"] == "en"
    assert att_1["order"] == 0
    assert att_1["is_published"] is False
    assert att_1["is_public"] is False
    assert att_1["original_filename"] == "doc.pdf"
    assert att_1["mime_type"] == "application/pdf"
    # Plain AttachmentResponse: no storage_key / created_by_id / is_deleted
    # leak onto this surface.
    assert "storage_key" not in att_1
    assert "created_by_id" not in att_1
    assert "is_deleted" not in att_1

    # Upload attachment 2 in the same category (order=1, so it lands
    # after attachment 1 rather than pushing it down).
    title_2 = f"Business license {uuid.uuid4().hex[:8]}"
    resp = await _upload_attachment(
        client, token, title=title_2, order=1, filename="license.pdf"
    )
    assert resp.status_code == 201, resp.text
    att_2 = resp.json()
    assert att_2["order"] == 1

    # Both visible on the list, in order.
    resp = await client.get("/api/v1/company/attachments", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    ids_in_order = [row["id"] for row in resp.json()]
    assert ids_in_order == [att_1["id"], att_2["id"]]

    # Edit attachment 1's metadata: title + publish it.
    resp = await client.patch(
        f"/api/v1/company/attachments/{att_1['id']}",
        json={"title": "Cert of incorporation, updated", "is_published": True},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Cert of incorporation, updated"
    assert resp.json()["is_published"] is True

    # Reorder: attachment 2 first, attachment 1 second.
    resp = await client.patch(
        "/api/v1/company/attachments/reorder",
        json={
            "category": "legal/incorporation",
            "item_ids": [att_2["id"], att_1["id"]],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 204, resp.text

    resp = await client.get("/api/v1/company/attachments", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    ids_in_order = [row["id"] for row in resp.json()]
    assert ids_in_order == [att_2["id"], att_1["id"]]

    # Replace attachment 2's file.
    resp = await client.patch(
        f"/api/v1/company/attachments/{att_2['id']}/replace",
        files={"file": ("license-v2.pdf", b"%PDF-1.4\nreplacement bytes\n", "application/pdf")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    replaced = resp.json()
    assert replaced["original_filename"] == "license-v2.pdf"
    assert replaced["title"] == title_2  # metadata untouched by replace

    # Soft-delete attachment 1 -- disappears from the list.
    resp = await client.delete(
        f"/api/v1/company/attachments/{att_1['id']}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204, resp.text

    resp = await client.get("/api/v1/company/attachments", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    remaining_ids = {row["id"] for row in resp.json()}
    assert remaining_ids == {att_2["id"]}


# ---------------------------------------------------------------------------
# 2: C4 isolation -- company A cannot touch company B's attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_cannot_edit_delete_replace_or_reorder_another_companys_attachment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Company B's PATCH/replace/DELETE/reorder against company A's
    attachment is refused with 404 (matching the staff attachments
    router / company-roadmap / company-posts isolation contract, never
    403 -- existence of the row is not confirmed to B), and A's
    attachment is left completely untouched.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a_id, email_a, password_a = await _create_company(client, admin_token)
    company_b_id, email_b, password_b = await _create_company(client, admin_token)
    token_a = await _login_company(client, email_a, password_a)
    token_b = await _login_company(client, email_b, password_b)

    original_title = f"A's own attachment {uuid.uuid4().hex[:8]}"
    resp = await _upload_attachment(client, token_a, title=original_title, order=0)
    assert resp.status_code == 201, resp.text
    att_a = resp.json()

    # B tries to edit A's attachment metadata.
    resp = await client.patch(
        f"/api/v1/company/attachments/{att_a['id']}",
        json={"title": "Hijacked by B"},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to replace A's attachment's file.
    resp = await client.patch(
        f"/api/v1/company/attachments/{att_a['id']}/replace",
        files={"file": ("hijack.pdf", b"%PDF-1.4\nhijack\n", "application/pdf")},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to delete A's attachment.
    resp = await client.delete(
        f"/api/v1/company/attachments/{att_a['id']}",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to reorder using A's attachment id -- rejected as a set
    # mismatch (400, B has nothing in this category), not a silent
    # success, and definitely not able to move A's attachment.
    resp = await client.patch(
        "/api/v1/company/attachments/reorder",
        json={"category": "legal/incorporation", "item_ids": [att_a["id"]]},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 400, resp.text

    # A's attachment is untouched: title unchanged, still present in A's
    # own list, still original filename.
    resp = await client.get("/api/v1/company/attachments", headers=auth_headers(token_a))
    assert resp.status_code == 200, resp.text
    items_a = resp.json()
    assert len(items_a) == 1
    assert items_a[0]["id"] == att_a["id"]
    assert items_a[0]["title"] == original_title
    assert items_a[0]["original_filename"] == "doc.pdf"

    # B's own list does not contain A's attachment.
    resp = await client.get("/api/v1/company/attachments", headers=auth_headers(token_b))
    assert resp.status_code == 200, resp.text
    ids_b = {row["id"] for row in resp.json()}
    assert att_a["id"] not in ids_b


# ---------------------------------------------------------------------------
# 3: hard-delete is genuinely absent from this router -- not merely
#    unauthorized, unroutable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_attachments_hard_delete_route_does_not_exist(
    client: AsyncClient,
) -> None:
    """DELETE /api/v1/company/attachments/{id}/hard has no route on this
    router at all (unlike the staff surface, which has one gated behind
    project_manage + is_admin()). A request to that path 404s the same
    way any unmatched route would -- BEFORE any auth dependency runs, so
    this is checked with NO Authorization header at all: if the route
    existed, an unauthenticated request would 401, not 404. Getting 404
    here confirms the path itself is unroutable, not merely gated.
    """
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/v1/company/attachments/{fake_id}/hard")
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# 4: audit -- keyed to the company, so it surfaces in the admin feed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_attachment_write_appears_in_company_audit_feed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A company uploading its own attachment writes an AuditLog row with
    target_type="company", target_id=<own company_id> (not
    target_type="attachment") -- so
    GET /api/v1/staff/audit/companies?company_id=<id> (project_manage-
    gated) surfaces "what did this project write about itself", matching
    the convention update_own_company, posts/company_router.py, and
    roadmap_company_router.py all established for this feature.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    resp = await _upload_attachment(client, token, title="Audited attachment", order=0)
    assert resp.status_code == 201, resp.text
    attachment_id = resp.json()["id"]

    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    matching = [
        row for row in resp.json()["items"] if row["event"] == "company.attachment_created"
    ]
    assert len(matching) == 1, resp.json()["items"]
    row = matching[0]
    assert row["company_id"] == company_id
    assert row["data"]["attachment_id"] == attachment_id
    assert row["actor_type"] == "user"
