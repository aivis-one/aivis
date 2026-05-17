# =============================================================================
# CBSHOME Backend -- Public Companies HTTP Tests (iter 2.5-finishing)
# =============================================================================
#
# HTTP-level coverage for app/modules/companies/public_router.py.
# Pre-iter-2.6 safety net before AttachmentsSection / PublicShell rewire.
#
# What's tested:
#   1.  list returns only ACTIVE companies (hidden + archived filtered out)
#   2.  detail 200 with full PublicCompanyStatsResponse on active company
#   3-5. detail 404 for hidden / archived / nonexistent
#   6.  stats.options_sold / pool_total_options / options_sold_percent
#       reflect real Purchase rows
#   7.  price_growth_90d_percent == 0 when CompanyPriceHistory is empty
#   8.  price_growth_90d_percent computed from a 91-day-old history row
#   9.  stretched-window fallback: growth computed from earliest row
#       when no row is older than 90 days (R1 §1.5)
#   10. shared rate-limit bucket: companies + products requests count
#       against one `public_companies:<ip>` budget. X-Real-IP isolates
#       the bucket per test.
#
# RATE-LIMIT BEHAVIOUR:
#   check_rate_limit raises RateLimitError (HTTP 429 with Retry-After
#   header). Updated in iter 2.5-finishing -- the helper previously
#   raised BadRequestError -> 400, which masked the rate-limit signal
#   and forced clients to parse the message body.
# =============================================================================

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyPriceHistory, CompanyProfile
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
# Local helpers -- mirror test_purchases.py / test_regression_guards.py shape.
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Create admin staff user and return their session token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _create_company(
    client: AsyncClient,
    admin_token: str,
    *,
    total_supply: int = 1_000_000,
    price_per_unit_cents: int = 10_000,
) -> dict:
    """POST /staff/companies + POST /staff/companies/{id}/pool (100% equity).

    Created in HIDDEN status. Caller activates via PATCH if needed.
    Pool is created so stats endpoint has a non-zero pool_total_options
    once the company is active.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"co_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"PubCo {uuid.uuid4().hex[:6]}",
            "description": "Public companies router test company",
            "price_per_unit_cents": price_per_unit_cents,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": total_supply,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    company = resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, pool_resp.text

    return company


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    """Transition company hidden -> active."""
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text


async def _set_company_status_direct(
    db_session: AsyncSession, company_id: str, status: str
) -> None:
    """ORM-level status flip, bypassing state-machine validation.

    Used to reach `archived` from `hidden` directly (which the service
    would also allow, but committing through HTTP requires going via
    PATCH and the company-update permission gate is already exercised
    by other tests).
    """
    profile = (
        await db_session.execute(
            select(CompanyProfile).where(CompanyProfile.id == UUID(company_id))
        )
    ).scalar_one()
    profile.status = status
    await db_session.commit()


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    package_size: int = 100,
) -> dict:
    """POST /staff/products with package_size."""
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": "Pub Test Pack",
            "package_size": package_size,
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
    assert resp.status_code == 200, resp.text


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    balance_cents: int = 10_000_000,
) -> tuple[str, UUID]:
    """Register investor, approve KYC, fund balance via ledger."""
    from app.modules.ledgers.models import LedgerStatus
    from app.modules.ledgers.service import record_active_ledger

    data = await register_user(client)
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    user = (
        await db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0xtest_pubco_{uuid.uuid4().hex[:8]}",
    )
    await db_session.commit()

    return token, user_id


def _unique_ip() -> str:
    """Generate a documentation-range IPv4 (192.0.2.0/24) for bucket isolation.

    Each test gets its own X-Real-IP so the shared `public_companies:`
    Redis bucket can't bleed between tests in one run.
    """
    return f"192.0.2.{uuid.uuid4().int % 200 + 50}"


# ---------------------------------------------------------------------------
# 1: list returns only ACTIVE companies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_returns_only_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Three companies created (1 active, 1 hidden, 1 archived).

    GET /api/v1/public/companies must surface only the active one.
    Hidden + archived are filtered by list_companies(active_only=True).
    """
    admin_token = await _admin_token(client, db_session)

    active_co = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, active_co["id"])

    hidden_co = await _create_company(client, admin_token)
    # Hidden by default -- no PATCH needed.

    archived_co = await _create_company(client, admin_token)
    await _set_company_status_direct(
        db_session, archived_co["id"], CompanyStatus.ARCHIVED.value
    )

    # Hit the list endpoint with a fresh IP so we don't burn an existing
    # bucket. Walk through pages if the dev DB already has many active
    # companies -- we only care that ours surface as expected.
    found_ids: set[str] = set()
    page = 1
    while True:
        resp = await client.get(
            f"/api/v1/public/companies?per_page=100&page={page}",
            headers={"X-Real-IP": _unique_ip()},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        found_ids.update(item["id"] for item in body["items"])
        if len(body["items"]) < 100 or page * 100 >= body["total"]:
            break
        page += 1

    assert active_co["id"] in found_ids
    assert hidden_co["id"] not in found_ids
    assert archived_co["id"] not in found_ids


# ---------------------------------------------------------------------------
# 2: detail 200 with full stats on active company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_active_returns_stats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/v1/public/companies/{id} on an active company returns
    PublicCompanyDetailResponse with `stats` populated. All four
    stats fields are required ints (R1 §1.6.2 -- stats is REQUIRED, not
    Optional).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["id"] == company["id"]
    assert "stats" in body and body["stats"] is not None
    stats = body["stats"]

    # All four are required ints per the schema.
    for field in (
        "pool_total_options",
        "options_sold",
        "options_sold_percent",
        "price_growth_90d_percent",
    ):
        assert field in stats, f"stats missing field {field}"
        assert isinstance(stats[field], int), (
            f"stats[{field}] is {type(stats[field]).__name__}, expected int"
        )

    # Pool was created at 100% equity on total_supply=1M, so total
    # options must match.
    assert stats["pool_total_options"] == 1_000_000


# ---------------------------------------------------------------------------
# 3: detail 404 for hidden company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_404_for_hidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hidden company -> 404. The router rejects non-ACTIVE status."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    # Stays hidden -- no activation.

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4: detail 404 for archived company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_404_for_archived(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Archived company -> 404."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _set_company_status_direct(
        db_session, company["id"], CompanyStatus.ARCHIVED.value
    )

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5: detail 404 for nonexistent UUID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_404_for_nonexistent(
    client: AsyncClient,
) -> None:
    """Random UUID -> 404. get_company_detail raises NotFoundError."""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/public/companies/{fake_id}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6: options_sold reflects real Purchase rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_stats_options_sold_reflects_purchases(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Create company with pool=400, package=100; investor buys one pack.

    Expect:
      pool_total_options   == 400
      options_sold         == 100  (get_pool_consumed: SUM(units) on
                                    active purchases incl. gifts)
      options_sold_percent == 25
    """
    admin_token = await _admin_token(client, db_session)

    # total_supply=400 so 100% equity gives a 400-option pool.
    company = await _create_company(
        client, admin_token, total_supply=400
    )
    await _activate_company(client, admin_token, company["id"])

    product = await _create_product(
        client, admin_token, company["id"], package_size=100
    )
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session, balance_cents=2_000_000
    )

    buy = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert buy.status_code == 201, buy.text

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    stats = resp.json()["stats"]

    assert stats["pool_total_options"] == 400
    assert stats["options_sold"] == 100
    assert stats["options_sold_percent"] == 25


# ---------------------------------------------------------------------------
# 7: price_growth_90d_percent == 0 without history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_price_growth_zero_without_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Fresh company has no CompanyPriceHistory rows -> growth = 0."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    await _activate_company(client, admin_token, company["id"])

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["stats"]["price_growth_90d_percent"] == 0


# ---------------------------------------------------------------------------
# 8: price_growth from a 91-day-old baseline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_price_growth_uses_90d_baseline(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Insert a CompanyPriceHistory row at 91 days old with price=10000.

    Then bump company.price_per_unit_cents to 12000. Service stage 1
    picks the row older than 90d, computes (12000 - 10000) / 10000 * 100
    = 20 (integer-rounded).
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, price_per_unit_cents=12_000
    )
    await _activate_company(client, admin_token, company["id"])

    # Insert old baseline directly via ORM. Service step 1 selects the
    # latest history row with changed_at < now-90d.
    old_row = CompanyPriceHistory(
        company_id=UUID(company["id"]),
        price_per_unit_cents=10_000,
        changed_at=datetime.now(UTC) - timedelta(days=91),
        changed_by=(
            await db_session.execute(
                select(User.id).where(User.role == "platform").limit(1)
            )
        ).scalar_one(),
    )
    db_session.add(old_row)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["stats"]["price_growth_90d_percent"] == 20


# ---------------------------------------------------------------------------
# 9: stretched-window fallback when no 90d-old row exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_detail_price_growth_stretched_window(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No row older than 90d, only a recent one -> stretched window:
    service falls back to the EARLIEST history row (R1 §1.5).

    Insert one history row at 10 days old (price=10000), set company
    price to 11000. Expected growth = 10%.
    """
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(
        client, admin_token, price_per_unit_cents=11_000
    )
    await _activate_company(client, admin_token, company["id"])

    recent_row = CompanyPriceHistory(
        company_id=UUID(company["id"]),
        price_per_unit_cents=10_000,
        changed_at=datetime.now(UTC) - timedelta(days=10),
        changed_by=(
            await db_session.execute(
                select(User.id).where(User.role == "platform").limit(1)
            )
        ).scalar_one(),
    )
    db_session.add(recent_row)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/public/companies/{company['id']}",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["stats"]["price_growth_90d_percent"] == 10


# ---------------------------------------------------------------------------
# 10: shared rate-limit bucket (companies + products)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_rate_limit_shared_bucket_with_products(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Companies and products public routers share `public_companies:<ip>`.

    Drop the cap to 2 via monkeypatch so the test is cheap. With a
    fresh IP:
      req 1 (companies list)  -> 200
      req 2 (products list)   -> 200
      req 3 (companies list)  -> 429 (limit exceeded)

    iter 2.5-finishing: rate-limit hits return HTTP 429 with the
    canonical `Retry-After` response header. Previously the helper
    raised BadRequestError -> 400; that masked the rate-limit signal
    and forced clients to parse the message body. The header value is
    a positive int (remaining seconds in the current window); we only
    assert it parses, not a specific value.
    """
    # Both routers reference PUBLIC_COMPANIES_RATE_LIMIT by name when
    # the request hits the helper, so monkeypatch the module-level
    # constant in each router module to a tight (max_requests, window).
    monkeypatch.setattr(
        "app.modules.companies.public_router.PUBLIC_COMPANIES_RATE_LIMIT",
        (2, 60),
    )
    monkeypatch.setattr(
        "app.modules.products.public_router.PUBLIC_COMPANIES_RATE_LIMIT",
        (2, 60),
    )

    ip = _unique_ip()
    headers = {"X-Real-IP": ip}

    # Belt-and-braces: drop any pre-existing bucket key for this IP.
    # The autouse clear_rate_limit fixture only wipes auth keys.
    from app.core.redis import get_redis

    redis = get_redis()
    await redis.delete(f"public_companies:{ip}")

    r1 = await client.get("/api/v1/public/companies", headers=headers)
    assert r1.status_code == 200, r1.text

    r2 = await client.get("/api/v1/public/products", headers=headers)
    assert r2.status_code == 200, r2.text

    # Third request from the same IP exhausts the shared bucket. It
    # doesn't matter whether it lands on companies or products -- the
    # Redis key prefix is identical.
    r3 = await client.get("/api/v1/public/companies", headers=headers)
    assert r3.status_code == 429, r3.text
    assert r3.json()["error"] == "rate_limit_exceeded"
    assert "Too many" in r3.json()["message"]
    retry_after = r3.headers.get("retry-after")
    assert retry_after is not None, "429 must include a Retry-After header"
    assert int(retry_after) > 0


# ---------------------------------------------------------------------------
# 11: ?search filter restricts the list to name-matched companies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_list_search_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """list_companies(search=X) does a case-insensitive substring match
    on CompanyProfile.name. Service escapes LIKE metacharacters, so a
    UUID-derived needle is unambiguous and the test does not depend on
    what else is sitting in the dev DB.
    """
    admin_token = await _admin_token(client, db_session)

    needle = uuid.uuid4().hex[:10]
    # Create one company whose name contains the needle; activate it.
    matching = await _create_company(client, admin_token)
    profile = (
        await db_session.execute(
            select(CompanyProfile).where(
                CompanyProfile.id == UUID(matching["id"])
            )
        )
    ).scalar_one()
    profile.name = f"Findme {needle} Corp"
    await db_session.commit()
    await _activate_company(client, admin_token, matching["id"])

    resp = await client.get(
        f"/api/v1/public/companies?search={needle}&per_page=100",
        headers={"X-Real-IP": _unique_ip()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    returned_ids = {item["id"] for item in body["items"]}
    assert matching["id"] in returned_ids
    # Body should be tight -- needle is UUID-derived, no other company
    # in the DB can share it.
    assert body["total"] == 1, (
        f"unexpected matches for needle {needle}: {body['total']}"
    )
