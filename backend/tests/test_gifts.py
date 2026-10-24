# =============================================================================
# AIVIS.ONE Backend -- Gift grant and acceptance Tests
# =============================================================================
#
# Tests cover:
#   1: Staff grants a gift -> 201, purchase in pending_acceptance, nothing
#      credited (no ledger entry, pool consumption unchanged)
#   2: The recipient lists it under /purchases/gifts/pending
#   3: Accepting -> 200, active; a zero-amount ledger entry, the SALE pool
#      is untouched (a staff gift comes from the reserve); accepting again
#      -> 409
#   4: Someone else cannot accept it (404)
#   5: Grant to a user who has not passed KYC -> 400 gift_recipient_not_kyc
#   6: Grant without the financial_operations permission -> 403 (staff
#      without it, and a plain investor)
#   7: Accepting re-checks the recipient's KYC -> 400 kyc_required
#   8: Grant on an archived product / a hidden company -> 400
#   9: Staff cancels a pending gift: status cancelled, no ledger entry, no
#      credit, S-02 stays green;
#      an accepted gift cannot be cancelled; cancel needs the permission
#  10: A pending gift's certificate is not e-mailed -> 404
# =============================================================================

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.companies.models import CompanyProfile
from app.modules.ledgers.models import ActiveLedger
from app.modules.pools.service import get_pool_consumed
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.products.models import Product
from app.modules.purchases.models import Purchase
from app.modules.purchases.service import get_available_packages_map
from app.modules.staff.consistency.service import s_02
from app.modules.staff.models import StaffProfile
from app.modules.users.models import KYCStatus, User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)
import uuid


