# =============================================================================
# CBSHOME Backend -- Staff Companies List Tests (iter 2.6c B2)
# =============================================================================
#
# HTTP-level smoke coverage for the new GET /api/v1/staff/companies
# endpoint added in iter 2.6c B2.
#
# Tests cover:
#   1: list returns every status (active + hidden + archived) when no
#      filter is given
#   2: ?status=hidden surfaces only the hidden company; active /
#      archived siblings are absent
#   3: ?search=<UUID-derived needle> returns exactly the company whose
#      name carries the needle
#   4: ?status=invalid -> 422 from the FastAPI enum bind
#   5: investor token (no company_manage) -> 403
#
# Robustness contract (mirrors test_public_companies.py / B1 notes):
#   * The dev DB is shared across runs and tests. Never iterate over
#     returned items asserting "all have status X" -- that fails on
#     pre-existing rows. Probe positive (our id IS in the page) and
#     negative (our other id IS NOT in the page) instead.
#   * Companies created here use UUID-suffixed names + emails so search
#     queries are unambiguous against arbitrary pollution.
#   * To survive a heavily polluted dev DB on unfiltered list, walk
#     pages until we find every staged id or exhaust total. Same
#     pattern as test_public_companies.py::test_public_list_returns_only_active.
#
# Email prefix:
#   Company users -- "co26c_" via _create_company (UUID-suffixed).
#   Investor probe -- default from register_user (test_<uuid>@example.com).
# =============================================================================

import uuid

import pytest
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)


# ---------------------------------------------------------------------------
# Local helpers -- mirror test_public_companies.py shape, minus the pool
# (this file tests the list endpoint, pool stats are irrelevant here).
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin staff user and return their session token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    *,
    name: str | None = None,
) -> dict:
    """POST /staff/companies. Created in HIDDEN status by service default.

    Pool is NOT created -- list-endpoint tests don't depend on pool
    stats. Caller activates / archives the company as needed.
    """
    if name is None:
        name = f"StaffListCo {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"co26c_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": name,
            "description": "Staff companies list test company",
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


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    """Transition hidden -> active via PATCH (exercises state machine)."""
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text


async def _set_company_status_direct(
    db_session: AsyncSession, company_id: str, status: str
) -> None:
    """ORM-level status flip, bypassing the state-machine guard.

    Used here to reach `archived` directly from `hidden` without going
    through PATCH twice (hidden -> active -> archived). Mirrors the
    helper in test_public_companies.py for the same reason.
    """
    profile = (
        await db_session.execute(
            select(CompanyProfile).where(
                CompanyProfile.id == uuid.UUID(company_id)
            )
        )
    ).scalar_one()
    profile.status = status
    await db_session.commit()


