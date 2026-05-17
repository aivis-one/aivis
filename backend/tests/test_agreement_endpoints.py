# =============================================================================
# CBSHOME Backend -- Agreement Endpoints HTTP Tests (iter 2.5-finishing)
# =============================================================================
#
# HTTP-level coverage for app/modules/purchases/agreement_router.py::agreement_router
# (the per-Purchase pair, prefix /api/v1/purchases).
#
# What's tested:
#   1.  GET /agreement for owner -> 200 + HTML body
#       (NOTE: spec text said "PDF bytes", but the router returns
#       HTMLResponse. GET is HTML; POST /email generates the PDF.
#       Recorded as Surprise finding; tests check reality.)
#   2.  GET /agreement for non-owner -> 404
#       (load_agreement_data filters by investor_id in the WHERE clause,
#       so a foreign caller sees the same shape as a missing Purchase.
#       NotFoundError -> 404, not 403.)
#   3.  GET /agreement with purchase_agreement_template_id=NULL -> 500
#       with code "agreement_template_missing"
#       (Direct ORM UPDATE flips the column to NULL, simulating the
#       broken-infra case from R2 §5.3.)
#   4.  POST /agreement/email -> 204, send hook called once with the
#       correct investor email.
#   5.  Per-user rate limit on POST /email: after settings.auth_rate_limit_max_requests
#       consecutive POSTs, the next one is rejected.
#
# IMPORTANT EMAIL-MOCK STRATEGY:
#   The router imports `send_agreement_email` from agreement_service as
#   a bare name. We monkeypatch the BINDING IN THE ROUTER MODULE
#   (app.modules.purchases.agreement_router.send_agreement_email) so
#   the real implementation never runs. This is the same lesson TD-069
#   recorded for the certificate-flow tests: mock at the router level,
#   not inside core/email, so Mailgun/SMTP routing changes can't break
#   the test.
# =============================================================================

import uuid
from uuid import UUID

import pytest
from app.core.config import settings
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.purchases.models import Purchase
from app.modules.users.models import User
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)

# ---------------------------------------------------------------------------
# Local helpers (lightweight purchase pipeline -- one company, one product,
# one investor, one purchase).
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company_with_product(
    client: AsyncClient, admin_token: str
) -> tuple[dict, dict]:
    """Build a usable Company + Product pair (both active, pool sized)."""
    co_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"AgrCo {uuid.uuid4().hex[:6]}",
            "description": "Agreement endpoints test company",
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
            "name": "Agr Pack",
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
    email: str | None = None,
    language: str = "en",
) -> tuple[str, UUID, UUID]:
    """Register investor, fund, KYC-approve, buy one pack of product_id.

    Returns (session_token, investor_id, sale_purchase_id).
    """
    data = await register_user(client, email=email)
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
        reason=f"deposit:crypto:0xtest_agr_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    buy = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(token),
    )
    assert buy.status_code == 201, buy.text
    sale = next(p for p in buy.json() if p["legal_basis"] == "sale")
    return token, inv_id, UUID(sale["id"])


async def _purge_agreement_email_bucket(
    investor_id: UUID,
) -> None:
    """Drop the per-user agreement_email rate-limit bucket.

    The autouse clear_rate_limit conftest fixture only handles auth
    buckets; we own this one.
    """
    from app.core.redis import get_redis

    redis = get_redis()
    await redis.delete(f"agreement_email:{investor_id}")


