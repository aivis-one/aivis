# =============================================================================
# CBSHOME Backend -- /companies/me Tests (Sprint 4.5)
# =============================================================================
#
# Tests cover:
#   1: GET /api/v1/companies/me as authenticated company user -> 200
#      with full profile including distribution_config
#   2: GET /api/v1/companies/me as investor -> 403
#      (get_current_company_profile rejects users without CompanyProfile)
#   3: GET /api/v1/companies/me without Authorization header -> 401
#
# Email prefix: "s45_" -- unique to this test file, cleaned up in fixture.
# Filename suffix `_me` keeps the broader test_companies.py untouched
# and lets `pytest tests/test_companies_me.py` run the Sprint 4.5
# surface in isolation.
# =============================================================================

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import (
    auth_headers,
    create_admin_user,
    login_user,
    register_user,
)

EMAIL_PREFIX = "s45_"

VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company_and_login(
    client: AsyncClient,
    admin_token: str,
    suffix: str,
) -> tuple[dict, str]:
    """Create a company via staff API and login as the company user.

    Mirrors the helper in test_company_dashboard.py (Sprint 4.3 B5)
    so behaviour stays consistent across the company-side test surface.
    Returns (company_response_dict, company_user_session_token).
    """
    email = f"{EMAIL_PREFIX}{suffix}@example.com"
    password = "companypass123"

    create_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert create_resp.status_code == 201, (
        f"Create company failed: {create_resp.text}"
    )
    company = create_resp.json()

    login_data = await login_user(client, email=email, password=password)
    return company, login_data["session_token"]


# ---------------------------------------------------------------------------
# Test 1: Authenticated company user gets their full profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_my_company_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Company user calls /companies/me -> 200 with full profile.

    The response is the staff-side CompanyResponse, which includes
    distribution_config and user_id (the public /companies/{id}
    projection omits both). This is the canonical contract for
    company-side Settings on the frontend.
    """
    admin_token = await _admin_token(client, db_session)
    company, company_token = await _create_company_and_login(
        client, admin_token, suffix="me"
    )

    resp = await client.get(
        "/api/v1/companies/me",
        headers=auth_headers(company_token),
    )
    assert resp.status_code == 200, f"/me failed: {resp.text}"
    body = resp.json()

    # Identity round-trip: the profile we get back must be the one
    # the staff just created.
    assert body["id"] == company["id"]
    assert body["name"] == company["name"]

    # Full-profile fields that the public /companies/{id} would NOT
    # expose. Their presence here is the whole point of the new
    # endpoint -- the frontend Settings UI needs them.
    assert "distribution_config" in body
    assert body["distribution_config"] == VALID_DIST_CONFIG
    assert "user_id" in body
    assert body["user_id"] == company["user_id"]

    # Sprint 4.3 supply fields round-trip too.
    assert body["total_supply"] == 1_000_000
    assert body["shares_per_option"] == 1


# ---------------------------------------------------------------------------
# Test 2: Investor gets 403 (no CompanyProfile linked to user)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_my_company_forbidden_for_non_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor calling /companies/me -> 403.

    get_current_company_profile raises ForbiddenError for any user
    without an attached CompanyProfile -- covers investor / agent /
    staff / platform uniformly. Same contract as /company/dashboard
    and /company/analytics (Sprint 4.3 B5), verified by message
    string match.
    """
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}investor@example.com"
    )
    inv_token = inv_data["session_token"]

    resp = await client.get(
        "/api/v1/companies/me",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403
    # Same message that test_dashboard_forbidden_for_non_company asserts.
    # Keeps the company-side surface contract uniform.
    assert "not linked to a company" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Test 3: Unauthenticated request gets 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_my_company_requires_auth(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No Authorization header on /companies/me -> 401.

    get_current_user (used transitively by get_current_company_profile)
    raises UnauthorizedError when the Bearer token is missing or
    invalid -- so the route must reject the request before it ever
    gets to the company-profile lookup.
    """
    resp = await client.get("/api/v1/companies/me")
    assert resp.status_code == 401
