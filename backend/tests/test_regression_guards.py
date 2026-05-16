# =============================================================================
# CBSHOME Backend -- Regression Guards
# =============================================================================
#
# Anti-regression tests for previously-fixed bugs. NOT CRUD coverage.
# These are kept here so a coordinated test-cleanup (removing CRUD tests
# en masse) cannot delete them by accident -- the file name announces
# that everything inside is load-bearing.
#
# Each test references the round / bug ID it guards against and explains
# what would silently regress without it. Stay static where possible
# (no fixtures, no DB) so the guards run cheaply and break at import
# time rather than during a full HTTP setup. Some guards (BUG-11-01)
# unavoidably need a real Purchase to exercise the render pipeline --
# those use the same lightweight HTTP setup pattern that test_purchases
# uses, with UUID-generated emails for isolation.
#
# Bug catalogue:
#   BUG-11-01  -- TEMPLATE_PLACEHOLDERS coverage in render context
#                 (per-purchase agreement AND ownership certificate)
#   SEC-11-01  -- OwnershipData must not carry full User ORM
#   R2-§5.1    -- Purchase.purchase_agreement_template_id snapshot is
#                 resolved via the 4-stage fallback in find_active_template
#                 (L1 per-company+lang, L2 per-company+en, L3 platform+lang,
#                  L4 platform+en) and frozen at purchase time
# =============================================================================

import uuid
from uuid import UUID

import jinja2
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TEMPLATE_PLACEHOLDERS,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.agreement_service import (
    load_agreement_data,
    render_agreement_html,
)
from app.modules.purchases.constants import PurchaseLegalBasis
from app.modules.purchases.models import Purchase
from app.modules.purchases.ownership_certificate_service import (
    OwnershipData,
    load_ownership_data,
    render_ownership_html,
)
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)


# Synthetic ISO-like language code never covered by the platform seed
# (the install script only seeds en/ru/de/ar). Lets the L1/L2/L3 guards
# test their fallback level without competing with seeded L4 rows.
SYNTHETIC_LANG = "xx"


# ---------------------------------------------------------------------------
# Setup helpers -- local to this file, kept minimal. Pattern mirrors
# test_purchases.py but trimmed to what these guards need (one Company,
# one Product, one Purchase).
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create an admin and return its session token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company_with_product(
    client: AsyncClient,
    admin_token: str,
) -> tuple[dict, dict]:
    """Stand up one active Company + one active Product + its OptionPool.

    The staff endpoint creates the company-owner User in the same call,
    so credentials are part of the body. Pool is required before any
    Product can attach to it (Sprint 4.3).
    """
    co_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": "Regression Co",
            "description": "Stand-in company for render-context guards",
            "price_per_unit_cents": 10000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert co_resp.status_code == 201, co_resp.text
    company = co_resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, pool_resp.text

    prod_resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Regression Package",
            "package_size": 100,
        },
        headers=auth_headers(admin_token),
    )
    assert prod_resp.status_code == 201, prod_resp.text
    product = prod_resp.json()

    co_act = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert co_act.status_code == 200, co_act.text

    prod_act = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert prod_act.status_code == 200, prod_act.text

    return company, product


async def _create_investor_and_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
    product_id: str,
    *,
    balance_cents: int = 2_000_000,
) -> tuple[UUID, UUID]:
    """Register investor, approve KYC, deposit balance, execute ONE purchase.

    Returns (investor_id, sale_purchase_id). The SALE Purchase row is
    what both agreement and ownership guards need; the agreement
    renderer requires Purchase.legal_basis = sale, ownership rolls it
    into total_units.
    """
    data = await register_user(client)
    inv_token = data["session_token"]
    inv_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == inv_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=inv_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    buy_resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert buy_resp.status_code == 201, buy_resp.text
    purchases = buy_resp.json()
    sale = next(p for p in purchases if p["legal_basis"] == "sale")
    return inv_id, UUID(sale["id"])


# ---------------------------------------------------------------------------
# Additional helpers for the template-snapshot guards (R2 §5.1).
# ---------------------------------------------------------------------------


