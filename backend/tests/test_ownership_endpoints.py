# =============================================================================
# AIVIS.ONE Backend -- Ownership Endpoints HTTP Tests (iter 2.5-finishing)
# =============================================================================
#
# HTTP-level coverage for app/modules/purchases/agreement_router.py::ownership_router
# (the per investor-company pair, prefix /api/v1/companies).
#
# Coverage:
#   1.  GET .../ownership-certificate -> 200, text/html
#   2.  GET .../ownership-certificate when investor has no purchases
#       in this company -> 404
#   3.  Bucket aggregate (R2 §5.3): sale + installment_tranche merge
#       into sale_units; gift stays separate. Asserted via direct
#       load_ownership_data() call -- complements the HTTP smoke
#       because the rendered HTML hides exact integers behind locale
#       formatting and risks brittle assertions.
#   4.  4-stage template fallback smoke on the OWNERSHIP path:
#       investor.language='ru', no per-company OWNERSHIP_CERTIFICATE
#       template -> platform-en row at L4 wins, GET renders 200.
#       (Sibling of test_regression_guards.py L4, which guards the
#       agreement side. The fallback machinery is shared, but the
#       ownership renderer resolves templates LIVE every call --
#       this asserts that path actually runs.)
#   5.  POST .../ownership-certificate/email -> 204, send_ownership_email
#       called once with the investor email visible.
#   6.  Per-user rate limit on POST /email (Redis key
#       `ownership_email:<user_id>`).
# =============================================================================

import uuid
from uuid import UUID

import pytest
from app.core.config import settings
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.purchases.ownership_certificate_service import (
    load_ownership_data,
)
from app.modules.users.models import User
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)

# ---------------------------------------------------------------------------
# Local helpers.
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company_with_product(
    client: AsyncClient, admin_token: str
) -> tuple[dict, dict]:
    """Same pattern as test_agreement_endpoints._create_company_with_product."""
    co_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"OwnCo {uuid.uuid4().hex[:6]}",
            "description": "Ownership endpoints test company",
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
            "name": "Own Pack",
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


async def _make_investor_with_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
    product_id: str,
    *,
    language: str = "en",
) -> tuple[str, UUID]:
    """Register + KYC + fund + buy one pack. Returns (token, investor_id)."""
    data = await register_user(client)
    token = data["session_token"]
    inv_id = UUID(data["user"]["id"])

    user = (
        await db_session.execute(select(User).where(User.id == inv_id))
    ).scalar_one()
    user.kyc_status = "approved"
    user.language = language
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=inv_id,
        amount_cents=2_000_000,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_own_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    buy = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(token),
    )
    assert buy.status_code == 201, buy.text
    return token, inv_id


async def _make_kyc_investor_no_purchases(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    language: str = "en",
) -> tuple[str, UUID]:
    """Register + KYC + fund (NO purchase). Returns (token, investor_id)."""
    data = await register_user(client)
    token = data["session_token"]
    inv_id = UUID(data["user"]["id"])

    user = (
        await db_session.execute(select(User).where(User.id == inv_id))
    ).scalar_one()
    user.kyc_status = "approved"
    user.language = language
    await db_session.commit()

    return token, inv_id


async def _purge_ownership_email_bucket(investor_id: UUID) -> None:
    """Drop the per-user ownership_email rate-limit Redis bucket."""
    from app.core.redis import get_redis

    redis = get_redis()
    await redis.delete(f"ownership_email:{investor_id}")


# ---------------------------------------------------------------------------
# 1: GET ownership-certificate -> 200, text/html
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_get_returns_html(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor with one purchase in company X -> GET .../ownership-certificate
    returns 200 with Content-Type: text/html.

    Same shape-reality note as test_agreement: the router emits
    HTMLResponse, not PDF -- PDF generation only happens inside POST
    /email.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)

    inv_token, _ = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    assert len(resp.content) > 0