async def _setup(client: AsyncClient, admin_token: str) -> tuple[str, str]:
    """An active company with a pool and one product. (company_id, product_id)."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"gift_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"GiftCo {uuid.uuid4().hex[:8]}",
            "description": "A test company",
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
    pool = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool.status_code == 201, pool.text
    product = await client.post(
        "/api/v1/staff/products",
        json={"company_id": company_id, "name": "Gift base", "package_size": 10},
        headers=auth_headers(admin_token),
    )
    assert product.status_code == 201, product.text
    # A new product is hidden; a gift is granted only of an active one.
    activated = await client.patch(
        f"/api/v1/staff/products/{product.json()['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activated.status_code == 200, activated.text
    # A new company is hidden too; a gift is granted only in an active one.
    company = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert company.status_code == 200, company.text
    return company_id, product.json()["id"]


async def _grant(
    client: AsyncClient, token: str, user_id: str, product_id: str, units: int = 7
):
    return await client.post(
        "/api/v1/staff/purchases/gifts",
        json={"user_id": user_id, "product_id": product_id, "units": units},
        headers=auth_headers(token),
    )


async def _ledger_rows(db_session: AsyncSession, purchase_id: str) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(ActiveLedger)
            .where(ActiveLedger.reason.like(f"gift:%{purchase_id}%"))
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_grant_stores_a_pending_gift_and_credits_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company_id, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)  # KYC approved by the helper

    consumed_before = await get_pool_consumed(UUID(company_id), db_session)
    resp = await _grant(client, admin_token, recipient["user"]["id"], product_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == PurchaseStatus.PENDING_ACCEPTANCE
    assert body["legal_basis"] == PurchaseLegalBasis.GIFT
    assert body["units"] == 7
    assert body["paid_cents"] == 0

    assert await _ledger_rows(db_session, body["id"]) == 0
    assert await get_pool_consumed(UUID(company_id), db_session) == consumed_before

    pending = await client.get(
        "/api/v1/purchases/gifts/pending",
        headers=auth_headers(recipient["session_token"]),
    )
    assert pending.status_code == 200, pending.text
    assert [g["id"] for g in pending.json()["items"]] == [body["id"]]


@pytest.mark.asyncio
async def test_accept_credits_the_parts_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company_id, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)
    token = recipient["session_token"]

    granted = (
        await _grant(client, admin_token, recipient["user"]["id"], product_id)
    ).json()
    consumed_before = await get_pool_consumed(UUID(company_id), db_session)
    packages_before = await get_available_packages_map(
        db_session,
        company_ids=[UUID(company_id)],
        product_ids=[UUID(product_id)],
    )

    accepted = await client.post(
        f"/api/v1/purchases/{granted['id']}/accept-gift",
        headers=auth_headers(token),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == PurchaseStatus.ACTIVE

    # One zero-amount entry for the recipient (active ledger).
    assert await _ledger_rows(db_session, granted["id"]) == 1
    # A staff gift is given from the reserve: the pool on sale is untouched.
    assert (
        await get_pool_consumed(UUID(company_id), db_session)
        == consumed_before
    )
    # The storefront's available packages agree with the purchase path.
    assert (
        await get_available_packages_map(
            db_session,
            company_ids=[UUID(company_id)],
            product_ids=[UUID(product_id)],
        )
        == packages_before
    )
    row = await db_session.get(Purchase, UUID(granted["id"]))
    await db_session.refresh(row)
    assert row.status == PurchaseStatus.ACTIVE

    again = await client.post(
        f"/api/v1/purchases/{granted['id']}/accept-gift",
        headers=auth_headers(token),
    )
    assert again.status_code == 409
    assert again.json()["error"] == "gift_not_pending"

    pending = await client.get(
        "/api/v1/purchases/gifts/pending", headers=auth_headers(token)
    )
    assert pending.json()["items"] == []


@pytest.mark.asyncio
async def test_someone_else_cannot_accept_the_gift(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    _, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)
    other = await register_user(client)

    granted = (
        await _grant(client, admin_token, recipient["user"]["id"], product_id)
    ).json()
    resp = await client.post(
        f"/api/v1/purchases/{granted['id']}/accept-gift",
        headers=auth_headers(other["session_token"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_grant_needs_a_recipient_who_passed_kyc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    _, product_id = await _setup(client, admin_token)
    unverified = await register_user(client, verified=False)

    resp = await _grant(client, admin_token, unverified["user"]["id"], product_id)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "gift_recipient_not_kyc"


@pytest.mark.asyncio
async def test_grant_requires_the_financial_operations_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    _, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)

    # Staff who lack financial_operations.
    staff, staff_token = await create_staff_user(client, db_session)
    profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == staff.id)
        )
    ).scalar_one()
    perms = dict(profile.permissions)
    perms["financial_operations"] = False
    profile.set_jsonb("permissions", perms)
    await db_session.commit()
    resp = await _grant(client, staff_token, recipient["user"]["id"], product_id)
    assert resp.status_code == 403, resp.text

    # A plain investor is not staff at all.
    resp = await _grant(
        client, recipient["session_token"], recipient["user"]["id"], product_id
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_accept_rechecks_the_recipients_kyc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company_id, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)
    granted = (
        await _grant(client, admin_token, recipient["user"]["id"], product_id)
    ).json()

    user = await db_session.get(User, UUID(recipient["user"]["id"]))
    user.kyc_status = KYCStatus.REVOKED
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/purchases/{granted['id']}/accept-gift",
        headers=auth_headers(recipient["session_token"]),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_required"
    assert await _ledger_rows(db_session, granted["id"]) == 0


@pytest.mark.asyncio
async def test_grant_needs_an_active_product_and_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company_id, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)

    product = await db_session.get(Product, UUID(product_id))
    product.status = "archived"
    await db_session.commit()
    resp = await _grant(client, admin_token, recipient["user"]["id"], product_id)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "product_not_available"

    product.status = "active"
    company = await db_session.get(CompanyProfile, UUID(company_id))
    company.status = "hidden"
    await db_session.commit()
    resp = await _grant(client, admin_token, recipient["user"]["id"], product_id)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "company_not_active"


@pytest.mark.asyncio
async def test_staff_cancels_a_pending_gift_without_any_ledger_entry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company_id, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)
    granted = (
        await _grant(client, admin_token, recipient["user"]["id"], product_id)
    ).json()
    consumed_before = await get_pool_consumed(UUID(company_id), db_session)

    resp = await client.post(
        f"/api/v1/staff/purchases/gifts/{granted['id']}/cancel",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == PurchaseStatus.CANCELLED
    assert await _ledger_rows(db_session, granted["id"]) == 0
    # A cancelled gift is no purchase of the ledger pairing (S-02).
    assert (await s_02(db_session)).status == "pass"
    assert await get_pool_consumed(UUID(company_id), db_session) == consumed_before

    # It leaves the recipient's pending list and cannot be accepted.
    pending = await client.get(
        "/api/v1/purchases/gifts/pending",
        headers=auth_headers(recipient["session_token"]),
    )
    assert pending.json()["items"] == []
    accept = await client.post(
        f"/api/v1/purchases/{granted['id']}/accept-gift",
        headers=auth_headers(recipient["session_token"]),
    )
    assert accept.status_code == 409, accept.text
    assert accept.json()["error"] == "gift_not_pending"

    # Cancelling twice is refused.
    again = await client.post(
        f"/api/v1/staff/purchases/gifts/{granted['id']}/cancel",
        headers=auth_headers(admin_token),
    )
    assert again.status_code == 409, again.text

    # The act is in the audit log.
    audited = (
        await db_session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.event == "purchase.gift_cancelled",
                AuditLog.target_id == UUID(granted["id"]),
            )
        )
    ).scalar_one()
    assert audited == 1


@pytest.mark.asyncio
async def test_an_accepted_gift_cannot_be_cancelled_and_cancel_needs_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    _, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)
    granted = (
        await _grant(client, admin_token, recipient["user"]["id"], product_id)
    ).json()

    not_staff = await client.post(
        f"/api/v1/staff/purchases/gifts/{granted['id']}/cancel",
        headers=auth_headers(recipient["session_token"]),
    )
    assert not_staff.status_code == 403

    accepted = await client.post(
        f"/api/v1/purchases/{granted['id']}/accept-gift",
        headers=auth_headers(recipient["session_token"]),
    )
    assert accepted.status_code == 200, accepted.text

    resp = await client.post(
        f"/api/v1/staff/purchases/gifts/{granted['id']}/cancel",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "gift_not_pending"


@pytest.mark.asyncio
async def test_a_pending_gifts_certificate_is_not_emailed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    _, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)
    granted = (
        await _grant(client, admin_token, recipient["user"]["id"], product_id)
    ).json()

    resp = await client.post(
        f"/api/v1/purchases/{granted['id']}/agreement/email",
        headers=auth_headers(recipient["session_token"]),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_grant_needs_the_administrator_mark_but_cancel_does_not(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    _, product_id = await _setup(client, admin_token)
    recipient = await register_user(client)

    # Default staff hold financial_operations but not every permission.
    _, staff_token = await create_staff_user(client, db_session)
    refused = await _grant(client, staff_token, recipient["user"]["id"], product_id)
    assert refused.status_code == 403, refused.text

    granted = await _grant(client, admin_token, recipient["user"]["id"], product_id)
    assert granted.status_code == 201, granted.text
    cancelled = await client.post(
        f"/api/v1/staff/purchases/gifts/{granted.json()['id']}/cancel",
        headers=auth_headers(staff_token),
    )
    assert cancelled.status_code == 200, cancelled.text