# ---------------------------------------------------------------------------
# 1: GET /agreement for owner -> 200 + HTML
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_get_returns_html_for_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Owner GETs their own agreement -> 200, Content-Type: text/html.

    Reality check vs. spec: agreement_router returns HTMLResponse, not
    PDF. The PDF only materialises inside POST /email. Coordinator
    report flags the doc/code mismatch.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    inv_token, _, purchase_id = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )

    resp = await client.get(
        f"/api/v1/purchases/{purchase_id}/agreement",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    assert len(resp.content) > 0


# ---------------------------------------------------------------------------
# 2: GET /agreement for a different investor -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_get_404_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A second investor tries to read investor-A's agreement.

    load_agreement_data joins on `Purchase.investor_id == user_id` in
    the WHERE clause, so a foreign caller gets the same `row is None`
    branch as a missing Purchase. NotFoundError -> 404, not 403.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    # Investor A makes a purchase.
    _, _, purchase_id = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )

    # Investor B exists, has KYC, but never bought this product.
    data_b = await register_user(client)
    token_b = data_b["session_token"]
    user_b = (
        await db_session.execute(
            select(User).where(User.id == UUID(data_b["user"]["id"]))
        )
    ).scalar_one()
    user_b.kyc_status = "approved"
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/purchases/{purchase_id}/agreement",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3: GET /agreement with template_id NULL -> 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_get_500_when_template_id_null(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Force purchase_agreement_template_id NULL via direct ORM update.

    load_agreement_data uses LEFT OUTER JOIN -- on a Purchase row that
    exists but with template_id IS NULL, the template column comes
    back as None and the helper raises TemplateMissingError
    (status_code=500, code="agreement_template_missing"). Per R2 §5.3
    this is a broken-infra signal, not a 404.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    inv_token, _, purchase_id = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )

    # Direct ORM nuke of the snapshot column. The test server's DB is
    # disposable; we don't need to revert.
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


# ---------------------------------------------------------------------------
# 4: POST /agreement/email -> 204 + send wired correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_email_204_and_send_called(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST .../agreement/email returns 204 and calls send_agreement_email
    exactly once with the investor's email visible on the AgreementData.

    Mocks the binding inside agreement_router (NOT core/email) -- see
    TD-069: routing-layer mock is the right level so future Mailgun /
    SMTP changes don't silently invalidate the test.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    investor_email = f"inv_{uuid.uuid4().hex[:12]}@example.com"
    inv_token, inv_id, purchase_id = await _make_investor_with_purchase(
        client, db_session, product["id"], email=investor_email
    )
    await _purge_agreement_email_bucket(inv_id)

    captured: list[tuple[str | None, int]] = []

    async def _fake_send_agreement_email(data, pdf_bytes) -> bool:
        # AgreementData carries investor_email + the PDF bytes generated
        # by xhtml2pdf. We assert on the email; bytes-length is a
        # smoke check that PDF generation actually ran.
        captured.append((data.investor_email, len(pdf_bytes)))
        return True

    monkeypatch.setattr(
        "app.modules.purchases.agreement_router.send_agreement_email",
        _fake_send_agreement_email,
    )

    resp = await client.post(
        f"/api/v1/purchases/{purchase_id}/agreement/email",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 204, resp.text

    assert len(captured) == 1, (
        f"send_agreement_email called {len(captured)} times, expected 1"
    )
    captured_email, pdf_len = captured[0]
    assert captured_email == investor_email
    assert pdf_len > 0, "PDF generation produced empty bytes"


# ---------------------------------------------------------------------------
# 5: per-user rate limit on POST /email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_email_rate_limit_per_user(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check_rate_limit("agreement_email:<user_id>") with default settings:
    after `auth_rate_limit_max_requests` calls in the window, the
    next one trips.

    We pin the cap to 2 via settings monkeypatch and make POSTs return
    no-op so the test is fast. Reality vs. spec: the helper raises
    BadRequestError -> HTTP 400 (not 429). The spec text says 429;
    recorded as a Surprise finding, not patched here.
    """
    admin_token = await _admin_token(client, db_session)
    _, product = await _create_company_with_product(client, admin_token)

    inv_token, inv_id, purchase_id = await _make_investor_with_purchase(
        client, db_session, product["id"]
    )

    # Tight cap so we hit the limit in three calls.
    monkeypatch.setattr(settings, "auth_rate_limit_max_requests", 2)
    await _purge_agreement_email_bucket(inv_id)

    async def _noop_send(_data, _pdf) -> bool:
        return True

    monkeypatch.setattr(
        "app.modules.purchases.agreement_router.send_agreement_email",
        _noop_send,
    )

    url = f"/api/v1/purchases/{purchase_id}/agreement/email"

    r1 = await client.post(url, headers=auth_headers(inv_token))
    assert r1.status_code == 204, r1.text

    r2 = await client.post(url, headers=auth_headers(inv_token))
    assert r2.status_code == 204, r2.text

    r3 = await client.post(url, headers=auth_headers(inv_token))
    # BadRequestError -> HTTP 400. Spec said 429; the router does NOT
    # remap, so 400 is the production behaviour we're guarding.
    assert r3.status_code == 400, r3.text
    assert "Too many" in r3.json()["message"]
