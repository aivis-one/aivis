# =============================================================================
# CBSHOME Backend -- Purchase Template Snapshot Tests
#                     (iter 2.5 mini-fix #2 rewrite)
# =============================================================================
#
# Tests cover the Refactor 2 iter 2.4 contract (R2 §5.1) for
# Purchase.purchase_agreement_template_id:
#
#   T1. After a successful purchase, the Purchase row's snapshot column
#       points at an ACTIVE platform-default template matching
#       (company_id=NULL, kind=purchase_agreement, language=en).
#       This is the happy path -- find_active_template's stage 4
#       (platform + en) hits because no per-company template exists.
#
#   T2. After the snapshotted template is ARCHIVED (status flipped, row
#       NOT deleted -- the path reconcile takes when a new active is
#       activated), the Purchase row still points at the archived row.
#       Confirms the snapshot semantic: historical Purchases render
#       against their own frozen template, not the latest one.
#
#   T3. Regression for iter 2.5 mini-fix #2 root cause: when a
#       platform-default template row is physically DELETEd (as the old
#       fixtures did), the FK ON DELETE SET NULL cascade nulls the
#       Purchase snapshot. The test reads the Purchase row through a
#       BRAND NEW session so the SQLAlchemy identity map cannot serve a
#       stale cached object -- this avoids the `expire_all` + greenlet
#       trap that broke the previous regression test.
#
# NO DESTRUCTIVE FIXTURE:
#   Tests do not run a session-wide `DELETE FROM company_document_templates
#   WHERE company_id IS NULL`. T2 and T3 delete only the specific row
#   they snapshotted, and T3 uses a separate Purchase per test so other
#   tests' purchases are not affected.
#
# Email prefix: "tsnap_"
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.constants import PurchaseLegalBasis
from app.modules.purchases.models import Purchase
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)


EMAIL_PREFIX = "tsnap_"

DIST_CONFIG = {
    "company_pct": 0.65,
    "agent_levels": [0.10, 0.03, 0.01],
}


@pytest.fixture(autouse=True)
async def cleanup(
    db_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Wipe any users we created so successive runs don't accumulate.

    Platform-default CompanyDocumentTemplate rows are NOT touched --
    they're shared session state seeded by `cbshome update`, and any
    deletion here would re-introduce the iter 2.5 bug.
    """
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Scaffolding helpers (inline -- no carry-over from the old file)
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession, suffix: str
) -> str:
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin_{suffix}@example.com"
    )
    return token


async def _activate_company_and_create_product(
    client: AsyncClient, admin_token: str, suffix: str
) -> tuple[str, str]:
    """Build a tiny company + product, activate both. Returns
    (company_id, product_id) as strings (as returned by the API).
    """
    company_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}co_{suffix}@example.com",
            "password": "companypass123",
            "name": f"Snapshot Co {suffix}",
            "description": f"Snapshot test company {suffix}",
            "price_per_unit_cents": 10000,
            "distribution_config": DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert company_resp.status_code == 201, company_resp.text
    company = company_resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, pool_resp.text

    product_resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": f"Snapshot Package {suffix}",
            "package_size": 100,
        },
        headers=auth_headers(admin_token),
    )
    assert product_resp.status_code == 201, product_resp.text
    product = product_resp.json()

    activate_co = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activate_co.status_code == 200, activate_co.text

    activate_prod = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert activate_prod.status_code == 200, activate_prod.text

    return company["id"], product["id"]


async def _register_funded_investor(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str,
    *,
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    """Register an investor, approve KYC, top up active ledger.

    Defaults to language='en' (set during register; not overridden here)
    so find_active_template's stage 4 (platform + en) is the matching
    branch.
    """
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    user.kyc_status = "approved"
    user.language = "en"
    user.profile = {"first_name": "T", "last_name": "Snap"}
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_{EMAIL_PREFIX}{suffix}",
    )
    await db_session.commit()
    return token, user_id


async def _buy_one_sale_purchase(
    client: AsyncClient,
    investor_token: str,
    product_id: str,
    db_session: AsyncSession,
) -> Purchase:
    """Buy through the public purchase endpoint and return the SALE
    Purchase row reloaded via ORM so the snapshot column is visible.
    """
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(investor_token),
    )
    assert resp.status_code == 201, resp.text
    purchases_json = resp.json()
    sale_dict = next(
        p for p in purchases_json if p["legal_basis"] == "sale"
    )
    sale_id = UUID(sale_dict["id"])

    return (
        await db_session.execute(
            select(Purchase).where(Purchase.id == sale_id)
        )
    ).scalar_one()


# ---------------------------------------------------------------------------
# T1 -- Snapshot lands on a platform-default active row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_snapshots_active_platform_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A fresh purchase against a company with no per-company templates
    snapshots the active platform-default for (purchase_agreement, en).
    """
    admin_token = await _admin_token(client, db_session, "t1")
    _, product_id = await _activate_company_and_create_product(
        client, admin_token, "t1"
    )
    inv_token, _ = await _register_funded_investor(
        client, db_session, "inv_t1"
    )

    purchase = await _buy_one_sale_purchase(
        client, inv_token, product_id, db_session
    )

    assert purchase.purchase_agreement_template_id is not None, (
        "Snapshot must be non-NULL: platform default for "
        "(purchase_agreement, en) is seeded by `cbshome update` and "
        "find_active_template's stage 4 must hit."
    )

    tpl = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.id
                == purchase.purchase_agreement_template_id
            )
        )
    ).scalar_one()
    assert tpl.company_id is None
    assert tpl.kind == DocumentTemplateKind.PURCHASE_AGREEMENT
    assert tpl.language == "en"
    assert tpl.status == TemplateStatus.ACTIVE


