# =============================================================================
# AIVIS.ONE Backend -- Company Audit Feed Tests (TASK-30 ruling 3 / F2)
# =============================================================================
#
# GET /api/v1/staff/audit/companies did not exist before this delivery,
# and nothing in this tree yet calls record_audit() from a project
# self-service write path (that lands in separate, later work). So
# there is no real write endpoint to exercise end-to-end here.
#
# Instead this file:
#   1. Calls record_audit() directly -- the same call a future
#      self-service write endpoint will make -- to seed one
#      target_type="company" row for a real CompanyProfile.
#   2. Asserts the feed endpoint returns that row with the right
#      shape (id, company_id, event, actor fields, data, created_at).
#   3. Asserts date-range and company_id filtering both work via
#      positive + negative probes (never "all items match" -- the
#      dev/test DB may carry other companies' audit rows), mirroring
#      test_staff_companies_list.py's ?search= probe pattern.
#   4. The two-sided permission control, same shape as
#      test_create_company_requires_project_manage in
#      test_staff_companies_list.py: staff WITH project_manage -> 200
#      with the row; staff WITHOUT it -> 403. The 403 alone would only
#      prove *something* failed -- pairing it with a succeeding call
#      on an otherwise-identical account proves project_manage
#      specifically is the gate.
# =============================================================================

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.core.audit import record_audit
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS
from app.modules.staff.models import StaffProfile
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user, create_staff_user


async def _set_project_manage(
    db_session: AsyncSession, user_id: uuid.UUID, value: bool
) -> None:
    """Flip project_manage on an existing StaffProfile.

    Copied from test_staff_companies_list.py's helper of the same name
    -- kept local rather than imported since it is test-file-private
    glue, not a shared fixture.
    """
    profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user_id)
        )
    ).scalar_one()
    perms = dict(DEFAULT_STAFF_PERMISSIONS)
    perms["project_manage"] = value
    profile.set_jsonb("permissions", perms)
    await db_session.commit()


async def _create_company(client: AsyncClient, admin_token: str) -> str:
    """POST /staff/companies -- returns the new company's id."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"audit_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"AuditFeedCo {uuid.uuid4().hex[:8]}",
            "description": "Company audit feed test company",
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
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1: record_audit() entry appears in the feed with the right shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recorded_entry_appears_in_feed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A row written by record_audit(target_type="company", ...) shows
    up in GET /staff/audit/companies?company_id=<id>, with actor_id,
    actor_type, event, and data all round-tripping correctly.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id = await _create_company(client, admin_token)

    entry = await record_audit(
        session=db_session,
        event="company.description_updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"before": "old text", "after": "new text"},
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    matching = [item for item in body["items"] if item["id"] == str(entry.id)]
    assert len(matching) == 1, (
        f"seeded entry {entry.id} missing from feed for company "
        f"{company_id}: {body['items']}"
    )
    row = matching[0]
    assert row["company_id"] == company_id
    assert row["event"] == "company.description_updated"
    assert row["actor_id"] == str(admin.id)
    assert row["actor_type"] == "staff"
    assert row["data"] == {"before": "old text", "after": "new text"}
    assert row["performed_by"] is None
    assert row["on_behalf_of"] is None


# ---------------------------------------------------------------------------
# 2: company_id filter -- positive + negative probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_filters_by_company_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?company_id=<A> returns A's entry, never B's -- proves the
    filter is a real WHERE clause, not a no-op that returns everything.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a = await _create_company(client, admin_token)
    company_b = await _create_company(client, admin_token)

    entry_a = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_a),
        data={"fields": ["name"]},
    )
    entry_b = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_b),
        data={"fields": ["name"]},
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_a}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(entry_a.id) in ids
    assert str(entry_b.id) not in ids


# ---------------------------------------------------------------------------
# 3: date-range filter -- positive + negative probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_filters_by_date_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A wide [date_from, date_to] window around "now" includes a
    freshly-recorded entry; a window entirely in the past excludes it.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id = await _create_company(client, admin_token)

    entry = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={},
    )
    await db_session.commit()

    now = datetime.now(timezone.utc)

    # Positive: window spans "now". Uses httpx's `params=` (not a
    # hand-built query string) so the "+00:00" UTC offset in
    # isoformat() is percent-encoded correctly -- a literal "+" in a
    # raw query string decodes as a space server-side and would
    # corrupt the timestamp.
    resp = await client.get(
        "/api/v1/staff/audit/companies",
        params={
            "company_id": company_id,
            "date_from": (now - timedelta(hours=1)).isoformat(),
            "date_to": (now + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(entry.id) in ids

    # Negative: window entirely before the entry was written.
    resp = await client.get(
        "/api/v1/staff/audit/companies",
        params={
            "company_id": company_id,
            "date_from": (now - timedelta(days=2)).isoformat(),
            "date_to": (now - timedelta(days=1)).isoformat(),
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(entry.id) not in ids


# ---------------------------------------------------------------------------
# 4: project_manage gate -- two-sided control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_requires_project_manage(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff WITHOUT project_manage -> 403. The SAME account with
    project_manage granted -> 200 with the seeded row -- proving the
    403 was specifically the project_manage gate, not some unrelated
    failure (wrong token, wrong path, empty result).
    """
    staff, token = await create_staff_user(client, db_session)

    # Need an admin to create the company + seed the audit row --
    # staff-under-test starts without project_manage, which also gates
    # POST /staff/companies.
    admin, admin_token = await create_admin_user(client, db_session)
    company_id = await _create_company(client, admin_token)
    entry = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={},
    )
    await db_session.commit()

    # Negative: create_staff_user's fixture carries
    # DEFAULT_STAFF_PERMISSIONS verbatim, i.e. project_manage=False.
    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_id}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text

    # CONTROL: identical account, identical call, project_manage
    # granted -> 200 with the seeded row.
    await _set_project_manage(db_session, staff.id, True)

    resp = await client.get(
        f"/api/v1/staff/audit/companies?company_id={company_id}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(entry.id) in ids
