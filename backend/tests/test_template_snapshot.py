# =============================================================================
# CBSHOME Backend -- Template Snapshot Tests (iter 2.5 mini-fix #3)
# =============================================================================
#
# What is tested:
#   At purchase creation time the resolved active CompanyDocumentTemplate
#   row's id is captured on the purchase as purchase_agreement_template_id.
#   This snapshot pin guarantees that subsequent renders use the version
#   in force when the purchase was created -- not whatever staff might
#   archive or replace later.
#
# Three scenarios:
#   T1 -- happy path: new purchase pins the active platform-default row.
#   T2 -- after the platform-default row is archived (NOT deleted), the
#         pinned row is still reachable. Render does not 500.
#   T3 -- after the platform-default row is DELETEd entirely, the
#         pinned row is gone. Render correctly fails with
#         agreement_template_missing.
#
# Why mutating / deleting platform-default rows is now safe in tests:
#   Each pytest worker runs against its own ephemeral Postgres database
#   (cbshome_test_<worker_id>, cloned from cbshome_test_template). T2's
#   archive and T3's DELETE are scoped to that one worker DB and vanish
#   in pytest_unconfigure. Under the old shared-DB regime these would
#   have leaked and broken ~17 unrelated tests; that whole class of
#   bug is gone with the conftest rewrite.
# =============================================================================

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.constants import TemplateKind, TemplateStatus
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.companies.template_service import find_active_template
from tests.helpers import (
    auth_headers,
    create_staff_user,
    register_user,
)


# All purchases in these tests target the (purchase_agreement, en) pair
# because purchase_agreement is what /agreement/* endpoints actually use.
TARGET_KIND = TemplateKind.PURCHASE_AGREEMENT
TARGET_LANGUAGE = "en"

EMAIL_PREFIX = "tsnap_"


# ---------------------------------------------------------------------------
# Tiny per-test setup: build a Purchase via the public flows so the
# snapshot pin happens through the same code path production uses.
# ---------------------------------------------------------------------------


async def _setup_company_with_product(
    client: AsyncClient,
    session: AsyncSession,
    *,
    staff_email: str,
    company_name: str,
) -> tuple[str, str, str, str]:
    """Stand up one staff user, one company, one pool, one product.
    Returns (staff_token, company_id, pool_id, product_id).

    Inline rather than a shared fixture because the three tests use it
    in slightly different ways and we want each test to remain readable
    end-to-end.
    """
    _, staff_token = await create_staff_user(
        client, session, email=staff_email
    )

    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "name": company_name,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 201, resp.text
    company_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/pools",
        json={"total_options": 1_000_000, "equity_percent": 100.0},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 201, resp.text
    pool_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/products",
        json={
            "pool_id": pool_id,
            "package_size": 100,
            "price_per_option_cents": 10_000,
        },
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 201, resp.text
    product_id = resp.json()["id"]

    # Publish company + product so the storefront accepts purchases.
    await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "published"},
        headers=auth_headers(staff_token),
    )
    await client.patch(
        f"/api/v1/staff/companies/{company_id}/products/{product_id}",
        json={"status": "active"},
        headers=auth_headers(staff_token),
    )

    return staff_token, company_id, pool_id, product_id