# ---------------------------------------------------------------------------
# 2: GET ownership-certificate when investor has no purchases here -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_get_404_when_no_purchases(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """KYC'd investor that never bought from this company -> 404.

    load_ownership_data scopes by (current_user, company_id) and raises
    NotFoundError when the resulting Purchase set is empty.
    """
    admin_token = await _admin_token(client, db_session)
    company, _product = await _create_company_with_product(client, admin_token)

    inv_token, _ = await _make_kyc_investor_no_purchases(client, db_session)

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3: bucket aggregate -- sale + installment_tranche vs gift
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_data_buckets_sale_tranche_and_gift(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R2 §5.3 bucket aggregation rules on load_ownership_data:

      sale_units  = SUM(units) WHERE legal_basis IN ('sale',
                                                     'installment_tranche')
      gift_units  = SUM(units) WHERE legal_basis = 'gift'
      total_units = sale_units + gift_units

    Setup (ORM-inserted to bypass the engine -- we want to control
    each row's legal_basis precisely):
      Purchase 1: sale,                10 units
      Purchase 2: installment_tranche,  5 units
      Purchase 3: gift,                 2 units

    Expected:
      sale_units  == 15
      gift_units  ==  2
      total_units == 17

    Why direct service call instead of HTTP-only: the rendered HTML's
    integers are wrapped in locale formatting, so asserting on response
    text is brittle. The bucketing lives in load_ownership_data, not
    in the renderer; calling the loader directly is the cleanest way
    to lock the aggregate.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)

    # KYC'd investor; no real purchase needed -- we insert rows directly.
    inv_token, inv_id = await _make_kyc_investor_no_purchases(
        client, db_session
    )

    # Three Purchase rows with controlled legal_basis values.
    rows = [
        Purchase(
            investor_id=inv_id,
            product_id=UUID(product["id"]),
            company_id=UUID(company["id"]),
            legal_basis=PurchaseLegalBasis.SALE.value,
            units=10,
            paid_cents=100_000,
            price_per_unit_cents=10_000,
            status=PurchaseStatus.ACTIVE.value,
        ),
        Purchase(
            investor_id=inv_id,
            product_id=UUID(product["id"]),
            company_id=UUID(company["id"]),
            legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE.value,
            units=5,
            paid_cents=50_000,
            price_per_unit_cents=10_000,
            status=PurchaseStatus.ACTIVE.value,
        ),
        Purchase(
            investor_id=inv_id,
            product_id=UUID(product["id"]),
            company_id=UUID(company["id"]),
            legal_basis=PurchaseLegalBasis.GIFT.value,
            units=2,
            paid_cents=0,
            price_per_unit_cents=10_000,
            status=PurchaseStatus.ACTIVE.value,
        ),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()

    data = await load_ownership_data(
        company_id=UUID(company["id"]),
        user_id=inv_id,
        session=db_session,
    )

    assert data.sale_units == 15, (
        f"sale_units bucket wrong: {data.sale_units} "
        "(expected 15 = 10 sale + 5 tranche)"
    )
    assert data.gift_units == 2, (
        f"gift_units bucket wrong: {data.gift_units} (expected 2)"
    )
    assert data.total_units == 17, (
        f"total_units wrong: {data.total_units} (expected sale+gift = 17)"
    )

    # Smoke check that the HTTP path still renders cleanly on the same
    # data set -- ensures router-side wiring is not broken even though
    # we won't assert on the HTML.
    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 4: 4-stage template fallback smoke -- platform-en wins for ru investor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_renders_via_platform_default_for_ru_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ownership endpoint uses find_active_template() live every render
    (no per-Purchase snapshot exists on the ownership side -- the
    aggregate is a live concept).

    Setup:
      - investor.language = 'ru'
      - company has NO custom OWNERSHIP_CERTIFICATE templates
      - platform seed installs OWNERSHIP_CERTIFICATE @ en (L4)

    Expected: GET renders 200 -- the L4 stage of find_active_template
    fires because L1/L2/L3 all miss (no company override, no platform
    'ru' for ownership_certificate among the seeded 16 rows). If the
    seed actually installed an ru row at L3, the test still passes;
    the assertion is just "render works at all", which is the smoke
    we want.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)

    inv_token, _ = await _make_investor_with_purchase(
        client, db_session, product["id"], language="ru"
    )

    resp = await client.get(
        f"/api/v1/companies/{company['id']}/ownership-certificate",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")


# ---------------------------------------------------------------------------
# 5: POST .../ownership-certificate/email -> 204 + send wired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_email_204_and_send_called(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST returns 204 and the router-level send_ownership_email is
    invoked exactly once with the investor's email and a non-empty
    PDF payload.

    Same mock-at-router pattern as the agreement-side test (TD-069).
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)

    inv_token, inv_id = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )
    await _purge_ownership_email_bucket(inv_id)

    # Read the investor's email back from the DB so the assertion is
    # robust against UUID-randomised emails from register_user.
    investor_email = (
        await db_session.execute(
            select(
                User.credentials["email"]["email"].as_string()
            ).where(User.id == inv_id)
        )
    ).scalar_one()

    captured: list[tuple[str | None, int]] = []

    async def _fake_send_ownership_email(data, pdf_bytes) -> bool:
        captured.append((data.investor_email, len(pdf_bytes)))
        return True

    monkeypatch.setattr(
        "app.modules.purchases.agreement_router.send_ownership_email",
        _fake_send_ownership_email,
    )

    resp = await client.post(
        f"/api/v1/companies/{company['id']}/ownership-certificate/email",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 204, resp.text

    assert len(captured) == 1, (
        f"send_ownership_email called {len(captured)} times, expected 1"
    )
    captured_email, pdf_len = captured[0]
    assert captured_email == investor_email
    assert pdf_len > 0, "PDF generation produced empty bytes"


# ---------------------------------------------------------------------------
# 6: per-user rate limit on POST /email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_email_rate_limit_per_user(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check_rate_limit("ownership_email:<user_id>") with default settings:
    after `auth_rate_limit_max_requests` POSTs, the next one trips.

    Pin to 2 via settings monkeypatch for speed.

    iter 2.5-finishing: rate-limit hits return HTTP 429 with the
    canonical `Retry-After` response header. Mirrors the
    agreement-side test exactly so the same contract is asserted on
    both rate-limit endpoints.
    """
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)

    inv_token, inv_id = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )

    monkeypatch.setattr(settings, "auth_rate_limit_max_requests", 2)
    await _purge_ownership_email_bucket(inv_id)

    async def _noop_send(_data, _pdf) -> bool:
        return True

    monkeypatch.setattr(
        "app.modules.purchases.agreement_router.send_ownership_email",
        _noop_send,
    )

    url = f"/api/v1/companies/{company['id']}/ownership-certificate/email"

    r1 = await client.post(url, headers=auth_headers(inv_token))
    assert r1.status_code == 204, r1.text

    r2 = await client.post(url, headers=auth_headers(inv_token))
    assert r2.status_code == 204, r2.text

    r3 = await client.post(url, headers=auth_headers(inv_token))
    assert r3.status_code == 429, r3.text
    assert r3.json()["error"] == "rate_limit_exceeded"
    assert "Too many" in r3.json()["message"]
    retry_after = r3.headers.get("retry-after")
    assert retry_after is not None, "429 must include a Retry-After header"
    assert int(retry_after) > 0
