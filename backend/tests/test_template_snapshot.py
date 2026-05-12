# =============================================================================
# CBSHOME Backend -- Template Snapshot Tests (iter 2.4-tests, T1 + T2)
# =============================================================================
#
# Purpose:
#   Test augmentation for iter 2.4 (R2 §5.1). The four-stage fallback
#   in find_active_template() and the investor_language snapshot
#   semantics on Purchase.purchase_agreement_template_id are both
#   covered indirectly by the happy-path tests in test_purchase_agreement.py,
#   but no test exercises each fallback level explicitly. This file
#   closes that gap.
#
# T1 -- four-stage fallback chain (R2 §5.1):
#   For each priority level we set up only that level's template and
#   any required upstream-misses, perform a purchase, then assert
#   Purchase.purchase_agreement_template_id matches the expected row.
#
#     L1: company + investor_language
#     L2: company + 'en'
#     L3: platform + investor_language
#     L4: platform + 'en'
#     all-missing: snapshot writes NULL + emits purchase.template_missing
#                  audit event
#
#   A sixth case adds a smoke check on the installment_tranche path
#   (installments/service.py::pay_tranche -> engine.execute) to confirm
#   the same snapshot logic fires when the purchase originates from a
#   tranche payment rather than instant purchase.
#
# T2 -- investor_language snapshot is frozen at purchase time:
#   An investor purchases while User.language='en' (matches an active
#   per-company en template). Afterwards User.language is changed to
#   'ru'. The snapshotted template_id on Purchase MUST NOT change --
#   re-fetching the row still points at the en template.
#
# Isolation strategy:
#   Every fallback test uses a synthetic language code "xx" (not
#   covered by the install-time platform seeds) so that the seeded
#   en platform-default templates can never accidentally win at
#   priority 4 when we're testing priorities 1-3. The level-4 case
#   uses the seeded platform-en template directly (queried by
#   selector, not hardcoded id) to avoid coupling to migration UUIDs.
#
# Email prefix: "tsnap_"
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
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
from scripts.seed_platform_templates import seed_platform_templates
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "tsnap_"

VALID_DIST_CONFIG = {
    "company_pct": 0.65,
    "agent_levels": [0.10, 0.03, 0.01],
}

# Synthetic ISO-like code never seeded by the platform install path.
# Picked so the four-stage fallback can be exercised level by level
# without competing with the seeded en platform default at level 4.
SYNTHETIC_LANG = "xx"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users + any CompanyDocumentTemplate rows we created.

    cleanup_test_users handles the User cascade. The DocumentTemplate
    rows are scoped per-test by company_id (which is created within
    each test, so the cleanup_test_users cascade reaches them via
    ondelete=RESTRICT? -- no, CompanyDocumentTemplate.company_id is
    RESTRICT, so we have to wipe templates ourselves before the user
    cascade fires). Platform templates (company_id IS NULL) we add
    in tests get wiped by language=SYNTHETIC_LANG filter.
    """
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    # Wipe any synthetic-language platform templates we inserted.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.language == SYNTHETIC_LANG,
        )
    )
    await db_session.commit()
    yield
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.language == SYNTHETIC_LANG,
        )
    )
    await db_session.commit()
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


async def _admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _create_company(
    client: AsyncClient, admin_token: str, suffix: str
) -> dict:
    """Staff-side company + pool create. Shape mirrors the helper used
    across the iter 2.4 test files."""
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}co_{suffix}@example.com",
            "password": "companypass123",
            "name": f"Snapshot Co {suffix}",
            "description": f"Snapshot {suffix}",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    company = resp.json()

    pool = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool.status_code == 201, pool.text
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
    client: AsyncClient, admin_token: str, company_id: str, suffix: str
) -> dict:
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Snapshot Package {suffix}",
            "package_size": 100,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
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


async def _register_investor(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str,
    *,
    language: str = "en",
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    """Register investor, approve KYC, set language, deposit funds."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.kyc_status = "approved"
    user.language = language
    user.profile = {"first_name": "T", "last_name": "Snap"}
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