async def _create_purchase(
    client: AsyncClient,
    *,
    investor_email: str,
    company_id: str,
    product_id: str,
) -> dict:
    """Register a new investor, deposit funds, execute one purchase.
    Returns the purchase response body.
    """
    data = await register_user(client, email=investor_email)
    investor_token = data["session_token"]

    # Crypto deposit (test webhook bypass).
    deposit_resp = await client.post(
        "/api/v1/test/deposits/crypto",
        json={
            "tx_hash": f"0xtest_{uuid.uuid4().hex[:8]}",
            "amount_cents": 2_000_000,
            "network": "TRC20",
        },
        headers=auth_headers(investor_token),
    )
    assert deposit_resp.status_code in (200, 201), deposit_resp.text

    resp = await client.post(
        f"/api/v1/storefront/companies/{company_id}/products/{product_id}/purchase",
        json={"package_count": 1},
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# T1 -- purchase pins the active platform-default row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_pins_active_platform_template(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """The new purchase's purchase_agreement_template_id matches the
    active platform-default row that find_active_template would return
    at that moment.
    """
    _, company_id, _, product_id = await _setup_company_with_product(
        client,
        db_session,
        staff_email=f"{EMAIL_PREFIX}t1_staff@example.com",
        company_name="T1 Company",
    )

    # Snapshot the active platform-default row BEFORE the purchase.
    snapshot = await find_active_template(
        db_session,
        company_id=uuid.UUID(company_id),
        kind=TARGET_KIND,
        language=TARGET_LANGUAGE,
    )
    assert snapshot is not None
    assert snapshot.company_id is None  # platform default

    purchase = await _create_purchase(
        client,
        investor_email=f"{EMAIL_PREFIX}t1_inv@example.com",
        company_id=company_id,
        product_id=product_id,
    )

    assert purchase["purchase_agreement_template_id"] == str(snapshot.id), (
        f"purchase pinned {purchase['purchase_agreement_template_id']!r}, "
        f"expected {str(snapshot.id)!r}"
    )


# ---------------------------------------------------------------------------
# T2 -- archived platform-default still serves the pinned purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_after_archive_uses_pinned_template(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Archive the platform-default row that a purchase pinned. The
    rendered agreement endpoint must still succeed because the pin
    references the row by id, not by status.
    """
    _, company_id, _, product_id = await _setup_company_with_product(
        client,
        db_session,
        staff_email=f"{EMAIL_PREFIX}t2_staff@example.com",
        company_name="T2 Company",
    )

    purchase = await _create_purchase(
        client,
        investor_email=f"{EMAIL_PREFIX}t2_inv@example.com",
        company_id=company_id,
        product_id=product_id,
    )
    pinned_id = uuid.UUID(purchase["purchase_agreement_template_id"])

    # Archive the pinned platform-default row directly. This is the
    # mutation that historically leaked into the shared dev DB; it is
    # now safe -- only this worker's DB sees it.
    result = await db_session.execute(
        select(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.id == pinned_id
        )
    )
    pinned = result.scalar_one()
    assert pinned.company_id is None, (
        "T2 invariant violated: pinned row must be a platform-default"
    )
    pinned.status = TemplateStatus.ARCHIVED
    await db_session.commit()

    # The agreement endpoint resolves by purchase_agreement_template_id,
    # so it must still find the (now archived) row and render OK.
    investor_resp = await client.post(
        "/api/v1/auth/email/login",
        json={
            "email": f"{EMAIL_PREFIX}t2_inv@example.com",
            "password": "Password123!",
        },
    )
    investor_token = investor_resp.json()["session_token"]

    resp = await client.get(
        f"/api/v1/purchases/{purchase['id']}/agreement",
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# T3 -- deleted platform-default row causes a clean template_missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_after_delete_returns_template_missing(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """If the pinned platform-default row is physically DELETEd, the
    render path must fail cleanly with agreement_template_missing --
    NOT a 200 against some unrelated row, and NOT a generic 500.
    """
    _, company_id, _, product_id = await _setup_company_with_product(
        client,
        db_session,
        staff_email=f"{EMAIL_PREFIX}t3_staff@example.com",
        company_name="T3 Company",
    )

    purchase = await _create_purchase(
        client,
        investor_email=f"{EMAIL_PREFIX}t3_inv@example.com",
        company_id=company_id,
        product_id=product_id,
    )
    pinned_id = uuid.UUID(purchase["purchase_agreement_template_id"])

    # Defensive: assert the row we are about to nuke really is the pin.
    result = await db_session.execute(
        select(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.id == pinned_id
        )
    )
    pinned = result.scalar_one()
    assert pinned.company_id is None, (
        "T3 invariant violated: pinned row must be a platform-default"
    )

    # Hard delete.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.id == pinned_id
        )
    )
    await db_session.commit()

    # Investor logs in and asks for the agreement -- should be a clean fail.
    investor_resp = await client.post(
        "/api/v1/auth/email/login",
        json={
            "email": f"{EMAIL_PREFIX}t3_inv@example.com",
            "password": "Password123!",
        },
    )
    investor_token = investor_resp.json()["session_token"]

    resp = await client.get(
        f"/api/v1/purchases/{purchase['id']}/agreement",
        headers=auth_headers(investor_token),
    )
    # Service raises TemplateMissingError, which the router maps to 500
    # with the agreement_template_missing error code in the body.
    assert resp.status_code == 500
    assert resp.json().get("error") == "agreement_template_missing"