async def _insert_template(
    db_session: AsyncSession,
    *,
    company_id: UUID | None,
    kind: str,
    language: str,
) -> CompanyDocumentTemplate:
    """Insert a CompanyDocumentTemplate row directly via ORM.

    No MinIO upload -- the snapshot logic in engine.py only resolves
    an id via find_active_template, never reads template bodies, so
    a metadata row alone exercises the fallback chain. storage_prefix
    is a synthetic path that would never collide with a real template.

    version is UUID-randomized to avoid the (company_id, kind, language,
    version) unique constraint colliding with rows left from prior test
    runs. 7 hex digits -> max 268M, fits Integer (int32) safely.
    """
    template = CompanyDocumentTemplate(
        company_id=company_id,
        kind=kind,
        language=language,
        version=int(uuid.uuid4().hex[:7], 16),
        title=f"Snapshot guard {kind}/{language}",
        storage_prefix=f"_test/snapshot/{uuid.uuid4().hex[:8]}/",
        asset_files=[],
        status=TemplateStatus.ACTIVE,
        created_by=None,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def _make_purchase_with_language(
    client: AsyncClient,
    db_session: AsyncSession,
    product_id: str,
    *,
    language: str,
    balance_cents: int = 2_000_000,
) -> tuple[UUID, Purchase]:
    """Same as _create_investor_and_purchase but lets the test pin the
    investor's language before the purchase fires, and returns the
    SALE Purchase ORM row (not just its id) so the test can assert on
    purchase_agreement_template_id without a second query.
    """
    data = await register_user(client)
    inv_token = data["session_token"]
    inv_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == inv_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.kyc_status = "approved"
    user.language = language
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=inv_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    buy_resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert buy_resp.status_code == 201, buy_resp.text
    purchases = buy_resp.json()
    sale_id = UUID(next(p for p in purchases if p["legal_basis"] == "sale")["id"])

    # Fetch ORM row -- the HTTP response does not expose
    # purchase_agreement_template_id.
    purchase_row = (
        await db_session.execute(
            select(Purchase).where(Purchase.id == sale_id)
        )
    ).scalar_one()
    return inv_id, purchase_row


# ---------------------------------------------------------------------------
# Synthetic template builders -- one placeholder per `{{ name }}` so a
# missing key in the render context surfaces as jinja2.UndefinedError
# under StrictUndefined.
# ---------------------------------------------------------------------------


def _build_synthetic_agreement_template(placeholders: frozenset[str]) -> str:
    """Build a Jinja2 template that references every placeholder for the
    per-Purchase doc kinds (purchase_agreement / gift_certificate /
    installment_subcontract).
    """
    return " | ".join(f"{{{{ {name} }}}}" for name in sorted(placeholders))


def _build_synthetic_ownership_template(
    placeholders: frozenset[str],
) -> str:
    """Build a Jinja2 template for the OWNERSHIP_CERTIFICATE kind.

    `purchases` is a list-of-dicts; we iterate it without touching
    sub-keys (TEMPLATE_PLACEHOLDERS only validates top-level names --
    see the comment block above the dict in companies/constants.py).
    Iteration alone is enough proof that `purchases` is in the context.
    """
    top_level = sorted(placeholders - {"purchases"})
    body = " | ".join(f"{{{{ {name} }}}}" for name in top_level)
    if "purchases" in placeholders:
        body += " | {% for p in purchases %}*{% endfor %}"
    return body


# ---------------------------------------------------------------------------
# BUG-11-01 / agreement renderer: per-Purchase render context covers
#                                  TEMPLATE_PLACEHOLDERS for every kind
# ---------------------------------------------------------------------------
#
# render_agreement_html builds ONE context dict that serves three doc
# kinds (PURCHASE_AGREEMENT / GIFT_CERTIFICATE / INSTALLMENT_SUBCONTRACT),
# so the same render path must satisfy the union of all three whitelists.
# Round 11 sync brought those whitelists to identical shape, but if any
# of them is later extended with a key the renderer doesn't supply,
# StrictUndefined will fail loudly at render time. We use StrictUndefined
# itself as the assertion mechanism: drop a synthetic template containing
# every placeholder of the given kind through get_template_html_cached,
# run the real renderer, and assert no UndefinedError fires.
#
# Direction covered: render_context >= TEMPLATE_PLACEHOLDERS[kind].
# Opposite direction (template references unknown var) is covered
# elsewhere by the reconcile parse-time validator.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        DocumentTemplateKind.PURCHASE_AGREEMENT,
        DocumentTemplateKind.GIFT_CERTIFICATE,
        DocumentTemplateKind.INSTALLMENT_SUBCONTRACT,
    ],
)
async def test_render_context_covers_template_placeholders(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """BUG-11-01 regression guard for the per-Purchase agreement render.

    The agreement renderer is shared across the three purchase-related
    doc kinds; the whitelists are currently identical but the test runs
    against each kind to guard against any future divergence.

    Mocking strategy:
      get_template_html_cached -- replaced so we control the template
        body; the real MinIO cache is not consulted.
      make_asset_data_uri_func -- replaced with a no-op factory; the
        synthetic template never calls asset_data_uri(), so the
        returned lambda would only fire on a test-template drift.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)
    inv_id, purchase_id = await _create_investor_and_purchase(
        client, db_session, product["id"]
    )

    data = await load_agreement_data(purchase_id, inv_id, db_session)

    synthetic_html = _build_synthetic_agreement_template(
        TEMPLATE_PLACEHOLDERS[kind]
    )

    async def _mock_get_template_html_cached(_storage_prefix: str) -> str:
        return synthetic_html

    async def _mock_make_asset_data_uri_func(
        _storage_prefix: str, _asset_files: list[str]
    ):
        def _unused(_name: str) -> str:
            raise AssertionError(
                "Synthetic test template should not reference asset_data_uri"
            )
        return _unused

    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.get_template_html_cached",
        _mock_get_template_html_cached,
    )
    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.make_asset_data_uri_func",
        _mock_make_asset_data_uri_func,
    )

    # The render call is what we're asserting: no UndefinedError, no
    # KeyError, no NameError. A successful return string proves every
    # placeholder in TEMPLATE_PLACEHOLDERS[kind] has a matching key in
    # the render context built by render_agreement_html.
    try:
        rendered = await render_agreement_html(data, db_session)
    except jinja2.UndefinedError as exc:
        pytest.fail(
            f"render_agreement_html context missing a key from "
            f"TEMPLATE_PLACEHOLDERS[{kind}]: {exc}"
        )

    # Sanity check: rendered output is non-empty -- defensive guard
    # against the test silently degenerating if the synthetic template
    # construction breaks in a future refactor.
    assert rendered, "Rendered output is empty"


# ---------------------------------------------------------------------------
# BUG-11-01 / ownership renderer: same coverage check for OWNERSHIP_CERTIFICATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_render_context_covers_template_placeholders(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUG-11-01 regression guard for the ownership-certificate render.

    Mocking strategy mirrors the agreement-side test above with one
    extra patch: find_active_template is stubbed to return a sentinel
    template object. The ownership renderer needs one because, unlike
    the per-Purchase agreement (which has a snapshot id on Purchase),
    the ownership renderer resolves the template live every call.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(
        client, admin_token
    )
    inv_id, _ = await _create_investor_and_purchase(
        client, db_session, product["id"]
    )

    data = await load_ownership_data(
        company_id=UUID(company["id"]),
        user_id=inv_id,
        session=db_session,
    )

    synthetic_html = _build_synthetic_ownership_template(
        TEMPLATE_PLACEHOLDERS[DocumentTemplateKind.OWNERSHIP_CERTIFICATE]
    )

    # Stub: find_active_template returns any active template-shaped
    # object; render_ownership_html only reads .storage_prefix and
    # .asset_files off it (both mocked away below).
    fake_template = CompanyDocumentTemplate(
        company_id=None,
        kind=DocumentTemplateKind.OWNERSHIP_CERTIFICATE,
        language="en",
        version=1,
        title="regression stub",
        storage_prefix="_test/regression_ownership/",
        asset_files=[],
        status="active",
        created_by=None,
    )

    async def _mock_find_active_template(**_kwargs):
        return fake_template

    async def _mock_get_template_html_cached(_storage_prefix: str) -> str:
        return synthetic_html

    async def _mock_make_asset_data_uri_func(
        _storage_prefix: str, _asset_files: list[str]
    ):
        def _unused(_name: str) -> str:
            raise AssertionError(
                "Synthetic test template should not reference asset_data_uri"
            )
        return _unused

    monkeypatch.setattr(
        "app.modules.purchases.ownership_certificate_service.find_active_template",
        _mock_find_active_template,
    )
    monkeypatch.setattr(
        "app.modules.purchases.ownership_certificate_service.get_template_html_cached",
        _mock_get_template_html_cached,
    )
    monkeypatch.setattr(
        "app.modules.purchases.ownership_certificate_service.make_asset_data_uri_func",
        _mock_make_asset_data_uri_func,
    )

    try:
        rendered = await render_ownership_html(data, db_session)
    except jinja2.UndefinedError as exc:
        pytest.fail(
            f"render_ownership_html context missing a key from "
            f"TEMPLATE_PLACEHOLDERS[OWNERSHIP_CERTIFICATE]: {exc}"
        )

    assert rendered, "Rendered output is empty"


# ---------------------------------------------------------------------------
# SEC-11-01: OwnershipData does not hold a full User ORM instance
# ---------------------------------------------------------------------------


def test_ownership_data_does_not_hold_user_object() -> None:
    """SEC-11-01 regression guard.

    OwnershipData MUST NOT carry a full User ORM instance. User has
    credentials (password hash), kyc_data, and other sensitive fields
    attached -- routing that through render context would have leaked
    them into Jinja templates and PDF generation memory. Only the
    minimal scalars required for render and audit-log correlation are
    allowed: investor_id (UUID) and investor_language (str), alongside
    the already-extracted investor_name / investor_email.

    Static dataclass-fields inspection -- no fixtures, no DB. Catches
    the regression at collection time without exercising the render
    pipeline.
    """
    fields = OwnershipData.__dataclass_fields__

    assert "investor_user" not in fields, (
        "OwnershipData.investor_user reintroduced -- SEC-11-01 regression. "
        "Carrying full User across render leaks credentials / password_hash "
        "into Jinja context. Use investor_id + investor_language instead."
    )
    assert "investor_id" in fields, (
        "OwnershipData must carry investor_id (UUID) for audit log "
        "correlation in send_ownership_email."
    )
    assert "investor_language" in fields, (
        "OwnershipData must carry investor_language (str) for template "
        "selection in render_ownership_html (4-stage fallback)."
    )


# ---------------------------------------------------------------------------
# R2 §5.1: Purchase.purchase_agreement_template_id snapshot fallback chain
# ---------------------------------------------------------------------------
#
# At purchase time the engine resolves the active template via a
# 4-stage fallback in find_active_template (companies/service.py):
#
#   L1: company_id == X AND language == investor_language
#   L2: company_id == X AND language == 'en'
#   L3: company_id IS NULL AND language == investor_language
#   L4: company_id IS NULL AND language == 'en'
#
# The first match wins; its id is snapshotted onto Purchase. If all
# four stages miss, the column is NULL and a `purchase.template_missing`
# audit row is recorded.
#
# Each guard below isolates one level by inserting only the template
# row required for that level to win. Synthetic language code SYNTHETIC_LANG
# ("xx") is used wherever a non-en language is needed -- the platform
# seed only installs en/ru/de/ar, so SYNTHETIC_LANG cannot accidentally
# match a seeded row at L3 or L4.


@pytest.mark.asyncio
async def test_snapshot_resolves_level_1_company_lang(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """L1: per-company + investor_language wins over every other level."""
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(
        client, admin_token
    )

    l1 = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language=SYNTHETIC_LANG,
    )

    _, purchase = await _make_purchase_with_language(
        client, db_session, product["id"], language=SYNTHETIC_LANG
    )

    assert purchase.purchase_agreement_template_id == l1.id, (
        "L1 (per-company + investor_language) must beat all other levels."
    )


@pytest.mark.asyncio
async def test_snapshot_resolves_level_2_company_en(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """L2: no per-company+lang, falls back to per-company+'en'.

    Investor language is SYNTHETIC_LANG; no L1 template exists. A
    per-company 'en' template is inserted -- it must beat the seeded
    platform-en template (L4) because company_id is more specific.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(
        client, admin_token
    )

    l2 = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
    )

    _, purchase = await _make_purchase_with_language(
        client, db_session, product["id"], language=SYNTHETIC_LANG
    )

    assert purchase.purchase_agreement_template_id == l2.id, (
        "L2 (per-company + 'en') must beat platform-en (L4)."
    )


