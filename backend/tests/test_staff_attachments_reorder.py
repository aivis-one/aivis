# =============================================================================
# CBSHOME Backend -- Staff Attachments Reorder Tests (iter 2.6c B5)
# =============================================================================
#
# HTTP-level smoke coverage for the new bulk reorder endpoint:
#   PATCH /api/v1/staff/companies/{company_id}/attachments/reorder
#
# Tests cover:
#   1: happy path -- 3 attachments in one category, reorder reverses
#      the list, verify CompanyAttachment.order updated atomically
#   2: missing id -- payload omits one attachment -> 400 with the
#      "attachments_reorder_set_mismatch" prefix in the message
#   3: extra id -- payload contains an unrelated UUID -> 400
#   4: 404 on unknown company_id (raised by get_company)
#   5: 403 for investor (no company_manage permission)
#
# Robustness contract:
#   * The dev DB is shared. We never iterate "all attachments" --
#     every test scopes its checks to attachment rows it just
#     inserted. (company_id, category) filter on
#     CompanyAttachment makes this trivially safe.
#   * Attachments are created via direct ORM insert (no real MinIO
#     upload, no multipart). The reorder endpoint only touches the
#     `order` column; storage_key / mime_type / file_size_bytes are
#     present for NOT NULL constraints but never read.
#
# Why ORM insert instead of multipart POST:
#   The multipart create_attachment_staff_endpoint pushes bytes to
#   MinIO before returning. That makes happy-path tests slow and
#   couples them to MinIO health. For B5 we only need rows on the
#   table -- the order column is the entire surface area under test.
#   Storage-coupled flows are covered by their own tests elsewhere.
# =============================================================================

import uuid

import pytest
from app.modules.companies.models import CompanyAttachment, CompanyProfile
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


