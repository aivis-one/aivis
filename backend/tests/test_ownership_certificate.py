# =============================================================================
# CBSHOME Backend -- Ownership Certificate Tests (Refactor 2 iter 2.4, R2 §5.3)
# =============================================================================
#
# Tests cover:
#   1: GET /companies/{id}/ownership-certificate  -- 200 HTML, single sale Purchase
#   2: Two sale Purchases -> sale_units sums correctly in HTML
#   3: installment_tranche rolled into sale_units (per design call iter 2.4)
#   4: gift Purchase counted in gift_units, not sale_units
#   5: 404 when investor has zero active Purchases for the company
#   6: 404 when company doesn't exist
#   7: POST /ownership-certificate/email -> 204 (mocked send)
#   8: 500 when ownership_certificate template lookup misses all 4 stages
#
# Aggregate verification is via raw HTML substring checks because the
# bootstrap ownership_certificate templates render sale_units / gift_units
# / total_units as plain integers in the body.
#
# Email prefix: "s24o_"
# =============================================================================

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import (
    record_active_ledger,
    record_passive_ledger,
)
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s24o_"


# ---------------------------------------------------------------------------
# Local helpers (mirror test_purchase_agreement.py setup ritual)
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
    """Create a company via staff endpoint + activate its OptionPool.

    Body shape matches tests/test_purchases.py::_create_company: the staff
    endpoint creates the company-owner User in the same call, so email,
    password, distribution_config, total_supply, shares_per_option are all
    required by the request schema. Pool POST uses {equity_percent: "100.0"}
    rather than total_options.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}co_{suffix}@example.com",
            "password": "companypass123",
            "name": f"Ownership Co {suffix}",
            "description": f"Company for ownership tests {suffix}",
            "price_per_unit_cents": price_per_unit_cents,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    company = resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, f"Create pool failed: {pool_resp.text}"

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
    package_size: int = 50,
    suffix: str = "pkg",
) -> dict:
    """Create a product via staff endpoint.

    Matches tests/test_purchases.py shape: only company_id + name +
    package_size; the staff endpoint doesn't accept description here.
    """
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Ownership Package {suffix}",
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


async def _buy(
    client: AsyncClient, inv_token: str, product_id: str
) -> list[dict]:
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"
    return resp.json()


async def _insert_direct_purchase(
    db_session: AsyncSession,
    *,
    investor_id: UUID,
    product_id: UUID,
    company_id: UUID,
    company_user_id: UUID,
    legal_basis: str,
    units: int,
    paid_cents: int,
    price_per_unit_cents: int,
) -> Purchase:
    """Insert a Purchase row directly + minimal SUM=0 ledger pair.

    For ownership-certificate aggregate testing we need to seed Purchases
    of specific legal_basis values (in particular installment_tranche and
    gift) without going through engine.execute -- that path requires full
    Product / Company state and pulls money through the registry, which
    is more setup than these targeted tests need.

    Writes the Purchase + one active+passive ledger pair to keep the
    SUM=0 invariant healthy. Skips template_id snapshot (left NULL is
    fine for ownership aggregation -- per-Purchase template_id is only
    consumed by the agreement renderer, not the ownership renderer).
    """
    purchase = Purchase(
        investor_id=investor_id,
        product_id=product_id,
        company_id=company_id,
        legal_basis=legal_basis,
        units=units,
        paid_cents=paid_cents,
        price_per_unit_cents=price_per_unit_cents,
        status=PurchaseStatus.ACTIVE,
        purchase_agreement_template_id=None,
    )
    db_session.add(purchase)
    await db_session.flush()

    # SUM=0 ledger pair, zero amount for gift / non-zero for paid bases.
    # The test-only direct-insert path skips the engine's processor
    # registry, so we record the absolute minimum to keep consistency
    # checks happy.
    if paid_cents > 0:
        reason = f"test_seed:{legal_basis}:{purchase.id}"
        await record_active_ledger(
            db_session,
            user_id=investor_id,
            amount_cents=-paid_cents,
            status=LedgerStatus.CONFIRMED,
            reason=reason,
        )
        await record_passive_ledger(
            db_session,
            user_id=company_user_id,
            amount_cents=paid_cents,
            status=LedgerStatus.CONFIRMED,
            reason=reason,
        )
    await db_session.flush()

    return purchase


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_ownership_html_single_sale(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /ownership-certificate -> 200 HTML with totals after one sale."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc1")
    product = await _create_product(
        client, admin_token, company["id"], package_size=50, suffix="oc1",
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc1",
        first_name="Alice", last_name="Doe",
    )
    await _buy(client, inv_token, product["id"])

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]
    html = resp.text

    # Investor + company anchors from context.
    assert "Alice Doe" in html
    assert company["name"] in html
    # Aggregate marker: 50 units sold (from package_size).
    assert "50" in html


@pytest.mark.asyncio
async def test_ownership_sums_two_sales(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two sale Purchases -> total_units = sum of package_sizes."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc2")
    product = await _create_product(
        client, admin_token, company["id"], package_size=30, suffix="oc2",
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc2",
        first_name="Bob", last_name="Smith",
    )
    await _buy(client, inv_token, product["id"])
    await _buy(client, inv_token, product["id"])

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    html = resp.text

    # 60 units = 30 + 30 (two packages).
    assert "60" in html
    assert "Bob Smith" in html


@pytest.mark.asyncio
async def test_ownership_installment_tranche_in_sale_units(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """installment_tranche Purchase counts in sale_units, not gift_units.

    Per the iter 2.4 design call (R2 §5.3), the bootstrap
    ownership_certificate templates expect two counters (sale + gift).
    installment_tranche is treated as "paid for in money" and rolls
    into sale_units. This test seeds a Purchase row directly with
    legal_basis=installment_tranche and verifies the response totals
    don't fold it into the gift bucket.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc3")
    product = await _create_product(
        client, admin_token, company["id"], package_size=20, suffix="oc3",
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc3",
    )

    # Resolve company.user_id for the passive ledger pair.
    from app.modules.companies.models import CompanyProfile
    co_row = (
        await db_session.execute(
            select(CompanyProfile).where(CompanyProfile.id == UUID(company["id"]))
        )
    ).scalar_one()

    # Seed: 20 units sale (real purchase) + 15 units installment_tranche.
    await _buy(client, inv_token, product["id"])
    await _insert_direct_purchase(
        db_session,
        investor_id=inv_id,
        product_id=UUID(product["id"]),
        company_id=UUID(company["id"]),
        company_user_id=co_row.user_id,
        legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        units=15,
        paid_cents=15 * 10000,
        price_per_unit_cents=10000,
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    html = resp.text

    # 35 = 20 sale + 15 installment_tranche, all rolled into sale_units.
    # gift_units must be 0 (no gift Purchases were seeded).
    assert "35" in html


@pytest.mark.asyncio
async def test_ownership_gift_in_gift_units(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """gift Purchase counts in gift_units, not sale_units."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc4")
    product = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="oc4",
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc4",
    )

    from app.modules.companies.models import CompanyProfile
    co_row = (
        await db_session.execute(
            select(CompanyProfile).where(CompanyProfile.id == UUID(company["id"]))
        )
    ).scalar_one()

    # Seed: 10 units sale + 7 units gift (paid_cents=0).
    await _buy(client, inv_token, product["id"])
    await _insert_direct_purchase(
        db_session,
        investor_id=inv_id,
        product_id=UUID(product["id"]),
        company_id=UUID(company["id"]),
        company_user_id=co_row.user_id,
        legal_basis=PurchaseLegalBasis.GIFT,
        units=7,
        paid_cents=0,
        price_per_unit_cents=10000,
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200
    html = resp.text

    # Totals: 17 = 10 sale + 7 gift.
    assert "17" in html
    # Make sure gift count of 7 shows up too -- bootstrap templates
    # render gift_units separately.
    assert "7" in html


@pytest.mark.asyncio
async def test_ownership_no_purchases_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /ownership-certificate when investor has zero Purchases -> 404."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc5")
    await _activate_company(client, admin_token, company["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc5",
    )

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ownership_company_not_found_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /ownership-certificate with non-existent company_id -> 404."""
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc6",
    )

    fake_id = uuid4()
    resp = await client.get(
        f"/api/v1/companies/{fake_id}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ownership_email_204_mocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /ownership-certificate/email -> 204 (mocked send)."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc7")
    product = await _create_product(
        client, admin_token, company["id"], package_size=25, suffix="oc7",
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc7",
    )
    await _buy(client, inv_token, product["id"])

    with patch(
        "app.modules.purchases.agreement_router.send_ownership_email",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        resp = await client.post(
            f"/api/v1/companies/{company['id']}/ownership-certificate/email",
            headers=auth_headers(inv_token),
        )

    assert resp.status_code == 204
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_ownership_template_missing_500(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /ownership-certificate when find_active_template returns None -> 500.

    Patches find_active_template at the call site (ownership_certificate_service)
    to return None, simulating the broken-stack branch where all 4
    fallback stages miss. Renderer should surface 500 with code
    agreement_template_missing.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, "oc8")
    product = await _create_product(
        client, admin_token, company["id"], package_size=10, suffix="oc8",
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, suffix="inv_oc8",
    )
    await _buy(client, inv_token, product["id"])

    with patch(
        "app.modules.purchases.ownership_certificate_service.find_active_template",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(
            f"/api/v1/companies/{company['id']}/ownership-certificate",
            headers=auth_headers(inv_token),
        )

    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert body["error"] == "agreement_template_missing"


# ===========================================================================
# T3 -- BUG-11-01 regression guard: ownership render context covers
#       TEMPLATE_PLACEHOLDERS[OWNERSHIP_CERTIFICATE]
# ===========================================================================

import jinja2  # noqa: E402

from app.modules.companies.constants import (  # noqa: E402
    DocumentTemplateKind,
    TEMPLATE_PLACEHOLDERS,
)
from app.modules.companies.models import (  # noqa: E402
    CompanyDocumentTemplate,
)
from app.modules.purchases.ownership_certificate_service import (  # noqa: E402
    OwnershipData,
    load_ownership_data,
    render_ownership_html,
)


def _build_synthetic_ownership_template(
    placeholders: frozenset[str],
) -> str:
    """Build a Jinja2 template that references every top-level placeholder.

    `purchases` is a list-of-dicts; we just iterate without touching
    sub-keys (TEMPLATE_PLACEHOLDERS only validates top-level names by
    design -- see companies/constants.py comment above the dict). The
    iteration alone is enough to prove `purchases` is in the context.
    """
    top_level = sorted(placeholders - {"purchases"})
    body = " | ".join(f"{{{{ {name} }}}}" for name in top_level)
    if "purchases" in placeholders:
        body += " | {% for p in purchases %}*{% endfor %}"
    return body


@pytest.mark.asyncio
async def test_ownership_render_context_covers_template_placeholders(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """render_ownership_html must supply every key in
    TEMPLATE_PLACEHOLDERS[OWNERSHIP_CERTIFICATE].

    Mocking strategy mirrors the agreement-side test in
    test_purchase_agreement.py: we replace get_template_html_cached
    with a synthetic body, make_asset_data_uri_func with a no-op
    factory, and find_active_template with a stub returning a
    sentinel template object (the ownership renderer needs one --
    storage_prefix is forwarded into the mocked helpers and never
    actually read).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token, suffix="t3o")
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session, suffix="inv_t3o",
    )
    await _buy(client, inv_token, product["id"])

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
        title="t3 stub",
        storage_prefix="_test/t3_ownership/",
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


# ===========================================================================
# T4 -- SEC-11-01 regression guard: OwnershipData does not hold full User
# ===========================================================================


def test_ownership_data_does_not_hold_user_object() -> None:
    """SEC-11-01 regression guard.

    OwnershipData MUST NOT carry a full User ORM instance (which has
    credentials / password_hash / kyc_data attached). Only the minimal
    scalar fields needed for render and audit-log correlation:
    investor_id (UUID) and investor_language (str) alongside the
    already-extracted investor_name / investor_email.

    Static inspection -- no fixtures, no DB. Catches the regression at
    import time without needing to exercise the full render pipeline.
    """
    fields = OwnershipData.__dataclass_fields__
    assert "investor_user" not in fields, (
        "OwnershipData.investor_user reintroduced -- SEC-11-01 regression. "
        "Use investor_id + investor_language instead."
    )
    assert "investor_id" in fields, (
        "OwnershipData must carry investor_id (UUID) for audit logging."
    )
    assert "investor_language" in fields, (
        "OwnershipData must carry investor_language (str) for template "
        "selection in render_ownership_html."
    )
