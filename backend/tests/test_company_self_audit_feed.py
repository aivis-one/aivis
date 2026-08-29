# =============================================================================
# AIVIS.ONE Backend -- Company Self-Service Audit Feed Tests (TASK-39 item 7)
# =============================================================================
#
# GET /api/v1/company/audit did not exist before this delivery -- see
# audit/company_router.py. These tests exercise the real endpoint
# end-to-end (never call audit/service.py directly), because the
# ownership boundary ("company A cannot see company B's history") is a
# route/dependency property (get_current_company_profile forcing
# company_id server-side), not just a service-layer filter one.
#
# Mirrors test_company_audit_feed.py's (the STAFF feed's) seeding
# style: record_audit() is called directly to plant rows with exact,
# controlled `data` shapes, since there is no live self-service write
# endpoint here that produces every event shape this feed must handle
# safely (company.price_updated in particular is staff-driven only).
#
# SHARED-DB DISCIPLINE: every assertion below is a positive/negative
# probe on THIS test's own row/company ids (never "the list has N
# items", never "the first item is..."), matching test_company_audit_
# feed.py and test_company_roadmap.py's convention -- the dev/test DB
# carries rows from other tests in the same run.
# =============================================================================

import uuid

import pytest
from app.core.audit import record_audit
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import auth_headers, create_admin_user, login_user, register_user