async def _admin_token_and_id(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[uuid.UUID, str]:
    """Create admin staff and return (user_id, session_token)."""
    user, token = await create_admin_user(client, db_session)
    return user.id, token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
) -> dict:
    """POST /staff/companies. Returns the created company response.

    Hidden status by default; we never need to activate it for these
    tests -- the reorder endpoint does not check company.status.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"att26c_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"AttReorderCo {uuid.uuid4().hex[:8]}",
            "description": "Staff attachments reorder test company",
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
    return resp.json()


async def _insert_attachment(
    db_session: AsyncSession,
    *,
    company_id: uuid.UUID,
    created_by: uuid.UUID,
    category: str,
    order: int,
    title: str | None = None,
) -> CompanyAttachment:
    """Insert a CompanyAttachment row directly via ORM.

    Storage / mime fields are filled with synthetic values that
    satisfy the NOT NULL constraints but are never inspected by
    the reorder code path. Each row gets a UUID-derived storage_key
    so the UNIQUE constraint on that column is satisfied across
    concurrent test runs.
    """
    if title is None:
        title = f"AttReorder {uuid.uuid4().hex[:8]}"

    attachment_id = uuid.uuid4()
    attachment = CompanyAttachment(
        id=attachment_id,
        company_id=company_id,
        category=category,
        language="en",
        title=title,
        description=None,
        storage_key=(
            f"companies/{company_id}/attachments/{attachment_id}/"
            f"{uuid.uuid4().hex}.pdf"
        ),
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1,
        order=order,
        is_published=False,
        is_public=False,
        created_by=created_by,
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    return attachment


async def _fetch_orders(
    db_session: AsyncSession,
    company_id: uuid.UUID,
    category: str,
) -> dict[uuid.UUID, int]:
    """Read back current `order` per attachment.id in scope.

    Used after a reorder to verify the column actually moved. We
    cannot drive this through the staff GET endpoint because it
    sorts by (category ASC, order ASC) globally -- a direct
    {id: order} map is the surgical check.

    Re-bind the session via a fresh SELECT so we observe the
    server-side state after the router's commit, not the cached
    ORM identity-map values from the inserts above.
    """
    await db_session.commit()  # flush any pending state from inserts
    db_session.expire_all()

    stmt = select(CompanyAttachment).where(
        CompanyAttachment.company_id == company_id,
        CompanyAttachment.category == category,
        CompanyAttachment.is_deleted == False,  # noqa: E712
    )
    result = await db_session.execute(stmt)
    return {att.id: att.order for att in result.scalars().all()}


# ---------------------------------------------------------------------------
# 1: happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_attachments_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Three attachments in one category -> reorder reverses them.

    Initial order: [a:0, b:1, c:2]. We PATCH with [c, b, a] and assert
    the new order column reads [a:2, b:1, c:0].
    """
    admin_id, admin_token = await _admin_token_and_id(client, db_session)
    company = await _create_company(client, admin_token)
    company_uuid = uuid.UUID(company["id"])
    category = "legal/incorporation"

    att_a = await _insert_attachment(
        db_session,
        company_id=company_uuid,
        created_by=admin_id,
        category=category,
        order=0,
    )
    att_b = await _insert_attachment(
        db_session,
        company_id=company_uuid,
        created_by=admin_id,
        category=category,
        order=1,
    )
    att_c = await _insert_attachment(
        db_session,
        company_id=company_uuid,
        created_by=admin_id,
        category=category,
        order=2,
    )

    # PATCH reversed -- c first, then b, then a.
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/attachments/reorder",
        json={
            "category": category,
            "item_ids": [str(att_c.id), str(att_b.id), str(att_a.id)],
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204, resp.text

    orders = await _fetch_orders(db_session, company_uuid, category)
    # c is now first (order=0), b stays in the middle (order=1),
    # a is now last (order=2).
    assert orders[att_c.id] == 0
    assert orders[att_b.id] == 1
    assert orders[att_a.id] == 2


# ---------------------------------------------------------------------------
# 2: missing id in payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_attachments_missing_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payload omits one attachment -> 400 with the sentinel prefix.

    The service computes a diff and surfaces both sides
    (`missing: [...]`, `unknown: [...]`) so staff UI can show a
    helpful message. We only assert the sentinel is present;
    the exact wording is documented in the service.
    """
    admin_id, admin_token = await _admin_token_and_id(client, db_session)
    company = await _create_company(client, admin_token)
    company_uuid = uuid.UUID(company["id"])
    category = "marketing/presentations"

    att_a = await _insert_attachment(
        db_session,
        company_id=company_uuid,
        created_by=admin_id,
        category=category,
        order=0,
    )
    att_b = await _insert_attachment(
        db_session,
        company_id=company_uuid,
        created_by=admin_id,
        category=category,
        order=1,
    )
    # att_c is NOT created -- we want a 2-row scope.

    # Send only one of the two rows -- the missing one is att_b.
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/attachments/reorder",
        json={
            "category": category,
            "item_ids": [str(att_a.id)],
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "attachments_reorder_set_mismatch" in body.get("message", ""), (
        f"Expected sentinel in error message, got: {body}"
    )

    # Sanity: order column not mutated when validation rejects.
    orders = await _fetch_orders(db_session, company_uuid, category)
    assert orders[att_a.id] == 0
    assert orders[att_b.id] == 1


# ---------------------------------------------------------------------------
# 3: extra unknown id in payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_attachments_unknown_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payload contains an UUID that isn't in the scope -> 400.

    Mirrors the "missing" test but on the other side of the diff.
    """
    admin_id, admin_token = await _admin_token_and_id(client, db_session)
    company = await _create_company(client, admin_token)
    company_uuid = uuid.UUID(company["id"])
    category = "patents"

    att_a = await _insert_attachment(
        db_session,
        company_id=company_uuid,
        created_by=admin_id,
        category=category,
        order=0,
    )
    bogus = uuid.uuid4()

    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/attachments/reorder",
        json={
            "category": category,
            "item_ids": [str(att_a.id), str(bogus)],
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400, resp.text
    assert "attachments_reorder_set_mismatch" in resp.json().get(
        "message", ""
    )

    # Sanity: order column unchanged.
    orders = await _fetch_orders(db_session, company_uuid, category)
    assert orders[att_a.id] == 0


# ---------------------------------------------------------------------------
# 4: 404 on unknown company_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_attachments_404_unknown_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Random company_id -> 404 (get_company raises NotFoundError).

    The service runs the company-existence check before loading
    the attachment scope, so an empty 204 would be a leak: a probe
    could distinguish "exists but empty" from "doesn't exist".
    """
    _admin_id, admin_token = await _admin_token_and_id(client, db_session)
    fake_id = uuid.uuid4()

    resp = await client.patch(
        f"/api/v1/staff/companies/{fake_id}/attachments/reorder",
        json={"category": "patents", "item_ids": []},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# 5: 403 for non-staff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_attachments_forbidden_for_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor token -> 403. require_staff_permission rejects on the
    role check before company / scope lookup runs.
    """
    inv_data = await register_user(client)
    inv_token = inv_data["session_token"]

    fake_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/v1/staff/companies/{fake_id}/attachments/reorder",
        json={"category": "patents", "item_ids": []},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403, resp.text