async def _insert_template(
    db_session: AsyncSession,
    *,
    company_id: UUID | None,
    kind: str,
    language: str,
    suffix: str,
) -> CompanyDocumentTemplate:
    """Insert a CompanyDocumentTemplate row directly via ORM.

    No MinIO upload -- snapshot logic in engine.py never reads MinIO
    (it only resolves an id via find_active_template), so a metadata
    row alone is enough to exercise the fallback chain. storage_prefix
    is set to a synthetic path that would never collide with a real
    template; render_*_html() would fail on this row, but the snapshot
    tests don't render.
    """
    template = CompanyDocumentTemplate(
        company_id=company_id,
        kind=kind,
        language=language,
        version=1,
        title=f"Snapshot test template {suffix}",
        storage_prefix=f"_test/snapshot/{suffix}/",
        asset_files=[],
        status=TemplateStatus.ACTIVE,
        created_by=None,
    )
    db_session.add(template)
    await db_session.flush()
    await db_session.commit()
    return template


async def _buy_one_sale_purchase(
    client: AsyncClient, inv_token: str, product_id: str, db_session: AsyncSession
) -> Purchase:
    """Buy through the public purchase endpoint and return the SALE Purchase row."""
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, resp.text
    purchases_json = resp.json()
    sale = next(p for p in purchases_json if p["legal_basis"] == "sale")

    # Re-load through the ORM so we see the snapshotted template_id
    # column (HTTP response doesn't expose it).
    stmt = select(Purchase).where(Purchase.id == UUID(sale["id"]))
    return (await db_session.execute(stmt)).scalar_one()


# ===========================================================================
# T1 -- Four-stage fallback chain
# ===========================================================================


@pytest.mark.asyncio
async def test_snapshot_resolves_level_1_company_lang(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """L1: per-company + investor_language wins over everything else.

    Insert a per-company template at language=SYNTHETIC_LANG. The
    investor's language is set to the same code so L1 is the highest
    priority match.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "l1")
    product = await _create_product(client, admin_token, company["id"], "l1")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # L1 template.
    l1 = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language=SYNTHETIC_LANG,
        suffix="l1",
    )

    inv_token, _ = await _register_investor(
        client, db_session, "inv_l1", language=SYNTHETIC_LANG
    )
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    assert purchase.purchase_agreement_template_id == l1.id


@pytest.mark.asyncio
async def test_snapshot_resolves_level_2_company_en(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """L2: no per-company+lang, falls back to per-company+'en'.

    Investor language is the synthetic code; no L1 template exists.
    A per-company 'en' template is inserted, which must win over any
    platform-level alternative.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "l2")
    product = await _create_product(client, admin_token, company["id"], "l2")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    l2 = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
        suffix="l2",
    )

    inv_token, _ = await _register_investor(
        client, db_session, "inv_l2", language=SYNTHETIC_LANG
    )
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    assert purchase.purchase_agreement_template_id == l2.id


@pytest.mark.asyncio
async def test_snapshot_resolves_level_3_platform_lang(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """L3: no per-company at all, falls back to platform + investor_language.

    Insert a platform template at language=SYNTHETIC_LANG. The seeded
    platform 'en' template still exists (we don't touch it) but L3
    priority beats L4 in the CASE ordering.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "l3")
    product = await _create_product(client, admin_token, company["id"], "l3")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    l3 = await _insert_template(
        db_session,
        company_id=None,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language=SYNTHETIC_LANG,
        suffix="l3",
    )

    inv_token, _ = await _register_investor(
        client, db_session, "inv_l3", language=SYNTHETIC_LANG
    )
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    assert purchase.purchase_agreement_template_id == l3.id


@pytest.mark.asyncio
async def test_snapshot_resolves_level_4_platform_en(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """L4: nothing per-company, no platform+lang, falls back to platform+'en'.

    No L1/L2/L3 setup. Investor language is the synthetic code so the
    platform+'en' seeded row is the only match. We query the seed row
    rather than hardcoding its id.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "l4")
    product = await _create_product(client, admin_token, company["id"], "l4")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # Look up the seeded platform-en row -- never hardcode the id.
    seeded_stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == DocumentTemplateKind.PURCHASE_AGREEMENT,
        CompanyDocumentTemplate.language == "en",
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    )
    seeded = (await db_session.execute(seeded_stmt)).scalar_one_or_none()
    assert seeded is not None, (
        "Platform-default purchase_agreement (en) template is not seeded. "
        "Migrations / seed_platform_templates must run before tests."
    )

    inv_token, _ = await _register_investor(
        client, db_session, "inv_l4", language=SYNTHETIC_LANG
    )
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    assert purchase.purchase_agreement_template_id == seeded.id


