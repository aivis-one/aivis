# =============================================================================
# AIVIS.ONE Backend -- Company Self-Service Posts Tests (TASK-30)
# =============================================================================
#
# GET/POST /api/v1/company/posts and PATCH/DELETE
# /api/v1/company/posts/{id} did not exist before this delivery -- see
# posts/company_router.py. These tests exercise the real endpoints
# end-to-end (never call posts/service.py functions directly), because
# the isolation guarantee ("company A cannot touch company B's post")
# is a route/auth-dependency property, not just a service-layer one.
#
# COMPANY LOGIN: POST /staff/companies (admin-only) creates a User with
# role=company plus a CompanyProfile in one call and returns the id;
# the email/password passed in are real login credentials -- login_user()
# authenticates as that company exactly like a real company rep would.
# Same pattern as test_company_audit_feed.py's _create_company helper.
#
# ROBUSTNESS: the dev/test DB can carry rows from other tests in the
# same run. Every assertion here is a positive/negative probe on this
# test's own row ids (never "the list has N items" or "every item
# matches"), same convention as test_public_events.py /
# test_staff_content_list.py.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user, login_user


async def _create_company(
    client: AsyncClient, admin_token: str
) -> tuple[str, str, str]:
    """POST /staff/companies -- returns (company_id, email, password)."""
    email = f"copost_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"CoPostCo {uuid.uuid4().hex[:8]}",
            "description": "Company posts test company",
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


async def _login_company(
    client: AsyncClient, email: str, password: str
) -> str:
    data = await login_user(client, email=email, password=password)
    return data["session_token"]


