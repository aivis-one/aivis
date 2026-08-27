# =============================================================================
# AIVIS.ONE Backend -- Purchase Tests (Sprint 6.1)
# =============================================================================
#
# Tests cover:
#   1:  PurchaseProcessor SUM=0 invariant (unit test)
#   2:  PurchaseProcessor company share calculation
#   3:  GiftProcessor "always" condition
#   4:  GiftProcessor "portfolio_size_gte" condition met
#   5:  GiftProcessor "portfolio_size_gte" condition not met
#   6:  GiftProcessor empty bonuses -> no transactions
#   7:  ProcessorRegistry runs both processors
#   8:  validate_purchase_config valid config
#   9:  validate_purchase_config invalid bonus percent sum > 100
#   10: validate_purchase_config unknown keys rejected
#   11: POST /products/{id}/purchase -> 201 (instant buy)
#   12: POST /products/{id}/purchase insufficient balance -> 400
#   13: POST /products/{id}/purchase product not active -> 400
#   14: POST /products/{id}/purchase non-investor -> 403
#   15: POST /products/{id}/purchase without KYC -> 400
#   16: POST /products/{id}/purchase with gift bonus -> 201 + 2 purchases
#   17: POST /products/{id}/purchase -> notification_request on the outbox
#       (TASK-24 batch 3, 2026-08-27)
#   18: Purchase with comms NOT configured -> no outbox row
#
# Email prefix: "s61_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from datetime import datetime, UTC
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_NOTIFICATION_REQUEST
from app.core.exceptions import BadRequestError
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.processors.base import PurchaseContext
from app.modules.processors.gift import GiftProcessor
from app.modules.processors.purchase import PurchaseProcessor
from app.modules.processors.registry import ProcessorRegistry
from app.modules.processors.validators import validate_purchase_config
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)
import uuid



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session
    )
    return token


async def _create_company(
    client: AsyncClient, admin_token: str, suffix: str = "co1"
) -> dict:
    """Helper: create a company via staff endpoint.

    Sprint 4.3: also creates the active OptionPool with equity_percent=100,
    so subsequent _create_product() calls can attach to it.
    """
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"company_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": f"Test Company {suffix}",
            "description": "A test company",
            "price_per_unit_cents": 10000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            # Sprint 4.3:
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create company failed: {resp.text}"
    company = resp.json()

    # Sprint 4.3: products require an active pool.
    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, f"Create pool failed: {pool_resp.text}"

    return company


async def _create_product(
    client: AsyncClient,
    admin_token: str,
    company_id: str,
    *,
    units: int = 100,
    purchase_config: dict | None = None,
) -> dict:
    """Helper: create a product via staff endpoint.

    Sprint 4.3: the `units` kwarg name stays for backwards-compat with
    test call sites; the value is forwarded as `package_size` in the
    request body (the column was renamed).
    """
    body: dict = {
        "company_id": company_id,
        "name": "Test Package",
        "package_size": units,  # Sprint 4.3: column renamed
    }
    if purchase_config is not None:
        body["purchase_config"] = purchase_config

    resp = await client.post(
        "/api/v1/staff/products",
        json=body,
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Create product failed: {resp.text}"
    return resp.json()


async def _activate_product(
    client: AsyncClient, admin_token: str, product_id: str
) -> None:
    """Helper: set product status to active."""
    resp = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _activate_company(
    client: AsyncClient, admin_token: str, company_id: str
) -> None:
    """Helper: set company status to active."""
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200


async def _create_investor_with_balance(
    client: AsyncClient,
    db_session: AsyncSession,
    balance_cents: int = 2_000_000,
) -> tuple[str, UUID]:
    """Helper: create investor, deposit funds, return (token, user_id)."""
    data = await register_user(
        client
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])

    # Approve KYC (TD-038: required for purchase).
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.kyc_status = "approved"
    await db_session.flush()

    # Deposit via direct ledger write (simulating confirmed deposit).
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=balance_cents,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_s61",
    )
    await db_session.commit()

    return token, user_id