# ---------------------------------------------------------------------------
# T2 -- Snapshot survives an archive (status flip, not delete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_survives_template_archive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Flipping the snapshotted template's status to ARCHIVED leaves
    the Purchase snapshot id unchanged. This is the path
    reconcile_platform_templates takes when a new active is uploaded
    (R2 §4.9): old row -> ARCHIVED, new row -> ACTIVE; historical
    Purchases must keep rendering against the archived snapshot.
    """
    admin_token = await _admin_token(client, db_session, "t2")
    _, product_id = await _activate_company_and_create_product(
        client, admin_token, "t2"
    )
    inv_token, _ = await _register_funded_investor(
        client, db_session, "inv_t2"
    )

    purchase = await _buy_one_sale_purchase(
        client, inv_token, product_id, db_session
    )
    snapshot_id = purchase.purchase_agreement_template_id
    purchase_id = purchase.id
    assert snapshot_id is not None

    # Archive the snapshotted template via ORM (no row delete).
    tpl = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.id == snapshot_id
            )
        )
    ).scalar_one()
    tpl.status = TemplateStatus.ARCHIVED
    await db_session.commit()

    # Re-read the Purchase row -- snapshot must still point at the
    # archived template.
    refetched = (
        await db_session.execute(
            select(Purchase).where(Purchase.id == purchase_id)
        )
    ).scalar_one()
    assert refetched.purchase_agreement_template_id == snapshot_id

    # And the template row still exists, just with archived status.
    archived_tpl = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.id == snapshot_id
            )
        )
    ).scalar_one()
    assert archived_tpl.status == TemplateStatus.ARCHIVED


# ---------------------------------------------------------------------------
# T3 -- Regression: FK ON DELETE SET NULL on physical template delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_physical_template_delete_nulls_purchase_snapshot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Physically DELETING the snapshotted template row triggers the FK
    `ON DELETE SET NULL` cascade and nulls Purchase.purchase_agreement_template_id.

    This was the iter 2.5 bug: the old `isolate_platform_templates`
    fixtures wiped all `company_id IS NULL` template rows in setup,
    cascading NULL onto every Purchase whose snapshot lived on a
    platform default. Nothing relinked, so investors saw 500s on
    agreement preview.

    The test uses a SEPARATE session factory call for the post-delete
    read. This avoids two SQLAlchemy quirks at once:
      - identity map serving the pre-delete cached `purchase` object,
      - `expire_all` + greenlet errors when reading from an expired
        ORM object inside the same async session that issued the
        commit.
    A fresh session has no cache for the Purchase row, so the
    re-select goes to the DB and observes the cascade.
    """
    admin_token = await _admin_token(client, db_session, "t3")
    _, product_id = await _activate_company_and_create_product(
        client, admin_token, "t3"
    )
    inv_token, _ = await _register_funded_investor(
        client, db_session, "inv_t3"
    )

    purchase = await _buy_one_sale_purchase(
        client, inv_token, product_id, db_session
    )
    snapshot_id = purchase.purchase_agreement_template_id
    purchase_id = purchase.id
    assert snapshot_id is not None

    # Physically delete just THIS template row. Surgical -- other
    # platform defaults remain in place so other tests are unaffected.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.id == snapshot_id
        )
    )
    await db_session.commit()

    # Read through a fresh session to bypass identity map entirely.
    factory = get_session_factory()
    async with factory() as fresh_session:
        refetched = (
            await fresh_session.execute(
                select(Purchase).where(Purchase.id == purchase_id)
            )
        ).scalar_one()
        assert refetched.purchase_agreement_template_id is None, (
            "FK ON DELETE SET NULL must null the snapshot when the "
            "template row is physically removed."
        )
