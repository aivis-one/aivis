# =============================================================================
# CBSHOME Backend -- Purchase Template Snapshot Tests
#                     (iter 2.5 mini-fix #3 rewrite)
# =============================================================================
#
# Tests cover Refactor 2 iter 2.4 contract (R2 §5.1) for
# Purchase.purchase_agreement_template_id:
#
#   T1. After a successful purchase against a company with no per-company
#       templates, the snapshot points at an ACTIVE platform-default row
#       (find_active_template stage 4: platform + en). T1 does NOT mutate
#       any platform row -- only reads.
#
#   T2. After the snapshotted template is ARCHIVED (status flipped to
#       archived, row NOT deleted), the snapshot id is unchanged: the
#       Purchase row keeps rendering against its frozen template, as
#       reconcile expects.
#       T2 archives a PER-COMPANY template, never a platform default.
#
#   T3. Physically deleting the snapshotted template row triggers the FK
#       ON DELETE SET NULL cascade and nulls the snapshot.
#       T3 deletes a PER-COMPANY template, never a platform default.
#
# WHAT CHANGED IN iter 2.5 mini-fix #3:
#   The previous T2 archived an ACTIVE platform-default row and
#   committed; the previous T3 physically DELETED an ACTIVE platform-
#   default row and committed. Both mutations bled past conftest
#   rollback into the live DB and broke the ТЗ §7 invariant ("all 16
#   active platform-default rows present after `cbshome update`"). On
#   the next pytest pass the live DB had no active row for
#   (purchase_agreement, en) and seed_platform_templates couldn't
#   recover because it hardcoded version=1, which collided with the
#   archived row left behind.
#
#   The replacement creates a PER-COMPANY template that wins stage 1
#   of find_active_template (per-company + user-lang); the snapshot
#   then points at the per-company row, and T2/T3 mutate that row only.
#   Platform defaults are untouched. The defensive assertion
#   `assert snapshot_id == per_company_template.id` guarantees the
#   test fails CLEANLY (before any mutation) if stage 1 doesn't fire
#   for any reason.
#
# NO DESTRUCTIVE FIXTURE:
#   No teardown deletes platform-default rows. Per-company rows that
#   tests create are cleaned up automatically by cleanup_test_users
#   (helpers.py wipes templates whose company_id is in the doomed
#   company set -- platform-defaults with company_id IS NULL never
#   match).
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


# Standard placeholder asset list for inline per-company template rows.
# The rendering surface is not exercised in these snapshot tests; we
# only care that find_active_template picks the row up and that the FK
# wiring on Purchase.purchase_agreement_template_id behaves correctly.
PER_COMPANY_ASSET_FILES = ["logo.png", "signature.png", "stamp.png"]


@pytest.fixture(autouse=True)
async def cleanup(
    db_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Wipe test users (and their templates / companies / purchases)
    after each test so successive runs don't accumulate.

    Platform-default CompanyDocumentTemplate rows are NEVER touched --
    cleanup_test_users only deletes templates with company_id in the
    doomed company list (NULL never matches), and never deletes by
    created_by IS NULL.
    """
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Scaffolding helpers
# ---------------------------------------------------------------------------


async def _admin_user_and_token(
    client: AsyncClient, db_session: AsyncSession, suffix: str
) -> tuple[UUID, str]:
    """Create admin staff; return (admin_user_id, admin_token).

    Returning admin_user_id lets T2/T3 stamp it on the created_by column
    of inline per-company template rows (FK to users.id with RESTRICT
    so NULL is fine but a real staff user matches what reconcile would
    have written).
    """
    data, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin_{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), token


async def _activate_company_and_create_product(
    client: AsyncClient, admin_token: str, suffix: str
) -> tuple[UUID, str]:
    """Build a tiny company + product, activate both.

    Returns (company_id as UUID, product_id as string). company_id is
    returned as UUID rather than the API's string because T2/T3 use it
    in ORM queries.
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
    company_id = UUID(company["id"])

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, pool_resp.text

    product_resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": str(company_id),
            "name": f"Snapshot Package {suffix}",
            "package_size": 100,
        },
        headers=auth_headers(admin_token),
    )
    assert product_resp.status_code == 201, product_resp.text
    product = product_resp.json()

    activate_co = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
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

    return company_id, product["id"]