def _make_context(
    *,
    amount_cents: int = 1_000_000,
    units: int = 100,
    company_pct: float = 0.65,
    agent_levels: list[float] | None = None,
    bonuses: list[dict] | None = None,
) -> PurchaseContext:
    """Helper: build a PurchaseContext for unit tests."""
    from uuid import uuid4

    return PurchaseContext(
        investor_id=uuid4(),
        product_id=uuid4(),
        company_id=uuid4(),
        company_user_id=uuid4(),
        platform_user_id=uuid4(),
        amount_cents=amount_cents,
        units=units,
        price_per_unit_cents=amount_cents // units,
        distribution_config={
            "company_pct": company_pct,
            "agent_levels": agent_levels or [0.10, 0.03, 0.01],
        },
        purchase_config_bonuses=bonuses or [],
        origin_payment_id=None,
        frozen_until=None,
        agent_chain=[],
        triggered_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Unit tests: PurchaseProcessor
# ---------------------------------------------------------------------------


def test_purchase_processor_sum_zero() -> None:
    """PurchaseProcessor: all entries sum to 0."""
    ctx = _make_context()
    processor = PurchaseProcessor()
    transactions = processor.process(ctx)

    assert len(transactions) == 1
    txn = transactions[0]
    assert txn.legal_basis == "sale"
    assert sum(e.amount_cents for e in txn.entries) == 0


def test_purchase_processor_company_share() -> None:
    """PurchaseProcessor: company gets company_pct share."""
    ctx = _make_context(amount_cents=100_000, company_pct=0.75)
    processor = PurchaseProcessor()
    transactions = processor.process(ctx)

    txn = transactions[0]
    # Find company credit entry.
    company_entries = [
        e for e in txn.entries
        if e.user_id == ctx.company_user_id and e.amount_cents > 0
    ]
    assert len(company_entries) == 1
    assert company_entries[0].amount_cents == 75_000  # 75% of 100_000


# ---------------------------------------------------------------------------
# Unit tests: GiftProcessor
# ---------------------------------------------------------------------------


def test_gift_processor_always_condition() -> None:
    """GiftProcessor: 'always' condition triggers bonus."""
    ctx = _make_context(
        units=100,
        bonuses=[{
            "condition": "always",
            "bonus_units_percent": 10,
            "funded_by": "company",
        }],
    )
    processor = GiftProcessor(investor_portfolio_cents=0)
    transactions = processor.process(ctx)

    assert len(transactions) == 1
    txn = transactions[0]
    assert txn.legal_basis == "gift"
    assert txn.units == 10  # 10% of 100
    assert sum(e.amount_cents for e in txn.entries) == 0


def test_gift_processor_portfolio_gte_met() -> None:
    """GiftProcessor: portfolio_size_gte condition met -> bonus triggered."""
    ctx = _make_context(
        amount_cents=100_000,
        units=100,
        bonuses=[{
            "condition": "portfolio_size_gte",
            "threshold_cents": 50_000,
            "bonus_units_percent": 5,
            "funded_by": "platform",
        }],
    )
    # Portfolio 0 + current purchase 100_000 >= threshold 50_000.
    processor = GiftProcessor(investor_portfolio_cents=0)
    transactions = processor.process(ctx)

    assert len(transactions) == 1
    assert transactions[0].units == 5  # 5% of 100


def test_gift_processor_portfolio_gte_not_met() -> None:
    """GiftProcessor: portfolio_size_gte condition NOT met -> no bonus."""
    ctx = _make_context(
        amount_cents=10_000,
        units=100,
        bonuses=[{
            "condition": "portfolio_size_gte",
            "threshold_cents": 500_000,
            "bonus_units_percent": 5,
            "funded_by": "platform",
        }],
    )
    processor = GiftProcessor(investor_portfolio_cents=0)
    transactions = processor.process(ctx)

    assert len(transactions) == 0


def test_gift_processor_empty_bonuses() -> None:
    """GiftProcessor: no bonuses configured -> empty result."""
    ctx = _make_context(bonuses=[])
    processor = GiftProcessor(investor_portfolio_cents=0)
    transactions = processor.process(ctx)

    assert len(transactions) == 0


# ---------------------------------------------------------------------------
# Unit tests: ProcessorRegistry
# ---------------------------------------------------------------------------


def test_registry_runs_both_processors() -> None:
    """ProcessorRegistry: runs purchase + gift processors."""
    ctx = _make_context(
        units=200,
        bonuses=[{
            "condition": "always",
            "bonus_units_percent": 10,
            "funded_by": "company",
        }],
    )
    registry = ProcessorRegistry(investor_portfolio_cents=0)
    transactions = registry.run_all(ctx)

    # 1 sale + 1 gift.
    assert len(transactions) == 2
    assert transactions[0].legal_basis == "sale"
    assert transactions[1].legal_basis == "gift"
    assert transactions[1].units == 20  # 10% of 200

    # All pass SUM=0.
    for txn in transactions:
        assert sum(e.amount_cents for e in txn.entries) == 0


# ---------------------------------------------------------------------------
# Unit tests: validate_purchase_config
# ---------------------------------------------------------------------------


def test_validate_purchase_config_valid() -> None:
    """Valid purchase_config passes validation."""
    validate_purchase_config({
        "distribution": {
            "company_pct": 0.70,
            "agent_levels": [0.05],
        },
        "bonuses": [
            {
                "condition": "always",
                "bonus_units_percent": 10,
                "funded_by": "company",
            },
        ],
    })


def test_validate_purchase_config_bonus_sum_exceeds_100() -> None:
    """Bonus percentages summing > 100 -> BadRequestError."""
    with pytest.raises(BadRequestError, match="exceeds 100"):
        validate_purchase_config({
            "bonuses": [
                {
                    "condition": "always",
                    "bonus_units_percent": 60,
                    "funded_by": "company",
                },
                {
                    "condition": "always",
                    "bonus_units_percent": 50,
                    "funded_by": "platform",
                },
            ],
        })


def test_validate_purchase_config_unknown_keys() -> None:
    """Unknown top-level keys -> BadRequestError."""
    with pytest.raises(BadRequestError, match="unknown keys"):
        validate_purchase_config({"bonuses": [], "foo": "bar"})


# ---------------------------------------------------------------------------
# Integration tests: POST /products/{id}/purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_instant_buy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor purchases product -> 201, Purchase created."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session
    )

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"

    data = resp.json()
    assert len(data) >= 1
    assert data[0]["legal_basis"] == "sale"
    # Sprint 4.3: data[0] is a Purchase response (Purchase.units stays);
    # product["package_size"] was Product.units before the rename.
    assert data[0]["units"] == product["package_size"]
    assert data[0]["paid_cents"] == product["package_size"] * product["price_per_unit_cents"]


