# =============================================================================
# AIVIS.ONE Backend -- PATCH /api/v1/companies/me Tests
#                       (TASK-30 ruling 10/12 + TASK-39 item 6 supersession)
# =============================================================================
#
# Covers the TASK-30 DONE-TEST groups that apply to this endpoint, UPDATED
# for TASK-39 item 6 (owner ruling, 2026-08, time-boxed): name,
# price_per_unit_cents, total_supply, and shares_per_option are now
# ALSO project-editable through this endpoint (previously admin-only).
#   C1 -- the project edits every one of its own editable fields, response
#         reflects the change. Now split in two: presentation fields (as
#         before) plus a dedicated group for name/total_supply/
#         shares_per_option (non-cascading scalar writes) and a SEPARATE
#         group for price_per_unit_cents, because a price change is NOT a
#         plain field write -- it must cascade through cascade_price()
#         (product price propagation + installment-template soft-delete),
#         append a CompanyPriceHistory row, and record its own
#         company.price_updated audit event. See
#         test_project_price_change_cascades_and_audits below.
#   C4 -- ISOLATION. No company_id in the URL, so the natural attack is:
#         company B calls PATCH /me, company A's row is unchanged. Must
#         never be skipped just because "there's no id to attack".
#   C5 -- admin-column rejection, NARROWED by TASK-39 item 6: only
#         distribution_config remains structurally unrepresentable here
#         (extra="forbid" 422) -- name / price_per_unit_cents /
#         total_supply / shares_per_option moved OUT of this group and
#         into the acceptance tests above. The OptionPool has no fields
#         on this schema at all (never did), so distribution_config alone
#         carries this coverage now.
#   C6 -- a non-company role (investor) gets 403, same as every other
#         company-role-gated endpoint (get_current_company_profile).
#   D1 -- ACTIVE -> HIDDEN succeeds.
#   D2 -- HIDDEN -> ACTIVE is refused (named 4xx, not 500, not a silent
#         no-op); ARCHIVED from this endpoint is also refused. Both shown
#         explicitly rather than assuming one implies the other. TASK-39
#         item 6 does NOT touch this asymmetry -- re-verified below.
#
# Company accounts are created the same way test_company_audit_feed.py
# creates them (POST /staff/companies as an admin), then logged in via
# the ordinary email/login endpoint to obtain that company's own token --
# company users are User rows with email/password credentials like any
# other, so /auth/email/login works unmodified for role=company.
# =============================================================================

import uuid

import pytest
from sqlalchemy import select
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.companies.models import CompanyPriceHistory
from app.modules.products.models import Product, ProductInstallment
from tests.helpers import auth_headers, create_admin_user, login_user, register_user


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


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    package_size: int = 100,
) -> dict:
    """POST /staff/products, then activate it (staff-side).

    Mirrors test_installments.py's _create_product / _activate_product.
    ACTIVE status matters here because cascade_price() only touches
    ACTIVE/HIDDEN products (companies/service.py::_apply_price_change ->
    products/service.py::cascade_price) -- ARCHIVED is excluded.
    """
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": "Self-service price cascade product",
            "package_size": package_size,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    product = resp.json()

    activate = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activate.status_code == 200, activate.text

    return product