async def _walk_pages(
    client: AsyncClient,
    admin_token: str,
    *,
    qs: str = "",
) -> set[str]:
    """Walk every page of GET /staff/companies and return the id set.

    Per the robustness contract: the dev DB may already contain
    hundreds of companies. We can't assume our staged ids land on
    page 1 of an unfiltered list, so we paginate until exhausted.
    For filtered probes (status / search) the page count is small
    and the walk terminates quickly.
    """
    found: set[str] = set()
    page = 1
    while True:
        sep = "&" if qs else ""
        resp = await client.get(
            f"/api/v1/staff/companies?per_page=100&page={page}{sep}{qs}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        found.update(item["id"] for item in body["items"])
        if len(body["items"]) < 100 or page * 100 >= body["total"]:
            break
        page += 1
    return found


# ---------------------------------------------------------------------------
# 1: unfiltered list returns every status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_list_returns_all_statuses(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Three companies (1 active, 1 hidden, 1 archived) -- unfiltered
    GET /staff/companies must surface ALL three.

    This is the contract that distinguishes the staff list from the
    public list (which filters active_only=True). Confirms the new
    endpoint passes active_only=False to the service.
    """
    admin_token = await _admin_token(client, db_session)

    active_co = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, active_co["id"])

    hidden_co = await _create_company(client, admin_token)
    # Hidden by default; no PATCH needed.

    archived_co = await _create_company(client, admin_token)
    await _set_company_status_direct(
        db_session, archived_co["id"], CompanyStatus.ARCHIVED.value
    )

    found_ids = await _walk_pages(client, admin_token)
    assert active_co["id"] in found_ids
    assert hidden_co["id"] in found_ids
    assert archived_co["id"] in found_ids


# ---------------------------------------------------------------------------
# 2: ?status=hidden -- positive + negative probes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_list_filter_by_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?status=hidden includes the hidden sibling, excludes the
    active and archived siblings staged in the same test.

    Positive + negative probes on specific ids is the only assertion
    that survives a polluted dev DB. We deliberately do NOT iterate
    items to claim "all are hidden" -- that would tautologically
    succeed when the SQL clause works AND fail on residual rows.
    """
    admin_token = await _admin_token(client, db_session)

    active_co = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, active_co["id"])

    hidden_co = await _create_company(client, admin_token)

    archived_co = await _create_company(client, admin_token)
    await _set_company_status_direct(
        db_session, archived_co["id"], CompanyStatus.ARCHIVED.value
    )

    hidden_ids = await _walk_pages(
        client, admin_token, qs="status=hidden"
    )
    assert hidden_co["id"] in hidden_ids, (
        f"Hidden company {hidden_co['id']} missing from "
        f"?status=hidden page"
    )
    assert active_co["id"] not in hidden_ids, (
        f"Active company {active_co['id']} leaked into "
        f"?status=hidden page -- WHERE clause not filtering"
    )
    assert archived_co["id"] not in hidden_ids, (
        f"Archived company {archived_co['id']} leaked into "
        f"?status=hidden page -- WHERE clause not filtering"
    )


# ---------------------------------------------------------------------------
# 3: ?search=<UUID-needle>
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_list_search_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?search=<needle> case-insensitively matches CompanyProfile.name.

    Use a UUID-derived needle that no other company in the dev DB can
    accidentally carry. Mirrors the contract proven for the public
    list in test_public_companies.py::test_public_list_search_filter.
    """
    admin_token = await _admin_token(client, db_session)
    needle = uuid.uuid4().hex[:10]
    matching = await _create_company(
        client, admin_token, name=f"Findme {needle} Corp"
    )

    found_ids = await _walk_pages(
        client, admin_token, qs=f"search={needle}"
    )
    assert matching["id"] in found_ids
    # Negative side of the probe: a same-test second company without
    # the needle in its name must NOT surface. Catches the case where
    # the service drops the search clause silently.
    decoy = await _create_company(client, admin_token)
    found_ids_after_decoy = await _walk_pages(
        client, admin_token, qs=f"search={needle}"
    )
    assert decoy["id"] not in found_ids_after_decoy


# ---------------------------------------------------------------------------
# 4: ?status=garbage -> 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_list_filter_status_invalid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?status=garbage -> 422 from the typed CompanyStatus bind.

    Confirms the FastAPI boundary rejects unknown values before the
    service is invoked.
    """
    admin_token = await _admin_token(client, db_session)
    resp = await client.get(
        "/api/v1/staff/companies?status=garbage",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 5: investor token -> 403 (company_manage permission missing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_list_forbidden_for_non_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor with no staff profile -> 403.

    The endpoint sits behind require_staff_permission("company_manage").
    A non-staff caller is rejected by the dependency well before the
    list query runs. We use a freshly registered investor (default
    role=investor, no staff profile, no permissions).
    """
    inv_data = await register_user(client)
    inv_token = inv_data["session_token"]

    resp = await client.get(
        "/api/v1/staff/companies",
        headers=auth_headers(inv_token),
    )
    # require_staff_permission raises ForbiddenError -> 403 for any
    # non-staff user (and for staff missing the specific permission).
    assert resp.status_code == 403, resp.text