async def _create_company(client: AsyncClient, admin_token: str) -> tuple[str, str, str]:
    """POST /staff/companies -- returns (company_id, email, password)."""
    email = f"coaudit_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"CoAuditCo {uuid.uuid4().hex[:8]}",
            "description": "Company self-audit feed test company",
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
# 1: a company sees its OWN entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_sees_own_entries(client: AsyncClient, db_session: AsyncSession) -> None:
    """A row recorded against the company's own id shows up on
    GET /api/v1/company/audit with the narrowed shape (id, event,
    created_at, actor_type, changed_fields) -- no company_id parameter
    exists on this route at all, unlike the staff feed.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    entry = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"fields": ["description", "logo_url"]},
    )
    await db_session.commit()

    resp = await client.get("/api/v1/company/audit", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    matching = [item for item in body["items"] if item["id"] == str(entry.id)]
    assert len(matching) == 1, (
        f"seeded entry {entry.id} missing from own feed: {body['items']}"
    )
    row = matching[0]
    assert row["event"] == "company.updated"
    assert row["actor_type"] == "staff"
    assert set(row["changed_fields"]) == {"description", "logo_url"}
    assert row.keys() == {"id", "event", "created_at", "actor_type", "changed_fields"}


# ---------------------------------------------------------------------------
# 2: OWNERSHIP BOUNDARY -- a company cannot see another company's entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_cannot_see_another_companys_entries(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The single most important property of this endpoint: company B's
    GET /api/v1/company/audit never contains a row recorded against
    company A's id, and company A's own call still sees it (proving the
    absence is the ownership boundary, not a broken/empty feed).

    There is no company_id query parameter to attempt on this route --
    company_id is forced server-side from get_current_company_profile,
    so this test proves that forcing actually holds.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_a_id, email_a, password_a = await _create_company(client, admin_token)
    company_b_id, email_b, password_b = await _create_company(client, admin_token)
    token_a = await _login_company(client, email_a, password_a)
    token_b = await _login_company(client, email_b, password_b)

    entry_a = await record_audit(
        session=db_session,
        event="company.self_updated",
        actor_id=admin.id,
        actor_type="user",
        target_type="company",
        target_id=uuid.UUID(company_a_id),
        data={"fields": ["description"], "changes": {"description": {"old": "x", "new": "y"}}},
    )
    await db_session.commit()

    # B's own feed never contains A's entry.
    resp_b = await client.get("/api/v1/company/audit", headers=auth_headers(token_b))
    assert resp_b.status_code == 200, resp_b.text
    ids_b = {item["id"] for item in resp_b.json()["items"]}
    assert str(entry_a.id) not in ids_b

    # CONTROL: A's own feed DOES contain it -- proves the absence above
    # is the ownership boundary, not an endpoint that returns nothing.
    resp_a = await client.get("/api/v1/company/audit", headers=auth_headers(token_a))
    assert resp_a.status_code == 200, resp_a.text
    ids_a = {item["id"] for item in resp_a.json()["items"]}
    assert str(entry_a.id) in ids_a


# ---------------------------------------------------------------------------
# 3: non-company role -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_company_role_gets_403(client: AsyncClient, db_session: AsyncSession) -> None:
    """A regular (investor-role) user has no CompanyProfile, so
    get_current_company_profile refuses with 403 -- matching every
    other /api/v1/company/* self-service route's contract.
    """
    body = await register_user(client)
    token = body["session_token"]

    resp = await client.get("/api/v1/company/audit", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 4: no staff identity, no raw values -- specifically price_updated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_carries_no_staff_identity_or_raw_values(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two rows are seeded: an ordinary avatar-mode-shaped write (to
    prove actor_id/performed_by/on_behalf_of never round-trip even
    when they ARE set on the underlying AuditLog row) and a
    company.price_updated write (to prove old_price/new_price never
    leak anywhere in the serialized response -- not as top-level
    fields, not inside changed_fields, not anywhere in the raw JSON
    text of the response body).
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    on_behalf_of_id = uuid.uuid4()
    identity_entry = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"fields": ["name"]},
        performed_by=admin.id,
        on_behalf_of=on_behalf_of_id,
    )
    price_entry = await record_audit(
        session=db_session,
        event="company.price_updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={
            "old_price": 999999,
            "new_price": 111111,
            "products_updated": 3,
        },
    )
    await db_session.commit()

    resp = await client.get("/api/v1/company/audit", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    raw_text = resp.text

    # No staff-identity value anywhere in the raw response text -- not
    # just "not a top-level key", genuinely absent from the payload.
    # Covers both seeded rows' actor_id (both = admin.id) plus
    # identity_entry's performed_by (also admin.id) and its distinct
    # on_behalf_of id (a fresh, unrelated random UUID -- proves this
    # specific field's value never round-trips, independent of
    # admin.id appearing for some unrelated reason).
    assert str(admin.id) not in raw_text
    assert str(on_behalf_of_id) not in raw_text

    # The distinctive price VALUES must not leak anywhere in the wire
    # payload, under any key.
    assert "999999" not in raw_text
    assert "111111" not in raw_text

    items = resp.json()["items"]
    identity_row = next(item for item in items if item["id"] == str(identity_entry.id))
    price_row = next(item for item in items if item["id"] == str(price_entry.id))

    for row in (identity_row, price_row):
        assert "actor_id" not in row
        assert "performed_by" not in row
        assert "on_behalf_of" not in row
        assert "data" not in row

    # company.price_updated: every key in its `data` blob (old_price,
    # new_price, products_updated) is a value-only carrier -- none of
    # them names a field, so changed_fields is empty. See schemas.py's
    # _derive_changed_fields()/_VALUE_ONLY_KEYS for the reasoning.
    assert price_row["changed_fields"] == []
    assert "old_price" not in price_row["changed_fields"]
    assert "new_price" not in price_row["changed_fields"]


# ---------------------------------------------------------------------------
# 5: pagination works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_works(client: AsyncClient, db_session: AsyncSession) -> None:
    """Seed 3 rows for one company with per_page=2: page 1 returns 2
    items, page 2 returns the remaining 1, and total reflects the full
    set for this company (never "count == 3" against the raw DB, since
    other tests share it -- instead we prove each seeded id appears on
    exactly one of the two pages, no overlap, no loss).
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)
    token = await _login_company(client, email, password)

    seeded_ids = []
    for i in range(3):
        entry = await record_audit(
            session=db_session,
            event="company.self_updated",
            actor_id=admin.id,
            actor_type="user",
            target_type="company",
            target_id=uuid.UUID(company_id),
            data={"fields": [f"field_{i}"]},
        )
        seeded_ids.append(str(entry.id))
    await db_session.commit()

    resp_p1 = await client.get(
        "/api/v1/company/audit",
        params={"page": 1, "per_page": 2},
        headers=auth_headers(token),
    )
    assert resp_p1.status_code == 200, resp_p1.text
    body_p1 = resp_p1.json()
    assert body_p1["page"] == 1
    assert body_p1["per_page"] == 2
    assert len(body_p1["items"]) == 2
    assert body_p1["total"] >= 3  # this company has at least our 3 seeded rows

    resp_p2 = await client.get(
        "/api/v1/company/audit",
        params={"page": 2, "per_page": 2},
        headers=auth_headers(token),
    )
    assert resp_p2.status_code == 200, resp_p2.text
    body_p2 = resp_p2.json()
    assert body_p2["page"] == 2

    ids_p1 = {item["id"] for item in body_p1["items"]}
    ids_p2 = {item["id"] for item in body_p2["items"]}

    # No overlap between pages.
    assert ids_p1.isdisjoint(ids_p2)

    # Every seeded id appears on exactly one of the two pages fetched
    # (all 3 rows fit within page1 + page2 = 4 slots).
    all_returned = ids_p1 | ids_p2
    for seeded_id in seeded_ids:
        assert seeded_id in all_returned, f"{seeded_id} missing from pages 1+2: {all_returned}"


# ---------------------------------------------------------------------------
# 6: a system-written row keyed to the company is NOT a company write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_company_event_is_excluded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """purchase.template_missing targets the company but is not its history.

    purchases/engine.py records that row with actor_type="system"
    beside a logger.error() when a document template is missing. It
    carries target_type="company", so the target_type filter alone
    would put our own internal error into a customer-facing "what
    changed on my project" feed. The route passes event_prefix=
    "company." precisely to keep it out; staff still see it in their
    own feed, which passes no prefix.

    The control is the second row: a real company.* row planted in the
    same company in the same test MUST come back, so a feed that
    returned nothing at all could not pass this test by accident.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)

    excluded = await record_audit(
        session=db_session,
        event="purchase.template_missing",
        actor_id=None,
        actor_type="system",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"kind": "investment_agreement", "language": "en"},
    )
    included = await record_audit(
        session=db_session,
        event="company.updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"fields": ["description"]},
    )
    await db_session.commit()

    token = await _login_company(client, email, password)
    resp = await client.get("/api/v1/company/audit", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text

    ids = {row["id"] for row in resp.json()["items"]}
    events = {row["event"] for row in resp.json()["items"]}

    # The control: without this the assertion below is vacuous.
    assert str(included.id) in ids, (
        f"control failed -- the company.* row {included.id} should be in its "
        f"own feed; got events {events}"
    )
    assert str(excluded.id) not in ids, (
        f"purchase.template_missing row {excluded.id} leaked into the "
        f"company-facing feed; got events {events}"
    )
    assert "purchase.template_missing" not in events


# ---------------------------------------------------------------------------
# 7: a staff write made through avatar mode must not be shown as "You"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_avatar_written_row_is_attributed_to_staff_not_the_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """actor_type must not say "user" when staff acted via avatar mode.

    Every company self-service write path hardcodes actor_type="user"
    because it names the AUTHENTICATED identity -- and in avatar mode
    that identity IS the company (avatar_service puts the target's
    user_id in the session). The stored row therefore reads "user"
    even though staff made the change, and the feed would render
    comp.auditFeed.actor.user = "You" to the company.

    core/audit.py back-fills performed_by with the avatar staff id on
    any write inside an avatar session, so its PRESENCE is the honest
    signal -- and only its presence is read, never its value, which
    must stay out of the response entirely.

    Control: the second row is an identical self-service write with NO
    performed_by. It MUST still come back as "user", or this test
    would also pass if the code simply labelled everything "staff".
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, email, password = await _create_company(client, admin_token)

    avatar_row = await record_audit(
        session=db_session,
        event="company.self_updated",
        actor_id=None,
        actor_type="user",           # what the write path stores
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"fields": ["description"]},
        performed_by=admin.id,       # the avatar back-fill marker
    )
    genuine_row = await record_audit(
        session=db_session,
        event="company.self_updated",
        actor_id=None,
        actor_type="user",
        target_type="company",
        target_id=uuid.UUID(company_id),
        data={"fields": ["logo_url"]},
    )
    await db_session.commit()

    token = await _login_company(client, email, password)
    resp = await client.get("/api/v1/company/audit", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    rows = {row["id"]: row for row in resp.json()["items"]}

    assert str(avatar_row.id) in rows, "seeded avatar row missing from the feed"
    assert rows[str(avatar_row.id)]["actor_type"] == "staff", (
        "a staff write made through avatar mode was attributed to the company "
        "itself -- the feed would tell them 'You' did it"
    )

    # Control: a real self-service write is still the company's own.
    assert str(genuine_row.id) in rows, "seeded genuine row missing from the feed"
    assert rows[str(genuine_row.id)]["actor_type"] == "user", (
        "control failed -- a genuine company write must still read 'user', "
        "otherwise the assertion above passes by labelling everything staff"
    )

    # The staff id itself must never appear, only the fact that staff acted.
    assert str(admin.id) not in resp.text
    assert "performed_by" not in resp.text