async def _register_funded_investor(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str,
    *,
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    """Register an investor, approve KYC, set language='en', top up
    active ledger. Returns (session_token, user_id).
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


async def _insert_per_company_active_template(
    db_session: AsyncSession,
    *,
    company_id: UUID,
    kind: DocumentTemplateKind,
    language: str,
    created_by: UUID,
    title: str,
) -> CompanyDocumentTemplate:
    """Insert one active per-company CompanyDocumentTemplate row for
    (company_id, kind, language) at version=1 and commit.

    No MinIO upload -- T2 and T3 exercise only the DB-side semantics
    of snapshot resolution and FK behaviour. Rendering surfaces (which
    would actually try to read template.html from MinIO) are covered by
    test_purchase_agreement.py and test_ownership_certificate.py.

    The commit is required because the next step (_buy_one_sale_purchase)
    issues an HTTP request that runs on its own DB session; that session
    must see this row to pick it up via find_active_template stage 1.
    """
    row = CompanyDocumentTemplate(
        company_id=company_id,
        kind=kind,
        language=language,
        version=1,
        title=title,
        storage_prefix=(
            f"companies/{company_id}/templates/{kind}/{language}/"
        ),
        asset_files=list(PER_COMPANY_ASSET_FILES),
        status=TemplateStatus.ACTIVE,
        created_by=created_by,
    )
    db_session.add(row)
    await db_session.commit()
    # Refresh so subsequent reads see the row id and any server-set
    # defaults (created_at).
    await db_session.refresh(row)
    return row


async def _buy_one_sale_purchase(
    client: AsyncClient,
    investor_token: str,
    product_id: str,
    db_session: AsyncSession,
) -> Purchase:
    """Buy through the public purchase endpoint and return the SALE
    Purchase row loaded via ORM so the snapshot column is visible.
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
# T1 -- Snapshot lands on a platform-default active row (read-only test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_snapshots_active_platform_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A fresh purchase against a company with NO per-company templates
    snapshots the active platform-default for (purchase_agreement, en).

    T1 only reads platform-default rows; no mutation happens.
    """
    _, admin_token = await _admin_user_and_token(client, db_session, "t1")
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
    the Purchase snapshot id unchanged.

    This is the path reconcile takes when a new active is uploaded
    (R2 §4.9): old row -> ARCHIVED, new row -> ACTIVE; historical
    Purchases must keep rendering against the archived snapshot.

    T2 archives a PER-COMPANY template, not a platform default. The
    snapshot is forced onto the per-company row by inserting it before
    the purchase so find_active_template's stage 1 (company + user_lang)
    wins over stage 4 (platform + en).
    """
    admin_user_id, admin_token = await _admin_user_and_token(
        client, db_session, "t2"
    )
    company_id, product_id = await _activate_company_and_create_product(
        client, admin_token, "t2"
    )

    # Per-company template that find_active_template's stage 1 will
    # find when investor.language="en". After this commit the row is
    # visible to the HTTP request that _buy_one_sale_purchase issues.
    per_company_tpl = await _insert_per_company_active_template(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
        created_by=admin_user_id,
        title=f"Snapshot {EMAIL_PREFIX}t2 PA EN v1",
    )

    inv_token, _ = await _register_funded_investor(
        client, db_session, "inv_t2"
    )

    purchase = await _buy_one_sale_purchase(
        client, inv_token, product_id, db_session
    )
    snapshot_id = purchase.purchase_agreement_template_id
    purchase_id = purchase.id

    # Defensive assertion: if the snapshot did NOT land on our per-
    # company row (because of an unexpected find_active_template
    # decision), the test must FAIL HERE -- before any mutation -- so
    # we never accidentally archive a platform default.
    assert snapshot_id == per_company_tpl.id, (
        f"Snapshot must point at our per-company template "
        f"{per_company_tpl.id} (stage 1 win for company={company_id}, "
        f"language=en). Got {snapshot_id} instead. Refusing to "
        f"archive whatever row that points at."
    )

    # Archive the per-company template via ORM (no DELETE -- only a
    # status flip, matching the reconcile flow).
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

    # And the template row still exists, just archived.
    archived_tpl = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.id == snapshot_id
            )
        )
    ).scalar_one()
    assert archived_tpl.status == TemplateStatus.ARCHIVED
    assert archived_tpl.company_id == company_id, (
        "Sanity check: the row we just archived must be per-company, "
        "not a platform default."
    )


# ---------------------------------------------------------------------------
# T3 -- FK ON DELETE SET NULL regression (per-company DELETE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_physical_template_delete_nulls_purchase_snapshot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Physically DELETING the snapshotted template row triggers the FK
    `ON DELETE SET NULL` cascade and nulls
    Purchase.purchase_agreement_template_id.

    The cascade is the safety-net that lets Staff clean up old archived
    template rows without orphaning Purchase.template_id references
    (R2 §5.1, comment in Purchases model). We exercise it on a
    PER-COMPANY row to keep the platform-default invariant from
    ТЗ §7 intact across pytest runs.

    The test reads the Purchase row through a SEPARATE session factory
    call so the SQLAlchemy identity map cannot serve a stale cached
    object. A fresh session has no cache for the Purchase row, so the
    re-select goes to the DB and observes the cascade.
    """
    admin_user_id, admin_token = await _admin_user_and_token(
        client, db_session, "t3"
    )
    company_id, product_id = await _activate_company_and_create_product(
        client, admin_token, "t3"
    )

    per_company_tpl = await _insert_per_company_active_template(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
        created_by=admin_user_id,
        title=f"Snapshot {EMAIL_PREFIX}t3 PA EN v1",
    )

    inv_token, _ = await _register_funded_investor(
        client, db_session, "inv_t3"
    )

    purchase = await _buy_one_sale_purchase(
        client, inv_token, product_id, db_session
    )
    snapshot_id = purchase.purchase_agreement_template_id
    purchase_id = purchase.id

    # Same defensive check as T2: refuse to DELETE unless the snapshot
    # is OUR per-company row.
    assert snapshot_id == per_company_tpl.id, (
        f"Snapshot must point at our per-company template "
        f"{per_company_tpl.id} (stage 1 win for company={company_id}, "
        f"language=en). Got {snapshot_id} instead. Refusing to "
        f"DELETE whatever row that points at -- this would have hit a "
        f"platform default in the previous iteration of this test."
    )

    # Physically delete just THIS per-company row. cleanup_test_users
    # would also remove it later as part of the company teardown, but
    # we need the DELETE to happen NOW so the FK cascade fires within
    # the test's assertion window.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.id == snapshot_id
        )
    )
    await db_session.commit()

    # Read through a fresh session to bypass the identity map.
    factory = get_session_factory()
    async with factory() as fresh_session:
        refetched = (
            await fresh_session.execute(
                select(Purchase).where(Purchase.id == purchase_id)
            )
        ).scalar_one()
        assert refetched.purchase_agreement_template_id is None, (
            "FK ON DELETE SET NULL must null the snapshot when the "
            "per-company template row is physically removed."
        )