async def _create_installment_template(
    client: AsyncClient, admin_token: str, product_id: str
) -> dict:
    """POST /staff/products/{id}/installments -- one ProductInstallment
    template. Tranches sized for the default _create_product price
    (10_000 cents) * package_size (100) = 1_000_000 total, mirroring
    test_installments.py's default fixture.
    """
    resp = await client.post(
        f"/api/v1/staff/products/{product_id}/installments",
        json={
            "name": "Self-service cascade test plan",
            "plan_config": {
                "tranches": [
                    {"amount_cents": 500_000, "units_percent": 50},
                    {"amount_cents": 500_000, "units_percent": 50},
                ],
                "bonus_units": 5,
                "agent_bonus_units": 2,
            },
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


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


@pytest.mark.asyncio
async def test_project_can_edit_name_total_supply_shares_per_option(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TASK-39 item 6: name / total_supply / shares_per_option are now
    project-editable.

    This company has NO active pool, which is the state the volume
    fields are editable in -- see
    test_project_cannot_change_volume_while_an_active_pool_exists for
    the other half. name has no cascade at all; total_supply only
    matters once a pool derives equity_percent from it.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    new_name = f"Renamed Co {uuid.uuid4().hex[:8]}"
    resp = await client.patch(
        "/api/v1/companies/me",
        json={
            "name": new_name,
            "total_supply": 2_000_000,
            "shares_per_option": 5,
        },
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == company_id
    assert body["name"] == new_name
    assert body["total_supply"] == 2_000_000
    assert body["shares_per_option"] == 5

    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["name"] == new_name
    assert get_body["total_supply"] == 2_000_000
    assert get_body["shares_per_option"] == 5


@pytest.mark.asyncio
async def test_project_price_change_cascades_and_audits(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TASK-39 item 6: a self-service price change is NOT a plain field
    write -- it must go through the SAME cascade_price() machinery as
    the staff price endpoint (companies/service.py::_apply_price_change,
    shared between update_own_company() and update_price()).

    Verifies, all scoped to rows created by THIS test (never absolute
    counts -- shared-DB discipline):
      1. the response and GET both show the new price;
      2. the company's ACTIVE product's price_per_unit_cents is updated;
      3. that product's installment template is soft-deleted
         (is_deleted=True);
      4. a CompanyPriceHistory row was appended with the new price,
         changed_by = the company's own user_id;
      5. a company.price_updated audit row was written with
         actor_type="user" (not "staff") and actor_id = the company's
         own user_id -- the self-service path reuses the STAFF event
         name/shape, only actor_type differs (same convention as
         attachment_created / roadmap_item_created self-service reuse).
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    # Company's own user_id, needed to scope the CompanyPriceHistory /
    # AuditLog assertions below to rows THIS test produced.
    me = await client.get("/api/v1/companies/me", headers=auth_headers(company_token))
    assert me.status_code == 200, me.text
    company_user_id = me.json()["user_id"]
    original_price = me.json()["price_per_unit_cents"]  # 10_000, from _create_company_and_login

    product = await _create_product(client, admin_token, company_id, package_size=100)
    installment = await _create_installment_template(client, admin_token, product["id"])

    new_price = original_price + 5_000
    assert new_price != original_price

    resp = await client.patch(
        "/api/v1/companies/me",
        json={"price_per_unit_cents": new_price},
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price_per_unit_cents"] == new_price

    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert get_resp.json()["price_per_unit_cents"] == new_price

    # 2. Product price cascaded.
    product_row = (
        await db_session.execute(
            select(Product).where(Product.id == uuid.UUID(product["id"]))
        )
    ).scalar_one()
    assert product_row.price_per_unit_cents == new_price

    # 3. Installment template soft-deleted.
    installment_row = (
        await db_session.execute(
            select(ProductInstallment).where(
                ProductInstallment.id == uuid.UUID(installment["id"])
            )
        )
    ).scalar_one()
    assert installment_row.is_deleted is True

    # 4. Price history row appended, changed_by = the project's own user.
    history_rows = (
        await db_session.execute(
            select(CompanyPriceHistory).where(
                CompanyPriceHistory.company_id == uuid.UUID(company_id),
                CompanyPriceHistory.price_per_unit_cents == new_price,
            )
        )
    ).scalars().all()
    assert len(history_rows) == 1
    assert str(history_rows[0].changed_by) == company_user_id

    # 5. Audit event: company.price_updated, actor_type="user" (the
    # self-service actor), reusing the SAME event name the staff price
    # endpoint writes -- see companies/service.py::update_own_company
    # docstring for why price stays out of company.self_updated's
    # "fields" list.
    audit_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.target_type == "company",
                AuditLog.target_id == uuid.UUID(company_id),
                AuditLog.event == "company.price_updated",
            )
        )
    ).scalars().all()
    assert len(audit_rows) == 1
    audit_row = audit_rows[0]
    assert audit_row.actor_type == "user"
    assert str(audit_row.actor_id) == company_user_id
    assert audit_row.data["old_price"] == original_price
    assert audit_row.data["new_price"] == new_price
    assert audit_row.data["products_updated"] == 1


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
#
# NARROWED by TASK-39 item 6: name / price_per_unit_cents / total_supply
# / shares_per_option are no longer in this group (see the acceptance +
# cascade tests above). distribution_config is the one field still
# structurally absent from UpdateOwnCompanyRequest -- the OptionPool has
# no representation on this schema at all, so there is nothing else left
# to test here.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_me_rejects_distribution_config_field(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={"distribution_config": {"company_pct": 0.9, "agent_levels": []}},
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 422, resp.text

    get_resp = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert get_resp.json()["distribution_config"] != {
        "company_pct": 0.9,
        "agent_levels": [],
    }


# ---------------------------------------------------------------------------
# C6: non-company role gets 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_me_rejects_non_company_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An investor (the default role register_user mints) has no
    CompanyProfile, so get_current_company_profile refuses with 403 --
    same contract as GET /me and every other company-role-gated route.
    """
    investor = await register_user(client)

    resp = await client.patch(
        "/api/v1/companies/me",
        json={"description": "should never land"},
        headers=auth_headers(investor["session_token"]),
    )
    assert resp.status_code == 403, resp.text


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


# ---------------------------------------------------------------------------
# TASK-39 item 6 guard: volume fields vs an existing option pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_cannot_change_volume_while_an_active_pool_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """total_supply / shares_per_option are refused once a pool exists.

    OptionPool.equity_percent is a STORED column whose invariant is
    total_options / company.total_supply * 100, recomputed only at pool
    create and pool update. Writing total_supply as a plain field would
    force a dilution decision nobody has made -- keep total_options and
    every investor's percentage silently drops, or keep equity_percent
    and the pool resizes, maybe below units already consumed. So the
    edit is refused while a pool exists and the caller is pointed at the
    pool-level operation.

    Two controls, so this cannot pass for the wrong reason:
      * BEFORE the pool exists the same PATCH SUCCEEDS (proving the
        rejection below is the pool's doing, not a blanket refusal);
      * a NON-volume field still succeeds AFTER the pool exists (proving
        the guard is scoped to the volume fields, not the endpoint).
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    # Control 1: no pool yet -> the volume edit is allowed.
    pre = await client.patch(
        "/api/v1/companies/me",
        json={"total_supply": 3_000_000},
        headers=auth_headers(company_token),
    )
    assert pre.status_code == 200, (
        f"control failed: with no active pool the volume edit must be "
        f"allowed, got {pre.status_code}: {pre.text}"
    )

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "10.0000"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code in (200, 201), pool_resp.text

    blocked = await client.patch(
        "/api/v1/companies/me",
        json={"total_supply": 4_000_000},
        headers=auth_headers(company_token),
    )
    assert blocked.status_code == 400, blocked.text
    assert "pool" in blocked.json()["message"].lower()

    blocked_shares = await client.patch(
        "/api/v1/companies/me",
        json={"shares_per_option": 7},
        headers=auth_headers(company_token),
    )
    assert blocked_shares.status_code == 400, blocked_shares.text

    # The company's stored total_supply is untouched by the refusals.
    after = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert after.status_code == 200
    assert after.json()["total_supply"] == 3_000_000

    # Control 2: a non-volume field still works with the pool in place.
    ok = await client.patch(
        "/api/v1/companies/me",
        json={"description": f"still editable {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(company_token),
    )
    assert ok.status_code == 200, (
        f"control failed: the guard must be scoped to the volume fields, "
        f"but a description edit was refused: {ok.text}"
    )


@pytest.mark.asyncio
async def test_unchanged_price_does_not_reject_the_rest_of_the_patch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Resubmitting the SAME price must not 400 a bundled PATCH.

    This endpoint is a partial PATCH fed by a settings form, so an
    untouched price field rides along on every save. Routed into
    _apply_price_change() it would hit that helper's "New price is the
    same as current price" guard -- correct for the STAFF endpoint,
    which is a dedicated "set the price" call, but here it would roll
    back a description the user really did change because of a field
    they never touched.

    Controls, so this cannot pass vacuously:
      * the description change actually LANDS (not merely a 200);
      * NO CompanyPriceHistory row is written for the no-op price, so
        "accepted" does not quietly mean "applied";
      * a genuinely DIFFERENT price in the same shape still cascades,
        proving the skip is scoped to equality, not to bundling.
    """
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, company_token = await _create_company_and_login(client, admin_token)

    current = await client.get(
        "/api/v1/companies/me", headers=auth_headers(company_token)
    )
    assert current.status_code == 200, current.text
    same_price = current.json()["price_per_unit_cents"]

    history_before = (
        await db_session.execute(
            select(CompanyPriceHistory).where(
                CompanyPriceHistory.company_id == uuid.UUID(company_id)
            )
        )
    ).scalars().all()

    new_desc = f"desc {uuid.uuid4().hex[:8]}"
    resp = await client.patch(
        "/api/v1/companies/me",
        json={"price_per_unit_cents": same_price, "description": new_desc},
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, (
        f"an unchanged price must not reject the bundled edit: {resp.text}"
    )
    assert resp.json()["description"] == new_desc
    assert resp.json()["price_per_unit_cents"] == same_price

    history_after = (
        await db_session.execute(
            select(CompanyPriceHistory).where(
                CompanyPriceHistory.company_id == uuid.UUID(company_id)
            )
        )
    ).scalars().all()
    assert len(history_after) == len(history_before), (
        "a no-op price must write no CompanyPriceHistory row"
    )

    # Control: a real change in the same request shape still goes through.
    changed = await client.patch(
        "/api/v1/companies/me",
        json={"price_per_unit_cents": same_price + 100, "description": new_desc},
        headers=auth_headers(company_token),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["price_per_unit_cents"] == same_price + 100
    history_final = (
        await db_session.execute(
            select(CompanyPriceHistory).where(
                CompanyPriceHistory.company_id == uuid.UUID(company_id)
            )
        )
    ).scalars().all()
    assert len(history_final) == len(history_before) + 1, (
        "control failed: a genuine price change must still record history"
    )