@pytest.mark.asyncio
async def test_snapshot_resolves_level_3_platform_lang(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """L3: no per-company at all, falls back to platform + investor_language.

    The seeded platform 'en' template (L4) still exists -- we just don't
    touch it -- but L3 priority beats L4 in the CASE ordering when
    investor_language matches.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    l3 = await _insert_template(
        db_session,
        company_id=None,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language=SYNTHETIC_LANG,
    )

    _, purchase = await _make_purchase_with_language(
        client, db_session, product["id"], language=SYNTHETIC_LANG
    )

    assert purchase.purchase_agreement_template_id == l3.id, (
        "L3 (platform + investor_language) must beat platform-en (L4)."
    )


@pytest.mark.asyncio
async def test_snapshot_resolves_level_4_platform_en(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """L4: nothing per-company, no platform+lang, falls back to platform+'en'.

    No L1/L2/L3 inserts. Investor language is a per-test unique code so
    no platform row at L3 priority exists for it -- not even residue
    left by L3-tests from the same or prior runs (those use SYNTHETIC_LANG,
    which is shared). The seeded platform-en row is the only match.
    Look up the seeded row via ORM rather than hardcoding its id --
    the install seed mints a fresh UUID per deployment.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    # Per-test unique language code. String(10) column; this fits at 9 chars.
    # No other test creates platform rows for this code, so the L3 stage
    # cannot match and the test is robust to residual SYNTHETIC_LANG rows
    # left over from earlier L3 runs.
    unique_lang = f"l4_{uuid.uuid4().hex[:6]}"

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

    _, purchase = await _make_purchase_with_language(
        client, db_session, product["id"], language=unique_lang
    )

    assert purchase.purchase_agreement_template_id == seeded.id, (
        "L4 (platform + 'en') is the final fallback and must win when no "
        "more specific template exists."
    )


@pytest.mark.asyncio
async def test_snapshot_all_levels_miss_writes_null_and_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All four fallback stages miss -> Purchase.purchase_agreement_template_id
    is NULL + a purchase.template_missing audit event is recorded.

    We force the miss by monkeypatching _BASIS_TO_TEMPLATE_KIND to map
    SALE -> 'never_seeded_kind'. find_active_template then queries for
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
    company, product = await _create_company_with_product(
        client, admin_token
    )

    _, purchase = await _make_purchase_with_language(
        client, db_session, product["id"], language="en"
    )

    assert purchase.purchase_agreement_template_id is None, (
        "All four fallback stages missed; snapshot must be NULL."
    )

    # purchase.template_missing audit event must be recorded against
    # the company. We don't pin actor_id -- the engine sets it from
    # context.investor_id; the regression-relevant assertion is just
    # that the audit row exists for this company.
    audit_stmt = select(AuditLog).where(
        AuditLog.event == "purchase.template_missing",
        AuditLog.target_id == UUID(company["id"]),
    )
    audit_row = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit_row is not None, (
        "Engine must emit purchase.template_missing audit on NULL fallthrough."
    )


@pytest.mark.asyncio
async def test_snapshot_uses_investor_language_at_purchase_time(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """investor_language is captured at purchase time and the resulting
    template_id snapshot does not move if the investor later updates
    their language preference (R2 §5.1).

    Setup:
      1. Per-company PURCHASE_AGREEMENT template at language='en'.
      2. Per-company PURCHASE_AGREEMENT template at language='ru'.
      3. Investor starts with language='en'.
      4. Purchase -> snapshot must point at the EN template.
      5. Change investor.language='ru', commit.
      6. Re-fetch the Purchase row -- snapshot is still the EN template.

    Both EN and RU templates are active simultaneously. The unique
    constraint is on (company_id, kind, language, version), so two
    rows with different languages do not collide.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(
        client, admin_token
    )

    en_template = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
    )
    ru_template = await _insert_template(
        db_session,
        company_id=UUID(company["id"]),
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="ru",
    )

    inv_id, purchase = await _make_purchase_with_language(
        client, db_session, product["id"], language="en"
    )

    # EN template won at L1 for this purchase.
    assert purchase.purchase_agreement_template_id == en_template.id
    assert purchase.purchase_agreement_template_id != ru_template.id

    # Investor changes language to Russian AFTER the purchase. This is
    # independent of any past purchase.
    stmt = select(User).where(User.id == inv_id)
    investor = (await db_session.execute(stmt)).scalar_one()
    investor.language = "ru"
    await db_session.commit()

    # Re-fetch the Purchase row -- snapshot must NOT have shifted to RU.
    refetch_stmt = select(Purchase).where(Purchase.id == purchase.id)
    refetched = (await db_session.execute(refetch_stmt)).scalar_one()

    assert refetched.purchase_agreement_template_id == en_template.id, (
        "Snapshot must be frozen at purchase time; later language changes "
        "on the User row must not move the template id."
    )
