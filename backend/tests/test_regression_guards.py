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
# =============================================================================

import uuid
from uuid import UUID

import jinja2
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.constants import (
    DocumentTemplateKind,
    TEMPLATE_PLACEHOLDERS,
)
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.agreement_service import (
    load_agreement_data,
    render_agreement_html,
)
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
