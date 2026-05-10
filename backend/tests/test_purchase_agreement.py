# =============================================================================
# CBSHOME Backend -- Purchase Agreement Tests (Refactor 2 iter 2.4, R2 §5.3)
# =============================================================================
#
# Tests cover:
#   1: GET  /purchases/{id}/agreement                -- 200 HTML happy path
#   2: GET  /purchases/{id}/agreement (other user)   -- 404
#   3: GET  /purchases/{id}/agreement (template miss) -- 500
#   4: POST /purchases/{id}/agreement/email           -- 204 (mocked send)
#   5: HTML render escapes investor-controlled fields (SEC-NEW-01)
#
# These tests run against the platform-default purchase_agreement
# templates seeded by `cbshome seed`. We don't need per-company
# templates -- the 4-stage fallback resolves the en/ru/de/ar platform
# defaults, and the snapshot id is recorded on Purchase at creation.
#
# Email prefix: "s24a_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.models import Purchase
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s24a_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Local helpers -- same shape as test_dashboard.py to keep the setup ritual
# consistent across the two purchase-document test files. Duplicated rather
# than imported because each test file owns its EMAIL_PREFIX namespace.
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    suffix: str = "co1",
    *,
    price_per_unit_cents: int = 10000,
) -> dict:
    """Create a company via staff endpoint + activate its OptionPool."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "name": f"Agreement Co {suffix}",
            "description": f"Company for agreement tests {suffix}",
            "price_per_unit_cents": price_per_unit_cents,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    company = resp.json()

    # Create the active OptionPool (required for purchases since Sprint 4.3).
    resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"total_options": 10_000},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create pool failed: {resp.text}"

    return company


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    package_size: int = 100,
    suffix: str = "pkg",
) -> dict:
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Agreement Package {suffix}",
            "description": f"Test package {suffix}",
            "package_size": package_size,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create product failed: {resp.text}"
    return resp.json()


async def _activate_product(
    client: AsyncClient, admin_token: str, product_id: str
) -> None:
    resp = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "inv1",
    balance_cents: int = 2_000_000,
    *,
    first_name: str = "Alice",
    last_name: str = "Doe",
) -> tuple[str, UUID]:
    """Register investor, set name in profile, approve KYC, deposit funds."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.kyc_status = "approved"
    user.profile = {"first_name": first_name, "last_name": last_name}
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_{EMAIL_PREFIX}",
    )
    await db_session.commit()

    return token, user_id


async def _buy_product(
    client: AsyncClient,
    inv_token: str,
    product_id: str,
) -> list[dict]:
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"
    return resp.json()