@pytest.mark.asyncio
async def test_snapshot_all_levels_miss_writes_null_and_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All four fallback stages miss -> Purchase.purchase_agreement_template_id
    is NULL + a purchase.template_missing audit event is recorded.

    We force the miss by monkeypatching _BASIS_TO_TEMPLATE_KIND to map
    SALE -> "never_seeded_kind". find_active_template then queries for
    a kind that has no rows at any level, which is functionally
    identical to a true four-stage miss (the helper's downstream NULL
    branch is unaware of how the miss was caused). Cleaner than
    DELETE/restore on the seeded platform rows.
    """
    monkeypatch.setattr(
        "app.modules.purchases.engine._BASIS_TO_TEMPLATE_KIND",
        {PurchaseLegalBasis.SALE: "never_seeded_kind"},
    )

    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "miss")
    product = await _create_product(client, admin_token, company["id"], "miss")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _register_investor(client, db_session, "inv_miss")
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    assert purchase.purchase_agreement_template_id is None, (
        "All four fallback stages missed; snapshot must be NULL."
    )

    # purchase.template_missing audit event was recorded against the
    # company. We don't pin actor_id here -- the engine sets it from
    # context.investor_id, but the regression-relevant assertion is
    # just "the audit row exists for this company".
    audit_stmt = select(AuditLog).where(
        AuditLog.event == "purchase.template_missing",
        AuditLog.target_id == UUID(company["id"]),
    )
    audit_row = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit_row is not None, (
        "Engine must emit purchase.template_missing audit on NULL fallthrough."
    )


@pytest.mark.asyncio
async def test_installment_tranche_snapshots_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Smoke test on the installment_tranche code path: pay_tranche ->
    engine.execute -> write_transactions -> _snapshot_template_id.

    We don't exercise all four fallback levels for the installment
    path (the underlying find_active_template helper is identical to
    the sale path -- already covered by L1-L4 above). Instead this
    asserts the path is wired correctly: a per-company
    INSTALLMENT_SUBCONTRACT template at synthetic language is picked
    up and snapshotted onto the installment_tranche Purchase row.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "ins")
    product = await _create_product(client, admin_token, company["id"], "ins")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # INSTALLMENT_SUBCONTRACT per-company template at the synthetic
    # investor language (level 1 for the tranche path).
    expected_template = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.INSTALLMENT_SUBCONTRACT,
        language=SYNTHETIC_LANG,
        suffix="ins",
    )

    # Staff creates a 2-tranche installment template on the product.
    # Total amount = package_size * price_per_unit_cents = 100 * 10000 = 1_000_000.
    plan_config = {
        "tranches": [
            {"amount_cents": 500_000, "units_percent": 50},
            {"amount_cents": 500_000, "units_percent": 50},
        ],
        "bonus_units": 0,
        "agent_bonus_units": 0,
    }
    plan_resp = await client.post(
        f"/api/v1/staff/products/{product['id']}/installments",
        json={"name": "Snapshot Plan", "plan_config": plan_config},
        headers=auth_headers(admin_token),
    )
    assert plan_resp.status_code == 201, plan_resp.text
    plan_template = plan_resp.json()

    inv_token, inv_id = await _register_investor(
        client, db_session, "inv_ins", language=SYNTHETIC_LANG
    )

    # Investor starts the plan -- create_plan() inlines the first
    # tranche payment, which is the installment_tranche purchase whose
    # snapshot we want to inspect.
    start_resp = await client.post(
        f"/api/v1/products/{product['id']}/installment",
        json={
            "product_installment_id": plan_template["id"],
        },
        headers=auth_headers(inv_token),
    )
    assert start_resp.status_code == 201, start_resp.text

    # Find the installment_tranche Purchase for this investor + company.
    tranche_purchase_stmt = select(Purchase).where(
        Purchase.investor_id == inv_id,
        Purchase.company_id == UUID(company["id"]),
        Purchase.legal_basis == PurchaseLegalBasis.INSTALLMENT_TRANCHE,
    )
    tranche_purchase = (
        await db_session.execute(tranche_purchase_stmt)
    ).scalars().first()
    assert tranche_purchase is not None, (
        "create_plan() must produce a Purchase with legal_basis=installment_tranche "
        "for the first tranche payment."
    )

    assert tranche_purchase.purchase_agreement_template_id == expected_template.id


# ===========================================================================
# T2 -- investor_language snapshot is frozen at purchase time
# ===========================================================================


@pytest.mark.asyncio
async def test_snapshot_uses_investor_language_at_purchase_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """investor_language is captured at purchase time and the resulting
    template_id snapshot does not change if the investor later updates
    their language preference (R2 §5.1).

    Setup:
      1. Per-company PURCHASE_AGREEMENT template at language='en'.
      2. Per-company PURCHASE_AGREEMENT template at language='ru' (also active).
      3. Investor starts with language='en'.
      4. Purchase -> snapshot must point at the EN template.
      5. Change investor.language='ru', commit.
      6. Re-fetch the Purchase row -- snapshot is still the EN template id.

    Both EN and RU templates are active simultaneously. The unique
    constraint is on (company_id, kind, language, version), so two
    rows with different languages do not collide.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "fz")
    product = await _create_product(client, admin_token, company["id"], "fz")
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    en_template = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
        suffix="fz_en",
    )
    ru_template = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="ru",
        suffix="fz_ru",
    )

    # Investor starts in English.
    inv_token, inv_id = await _register_investor(
        client, db_session, "inv_fz", language="en"
    )
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    # The EN template won at level 1.
    assert purchase.purchase_agreement_template_id == en_template.id
    assert purchase.purchase_agreement_template_id != ru_template.id

    # After purchase, the investor changes their language preference
    # to Russian. This is independent of any past purchase.
    stmt = select(User).where(User.id == inv_id)
    investor = (await db_session.execute(stmt)).scalar_one()
    investor.language = "ru"
    await db_session.commit()

    # Re-fetch the Purchase row from a fresh query -- the snapshotted
    # template_id must NOT have moved to the RU template.
    refetch_stmt = select(Purchase).where(Purchase.id == purchase.id)
    refetched = (await db_session.execute(refetch_stmt)).scalar_one()

    assert refetched.purchase_agreement_template_id == en_template.id, (
        "Snapshot must be frozen at purchase time; later language "
        "changes on the User row must not move the template id."
    )