@pytest.mark.asyncio
async def test_purchase_insufficient_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase with insufficient balance -> 400."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # Investor with only 100 cents (product costs 100 * 10000 = 1_000_000).
    inv_token, _ = await _create_investor_with_balance(
        client, db_session, balance_cents=100
    )

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 400
    assert "Insufficient balance" in resp.json()["message"]


@pytest.mark.asyncio
async def test_purchase_product_not_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase of non-active product -> 400."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    # Company active, product stays hidden (not activated).
    await _activate_company(client, admin_token, company["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session
    )

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 400
    assert "not available" in resp.json()["message"]


@pytest.mark.asyncio
async def test_purchase_non_investor_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Non-investor (staff) cannot purchase -> 403."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # Admin is staff, not investor.
    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_purchase_no_kyc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase without KYC approval -> 400."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    # Investor WITHOUT kyc_status=approved (skip helper, do manually).
    data = await register_user(
        client
    )
    token = data["session_token"]
    user_id = UUID(data["user"]["id"])
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=2_000_000,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xtest_nokyc",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "KYC" in resp.json()["message"]


@pytest.mark.asyncio
async def test_purchase_with_gift_bonus(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase with 'always' bonus -> 201, sale + gift purchases."""
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(
        client,
        admin_token,
        company["id"],
        units=100,
        purchase_config={
            "bonuses": [
                {
                    "condition": "always",
                    "bonus_units_percent": 10,
                    "funded_by": "company",
                },
            ],
        },
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session
    )

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"

    data = resp.json()
    assert len(data) == 2

    sale = next(p for p in data if p["legal_basis"] == "sale")
    gift = next(p for p in data if p["legal_basis"] == "gift")

    assert sale["units"] == 100
    assert sale["paid_cents"] == 100 * 10000
    assert gift["units"] == 10  # 10% of 100
    assert gift["paid_cents"] == 0


# ---------------------------------------------------------------------------
# 17-19. Notification emission (TASK-24 batch 3)
# ---------------------------------------------------------------------------


async def _notification_events(session: AsyncSession) -> list[OutboxEvent]:
    """Every notification_request event on the outbox, oldest first."""
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.event_type == EVENT_NOTIFICATION_REQUEST)
        .order_by(OutboxEvent.id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_purchase_emits_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Instant purchase, with comms configured, puts purchase.completed
    on the outbox -- one row, about the sale purchase (not a gift row
    even when the config would create one; covered by the gift-bonus
    fixture above's shape, single-purchase here keeps this test focused
    on the notification, not the gift math)."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session
    )
    before = len(await _notification_events(db_session))

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"
    sale_purchase_id = resp.json()[0]["id"]

    events = await _notification_events(db_session)
    assert len(events) == before + 1
    payload = events[-1].payload
    assert payload["type"] == "purchase.completed"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == str(inv_id)
    assert payload["idempotency_key"] == f"purchase-completed:{sale_purchase_id}"
    assert product["name"] in payload["body"]


@pytest.mark.asyncio
async def test_purchase_without_comms_emits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comms address -> no outbox row, same gate as every other
    emitter in this tree."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(client, admin_token, company["id"])
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, _ = await _create_investor_with_balance(
        client, db_session
    )
    before = len(await _notification_events(db_session))

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"

    assert len(await _notification_events(db_session)) == before


@pytest.mark.asyncio
async def test_purchase_with_gift_emits_both_notifications(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A purchase with a bonus config -> purchase.completed AND
    purchase.gift_received, each keyed to its own Purchase row."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    admin_token = await _admin_token(client, db_session)
    company = await _create_company(client, admin_token)
    product = await _create_product(
        client,
        admin_token,
        company["id"],
        units=100,
        purchase_config={
            "bonuses": [
                {
                    "condition": "always",
                    "bonus_units_percent": 10,
                    "funded_by": "company",
                },
            ],
        },
    )
    await _activate_company(client, admin_token, company["id"])
    await _activate_product(client, admin_token, product["id"])

    inv_token, inv_id = await _create_investor_with_balance(
        client, db_session
    )
    before = len(await _notification_events(db_session))

    resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201, f"Purchase failed: {resp.text}"
    data = resp.json()
    sale_id = next(p for p in data if p["legal_basis"] == "sale")["id"]
    gift_id = next(p for p in data if p["legal_basis"] == "gift")["id"]

    events = await _notification_events(db_session)
    assert len(events) == before + 2

    completed = next(e for e in events if e.payload["type"] == "purchase.completed")
    gift_event = next(e for e in events if e.payload["type"] == "purchase.gift_received")

    assert completed.payload["idempotency_key"] == f"purchase-completed:{sale_id}"
    assert gift_event.payload["idempotency_key"] == f"purchase-gift:{gift_id}"
    assert gift_event.payload["target_value"] == str(inv_id)
    assert "10" in gift_event.payload["body"]  # 10 bonus units (10% of 100)