async def _setup_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_token: str,
    *,
    company_suffix: str = "co1",
    investor_suffix: str = "inv1",
    first_name: str = "Alice",
    last_name: str = "Doe",
) -> tuple[str, UUID, dict, dict, list[dict]]:
    """Full setup: company + pool + product + investor + purchase."""
    company = await _create_company(client, admin_token, company_suffix)
    product = await _create_product(
        client, admin_token, company["id"], suffix=company_suffix,
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client,
        db_session,
        suffix=investor_suffix,
        first_name=first_name,
        last_name=last_name,
    )

    purchases = await _buy_product(client, inv_token, product["id"])

    return inv_token, inv_id, company, product, purchases


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_agreement_html_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agreement -> 200 HTML containing investor + company data.

    Asserts substrings we *put into the template context* rather than
    bootstrap copy ("Investment Certificate" was the old hardcoded
    title; the new template can render arbitrary HTML). Investor's
    display name and the company name are stable across template
    variants, so they are safe anchors.
    """
    admin_token = await _admin_token(client, db_session)
    inv_token, inv_id, company, product, purchases = (
        await _setup_purchase(
            client, db_session, admin_token,
            company_suffix="ag1", investor_suffix="inv_ag",
            first_name="Alice", last_name="Doe",
        )
    )

    sale_purchase = next(
        p for p in purchases if p["legal_basis"] == "sale"
    )

    resp = await client.get(
        f"/api/v1/purchases/{sale_purchase['id']}/agreement",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]

    html = resp.text
    # Context anchors we explicitly inject in render_agreement_html.
    assert "Alice Doe" in html
    assert company["name"] in html


@pytest.mark.asyncio
async def test_agreement_other_user_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agreement by another user -> 404 (Purchase scoped by owner)."""
    admin_token = await _admin_token(client, db_session)
    _, _, _, _, purchases = await _setup_purchase(
        client, db_session, admin_token,
        company_suffix="ag2", investor_suffix="inv_ag2",
    )
    sale_purchase = next(p for p in purchases if p["legal_basis"] == "sale")

    other_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_ag_other",
    )

    resp = await client.get(
        f"/api/v1/purchases/{sale_purchase['id']}/agreement",
        headers=auth_headers(other_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agreement_template_missing_500(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agreement when template_id is NULL -> 500.

    Simulates the broken-infra branch (R2 §5.3): we zero out the
    snapshotted template_id on the Purchase row directly, then call
    the endpoint and expect 500 with code agreement_template_missing.
    Reaches the load_agreement_data NULL-template branch (LEFT JOIN
    returns NULL template tuple).
    """
    admin_token = await _admin_token(client, db_session)
    inv_token, _, _, _, purchases = await _setup_purchase(
        client, db_session, admin_token,
        company_suffix="ag3", investor_suffix="inv_ag3",
    )
    sale_purchase = next(p for p in purchases if p["legal_basis"] == "sale")
    purchase_id = UUID(sale_purchase["id"])

    # Directly NULL out the snapshot to simulate the broken-state path.
    await db_session.execute(
        update(Purchase)
        .where(Purchase.id == purchase_id)
        .values(purchase_agreement_template_id=None)
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/purchases/{purchase_id}/agreement",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert body["error"] == "agreement_template_missing"


@pytest.mark.asyncio
async def test_agreement_email_204_mocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /agreement/email -> 204 (mocked send_agreement_email).

    Patches at the router level rather than core/email.send_email so
    we bypass both Mailgun and SMTP paths regardless of test-env config.
    """
    admin_token = await _admin_token(client, db_session)
    inv_token, _, _, _, purchases = await _setup_purchase(
        client, db_session, admin_token,
        company_suffix="ag4", investor_suffix="inv_ag4",
    )
    sale_purchase = next(p for p in purchases if p["legal_basis"] == "sale")

    with patch(
        "app.modules.purchases.agreement_router.send_agreement_email",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        resp = await client.post(
            f"/api/v1/purchases/{sale_purchase['id']}/agreement/email",
            headers=auth_headers(inv_token),
        )

    assert resp.status_code == 204
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_agreement_html_escapes_investor_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """HTML render escapes XSS in investor_name (SEC-NEW-01 closure).

    Sets the investor's profile.first_name to a payload that would be
    dangerous if injected raw, then asserts the literal payload is NOT
    present in the rendered HTML (autoescape replaces < and > with HTML
    entities). We assert the *escaped* form to confirm the value still
    rendered (otherwise the test would pass even if the field was
    silently dropped).
    """
    admin_token = await _admin_token(client, db_session)
    payload = "<script>alert('xss')</script>"

    inv_token, _, _, _, purchases = await _setup_purchase(
        client, db_session, admin_token,
        company_suffix="ag5", investor_suffix="inv_ag5",
        first_name=payload, last_name="Marker",
    )
    sale_purchase = next(p for p in purchases if p["legal_basis"] == "sale")

    resp = await client.get(
        f"/api/v1/purchases/{sale_purchase['id']}/agreement",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    html = resp.text

    # Raw payload must NOT survive autoescape.
    assert "<script>alert(" not in html
    # Escaped marker confirms the name field was actually rendered.
    assert "&lt;script&gt;" in html
    assert "Marker" in html
