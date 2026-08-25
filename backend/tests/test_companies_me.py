# =============================================================================
# AIVIS.ONE Backend -- PATCH /api/v1/companies/me Tests (TASK-30 ruling 10/12)
# =============================================================================
#
# Covers the TASK-30 DONE-TEST groups that apply to this endpoint:
#   C1 -- the project edits every one of its own editable fields, response
#         reflects the change.
#   C4 -- ISOLATION. No company_id in the URL, so the natural attack is:
#         company B calls PATCH /me, company A's row is unchanged. Must
#         never be skipped just because "there's no id to attack".
#   C5 -- admin-column rejection. A body carrying name / price_per_unit_cents
#         / total_supply / shares_per_option / distribution_config is
#         rejected 422 by the schema (extra="forbid"), not by ad-hoc service
#         logic. At least two fields are tested individually to show it is
#         the schema shape doing the rejecting, not a coincidence.
#   D1 -- ACTIVE -> HIDDEN succeeds.
#   D2 -- HIDDEN -> ACTIVE is refused (named 4xx, not 500, not a silent
#         no-op); ARCHIVED from this endpoint is also refused. Both shown
#         explicitly rather than assuming one implies the other.
#
# Company accounts are created the same way test_company_audit_feed.py
# creates them (POST /staff/companies as an admin), then logged in via
# the ordinary email/login endpoint to obtain that company's own token --
# company users are User rows with email/password credentials like any
# other, so /auth/email/login works unmodified for role=company.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user, login_user


async def _create_company_and_login(
    client: AsyncClient, admin_token: str
) -> tuple[str, str]:
    """POST /staff/companies, then log in as that company. Returns
    (company_id, company_session_token).
    """
    email = f"selfsvc_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"SelfServiceCo {uuid.uuid4().hex[:8]}",
            "description": "Original description",
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
    company_id = resp.json()["id"]

    login = await login_user(client, email=email, password=password)
    return company_id, login["session_token"]


async def _publish(client: AsyncClient, admin_token: str, company_id: str) -> None:
    """Staff-side PATCH to flip a freshly-created (HIDDEN) company to
    ACTIVE, so D1/D2 have something to move FROM.
    """
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


# ---------------------------------------------------------------------------
# C1: the project edits every one of its own editable fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_can_edit_all_own_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={
            "description": "New description",
            "logo_url": "https://example.com/logo.png",
            "cover_url": "https://example.com/cover.png",
            "promo_video_url": "https://example.com/promo.mp4",
            "presentation_url": "https://example.com/deck.pdf",
        },
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == company_id
    assert body["description"] == "New description"
    assert body["logo_url"] == "https://example.com/logo.png"
    assert body["cover_url"] == "https://example.com/cover.png"
    assert body["promo_video_url"] == "https://example.com/promo.mp4"
    assert body["presentation_url"] == "https://example.com/deck.pdf"

    # Confirm it round-trips via GET too, not just the PATCH response.
    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["description"] == "New description"


# ---------------------------------------------------------------------------
# C4: ISOLATION -- must never be skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_me_only_affects_callers_own_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No company_id in the URL, so the proof of isolation is: company B
    calling PATCH /me never touches company A's row, no matter what B
    sends.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a_id, company_a_token = await _create_company_and_login(
        client, admin_token
    )
    company_b_id, company_b_token = await _create_company_and_login(
        client, admin_token
    )
    assert company_a_id != company_b_id

    # Snapshot A's description before B acts.
    a_before = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_a_token)
    )
    assert a_before.status_code == 200, a_before.text
    original_description = a_before.json()["description"]

    # B updates its OWN profile with a distinctive value.
    b_resp = await client.patch(
        "/api/v1/companies/me",
        json={"description": "Company B was here"},
        headers=auth_headers(company_b_token),
    )
    assert b_resp.status_code == 200, b_resp.text
    assert b_resp.json()["id"] == company_b_id
    assert b_resp.json()["description"] == "Company B was here"

    # A's row must be completely unchanged.
    a_after = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_a_token)
    )
    assert a_after.status_code == 200, a_after.text
    assert a_after.json()["description"] == original_description
    assert a_after.json()["description"] != "Company B was here"
    assert a_after.json()["id"] == company_a_id


# ---------------------------------------------------------------------------
# C5: admin-column rejection -- schema shape, not coincidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_me_rejects_name_field(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={"name": "Hijacked Name"},
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 422, resp.text

    # Confirm nothing changed server-side.
    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert get_resp.json()["name"] != "Hijacked Name"


@pytest.mark.asyncio
async def test_patch_me_rejects_price_per_unit_cents_field(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={"price_per_unit_cents": 999_999},
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 422, resp.text

    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert get_resp.json()["price_per_unit_cents"] != 999_999


@pytest.mark.asyncio
async def test_patch_me_rejects_total_supply_shares_and_distribution_config(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Third and fourth admin-only fields, batched in one request --
    still a schema-level 422, still nothing changes.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={
            "total_supply": 2_000_000,
            "shares_per_option": 5,
            "distribution_config": {"company_pct": 0.9, "agent_levels": []},
        },
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 422, resp.text

    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    body = get_resp.json()
    assert body["total_supply"] != 2_000_000
    assert body["shares_per_option"] != 5
    assert body["distribution_config"] != {"company_pct": 0.9, "agent_levels": []}


# ---------------------------------------------------------------------------
# D1 / D2: publication direction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_can_hide_itself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """D1: ACTIVE -> HIDDEN succeeds."""
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)
    await _publish(client, admin_token, company_id)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={"status": "hidden"},
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "hidden"


@pytest.mark.asyncio
async def test_project_cannot_publish_or_archive_itself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """D2, explicit control: HIDDEN -> ACTIVE is refused with a named
    4xx (not a 500, not a silent no-op), and separately, requesting
    ARCHIVED from this endpoint is also refused. Both attempts are
    shown, not assumed to share one code path.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    # Company starts HIDDEN (create_company always mints status=HIDDEN).
    starting = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert starting.json()["status"] == "hidden"

    # Attempt 1: HIDDEN -> ACTIVE (publish) -- staff-only, must be refused.
    publish_attempt = await client.patch(
        "/api/v1/companies/me",
        json={"status": "active"},
        headers=auth_headers(company_token),
    )
    assert publish_attempt.status_code == 400, publish_attempt.text
    assert publish_attempt.status_code < 500

    still_hidden = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert still_hidden.json()["status"] == "hidden"

    # Attempt 2: HIDDEN -> ARCHIVED -- staff-only, must be refused.
    archive_attempt = await client.patch(
        "/api/v1/companies/me",
        json={"status": "archived"},
        headers=auth_headers(company_token),
    )
    assert archive_attempt.status_code == 400, archive_attempt.text
    assert archive_attempt.status_code < 500

    still_hidden_2 = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert still_hidden_2.json()["status"] == "hidden"

    # CONTROL: from ACTIVE, ACTIVE -> HIDDEN (the one legal direction)
    # still works on this same company -- proves the 400s above were the
    # direction check specifically, not the endpoint being broken.
    await _publish(client, admin_token, company_id)
    legal_attempt = await client.patch(
        "/api/v1/companies/me",
        json={"status": "hidden"},
        headers=auth_headers(company_token),
    )
    assert legal_attempt.status_code == 200, legal_attempt.text
    assert legal_attempt.json()["status"] == "hidden"