# ===========================================================================
# T3 -- Fixture relink (regression guard for iter 2.5 mini-fix #2)
# ===========================================================================


@pytest.mark.asyncio
async def test_platform_template_wipe_relinks_purchase_snapshot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A platform-default DELETE+reseed cycle must leave existing Purchase
    rows with a valid (non-NULL) snapshot id pointing at the freshly-seeded
    active template for the same (kind, language) pair.

    Regression coverage for the iter 2.5 mini-fix #2 cause: the
    isolate_platform_templates fixtures in test_seed_platform_templates.py
    and test_reconcile_platform_templates.py used to wipe all
    platform-default templates in setup and re-seed in teardown without
    a relink pass. FK ON DELETE SET NULL on
    purchases.purchase_agreement_template_id cascaded the wipe onto
    every Purchase row whose snapshot landed on a platform-default
    template -- and the next seed minted fresh UUIDs that didn't match
    the orphaned column. Subsequent agreement_render calls then 500'd
    with 'agreement_render_template_missing' for every affected purchase.

    This test reproduces the wipe + reseed dance inline (without the
    fixture noise) and asserts the relink pass restores the snapshot
    correctly.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "relink")
    product = await _create_product(
        client, admin_token, company["id"], "relink"
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # Investor with language='en' -- L4 (platform-en) wins because we
    # do NOT insert any company-scoped or platform-synthetic templates.
    inv_token, _ = await _register_investor(
        client, db_session, "inv_relink", language="en"
    )
    purchase = await _buy_one_sale_purchase(
        client, inv_token, product["id"], db_session
    )

    # Sanity: snapshot landed on the platform-default en row.
    original_tpl_id = purchase.purchase_agreement_template_id
    assert original_tpl_id is not None, (
        "Purchase must have been snapshotted on a platform default; "
        "test scaffolding is broken if this fires."
    )

    original_tpl = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.id == original_tpl_id
            )
        )
    ).scalar_one()
    assert original_tpl.company_id is None
    assert original_tpl.kind == DocumentTemplateKind.PURCHASE_AGREEMENT
    assert original_tpl.language == "en"

    # Save the relink hint before the wipe, exactly like the fixture does.
    saved_refs = (
        await db_session.execute(
            select(
                Purchase.id,
                CompanyDocumentTemplate.kind,
                CompanyDocumentTemplate.language,
            )
            .join(
                CompanyDocumentTemplate,
                Purchase.purchase_agreement_template_id
                == CompanyDocumentTemplate.id,
            )
            .where(CompanyDocumentTemplate.company_id.is_(None))
        )
    ).all()
    assert any(p_id == purchase.id for p_id, *_ in saved_refs), (
        "Our purchase must be in the saved_refs set."
    )

    # Wipe platform defaults -- the destructive step the old fixture did
    # without a follow-up relink. FK SET NULL fires here.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id.is_(None)
        )
    )
    await db_session.commit()

    # FK SET NULL fires at the DB level, but SQLAlchemy's identity map
    # still holds the pre-cascade Purchase row in memory. A naive
    # `select(Purchase).where(...)` would return the stale ORM object
    # with the original template_id intact, hiding the cascade we're
    # trying to verify. expire_all() drops every cached attribute so
    # the next read goes to the DB.
    db_session.expire_all()

    # Verify the snapshot was nulled by the cascade.
    refetched = (
        await db_session.execute(
            select(Purchase).where(Purchase.id == purchase.id)
        )
    ).scalar_one()
    assert refetched.purchase_agreement_template_id is None, (
        "FK ON DELETE SET NULL should have nulled the snapshot."
    )

    # Re-seed platform defaults (new UUIDs).
    await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()

    # Apply the relink pass.
    for purchase_id, kind, lang in saved_refs:
        new_tpl_id = (
            await db_session.execute(
                select(CompanyDocumentTemplate.id).where(
                    CompanyDocumentTemplate.company_id.is_(None),
                    CompanyDocumentTemplate.kind == kind,
                    CompanyDocumentTemplate.language == lang,
                    CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        if new_tpl_id is not None:
            await db_session.execute(
                update(Purchase)
                .where(Purchase.id == purchase_id)
                .values(purchase_agreement_template_id=new_tpl_id)
            )
    await db_session.commit()

    # Same identity-map concern as above -- expire so the final assert
    # reads the post-relink state from the DB.
    db_session.expire_all()

    # Assert relink succeeded.
    relinked = (
        await db_session.execute(
            select(Purchase).where(Purchase.id == purchase.id)
        )
    ).scalar_one()
    assert relinked.purchase_agreement_template_id is not None, (
        "Relink pass must restore a non-NULL snapshot."
    )
    assert relinked.purchase_agreement_template_id != original_tpl_id, (
        "After re-seed the UUID must be new; if it matches the old one, "
        "either seed_platform_templates is no longer minting fresh ids "
        "or the test setup is wrong."
    )

    new_tpl = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.id
                == relinked.purchase_agreement_template_id
            )
        )
    ).scalar_one()
    assert new_tpl.company_id is None
    assert new_tpl.kind == DocumentTemplateKind.PURCHASE_AGREEMENT
    assert new_tpl.language == "en"
    assert new_tpl.status == TemplateStatus.ACTIVE