# ---------------------------------------------------------------------------
# 1: creates a post about itself, publish behaviour is real, not assumed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_published_company_post_is_publicly_readable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /company/posts with is_published=True shows up on the
    public feed (GET /api/v1/posts) and single-post endpoint
    (GET /api/v1/posts/{id}) immediately -- no moderation step.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    title = f"Published news {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/company/posts",
        json={
            "title": title,
            "body": "We shipped a thing.",
            "is_published": True,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    post = resp.json()
    assert post["owner_type"] == "company"
    assert post["owner_id"] == company_id
    assert post["is_published"] is True
    assert post["published_at"] is not None
    assert post["is_banner"] is False

    # Public single-post read.
    resp = await client.get(f"/api/v1/posts/{post['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == title

    # Public feed, filtered to this company -- positive probe.
    resp = await client.get(
        "/api/v1/posts", params={"owner_type": "company", "company_id": company_id}
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert post["id"] in ids


@pytest.mark.asyncio
async def test_unpublished_company_post_is_not_publicly_visible_until_patched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Omitting is_published defaults to False (real Post model default)
    and stays invisible on the public surface until the company itself
    PATCHes is_published=True -- exercises the real transition, not an
    assumption about defaults.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    resp = await client.post(
        "/api/v1/company/posts",
        json={"title": "Draft news", "body": "Not ready yet."},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    post = resp.json()
    assert post["is_published"] is False
    assert post["published_at"] is None

    # Public read: 404, both single and list.
    resp = await client.get(f"/api/v1/posts/{post['id']}")
    assert resp.status_code == 404, resp.text

    resp = await client.get(
        "/api/v1/posts", params={"owner_type": "company", "company_id": company_id}
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert post["id"] not in ids

    # But the company itself can see its own draft via GET /company/posts.
    resp = await client.get("/api/v1/company/posts", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert post["id"] in ids

    # Publish it.
    resp = await client.patch(
        f"/api/v1/company/posts/{post['id']}",
        json={"is_published": True},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_published"] is True
    assert resp.json()["published_at"] is not None

    resp = await client.get(f"/api/v1/posts/{post['id']}")
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2: isolation -- company A cannot touch company B's post (C4 done-test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_cannot_edit_or_delete_another_companys_post(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Company B's PATCH/DELETE against company A's post is refused
    (404, matching the attachments-router isolation contract), and A's
    post is left completely untouched.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a_id, email_a, password_a = await _create_company(client, admin_token)
    company_b_id, email_b, password_b = await _create_company(client, admin_token)
    token_a = await _login_company(client, email_a, password_a)
    token_b = await _login_company(client, email_b, password_b)

    original_title = f"A's own news {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/company/posts",
        json={"title": original_title, "body": "Body A", "is_published": True},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 201, resp.text
    post_a = resp.json()

    # B tries to edit A's post.
    resp = await client.patch(
        f"/api/v1/company/posts/{post_a['id']}",
        json={"title": "Hijacked by B"},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # B tries to delete A's post.
    resp = await client.delete(
        f"/api/v1/company/posts/{post_a['id']}",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text

    # A's post is untouched: title unchanged, still published, still
    # readable publicly (i.e. not soft-deleted by B's DELETE attempt).
    resp = await client.get(f"/api/v1/posts/{post_a['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == original_title
    assert resp.json()["owner_id"] == company_a_id

    # B's own list does not contain A's post either.
    resp = await client.get("/api/v1/company/posts", headers=auth_headers(token_b))
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert post_a["id"] not in ids


@pytest.mark.asyncio
async def test_company_create_post_request_rejects_owner_id_override(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CreateCompanyPostRequest has no owner_type/owner_id field at all
    (extra="forbid") -- a company literally cannot pass a different
    owner_id in the JSON body; the request is rejected at the schema
    layer (422) before any service code runs.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a_id, email_a, password_a = await _create_company(client, admin_token)
    company_b_id, _email_b, _password_b = await _create_company(client, admin_token)
    token_a = await _login_company(client, email_a, password_a)

    resp = await client.post(
        "/api/v1/company/posts",
        json={
            "title": "Trying to spoof owner",
            "body": "Body",
            "owner_id": company_b_id,
        },
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 3: platform / staff-owned posts are untouched by company self-service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_post_untouched_by_company_crud(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A platform post (owner_type="platform", created by staff) cannot
    be edited or deleted through /api/v1/company/posts/{id}, and does
    not appear in a company's own list.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    platform_title = f"Platform news {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": platform_title,
            "body": "System-wide announcement.",
            "is_published": True,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    platform_post = resp.json()
    assert platform_post["owner_id"] is None

    # The company cannot edit it.
    resp = await client.patch(
        f"/api/v1/company/posts/{platform_post['id']}",
        json={"title": "Hijacked"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404, resp.text

    # The company cannot delete it.
    resp = await client.delete(
        f"/api/v1/company/posts/{platform_post['id']}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404, resp.text

    # Not present in the company's own list.
    resp = await client.get("/api/v1/company/posts", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert platform_post["id"] not in ids

    # Still intact and publicly visible, untouched.
    resp = await client.get(f"/api/v1/posts/{platform_post['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == platform_title
    assert resp.json()["owner_type"] == "platform"


# ---------------------------------------------------------------------------
# 4: audit -- keyed to the company, so it surfaces in the admin feed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_post_write_appears_in_company_audit_feed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A company creating its own post writes an AuditLog row with
    target_type="company", target_id=<own company_id> (not
    target_type="post") -- so GET /api/v1/staff/audit/companies
    ?company_id=<id> (project_manage-gated) surfaces "what did this
    project write about itself", per the AUDIT DECISION documented in
    posts/service.py.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    resp = await client.post(
        "/api/v1/company/posts",
        json={"title": "Audited news", "body": "Body", "is_published": True},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    post_id = resp.json()["id"]

    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    matching = [
        item
        for item in resp.json()["items"]
        if item["event"] == "company.post_created"
    ]
    assert len(matching) == 1, resp.json()["items"]
    row = matching[0]
    assert row["company_id"] == company_id
    assert row["data"]["post_id"] == post_id
    assert row["actor_type"] == "user"
