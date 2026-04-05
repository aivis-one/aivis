# =============================================================================
# CBSHOME Backend -- Ledger Service Tests (Sprint 5.1)
# =============================================================================
#
# Tests cover:
#   1:  record_active_ledger frozen -> entry created with correct fields
#   2:  record_active_ledger confirmed -> entry created, no frozen_until
#   3:  record_passive_ledger frozen -> entry created with correct fields
#   4:  record_passive_ledger confirmed -> entry created, no frozen_until
#   5:  record_active_ledger negative amount (debit) -> works
#   6:  record_active_ledger with origin_payment_id -> stored
#   7:  get_active_balance -> frozen and confirmed split correctly
#   8:  get_passive_balance -> frozen and confirmed split correctly
#   9:  get_active_balance empty -> {frozen: 0, confirmed: 0}
#   10: get_active_balance excludes reversed entries
#   11: get_passive_balance excludes reversed entries
#   12: validate_route active->passive -> AMLViolationError
#   13: validate_route active->active -> ok
#   14: validate_route passive->active -> ok
#   15: validate_route passive->passive -> ok
#
# Email prefix: "s51_" -- unique to this test file, cleaned up in fixture.
#
# NOTE: These tests call service functions directly with db_session,
#       not through HTTP endpoints (ledger service is internal).
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AMLViolationError
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.ledgers.service import (
    get_active_balance,
    get_passive_balance,
    record_active_ledger,
    record_passive_ledger,
)
from app.modules.ledgers.validators import validate_route
from tests.helpers import auth_headers, cleanup_test_users, register_user

EMAIL_PREFIX = "s51_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _create_user(client: AsyncClient, suffix: str = "u1") -> UUID:
    """Helper: register a user and return their UUID."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}{suffix}@example.com")
    return UUID(data["user"]["id"])


# ---------------------------------------------------------------------------
# record_active_ledger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_active_ledger_frozen(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record frozen active ledger entry -> correct fields stored."""
    user_id = await _create_user(client, "al_frozen")
    frozen_until = datetime.now(UTC) + timedelta(hours=1)

    entry = await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=10000,
        status=LedgerStatus.FROZEN,
        reason="deposit:crypto:0xabc123",
        frozen_until=frozen_until,
    )
    await db_session.commit()

    assert isinstance(entry, ActiveLedger)
    assert entry.user_id == user_id
    assert entry.amount_cents == 10000
    assert entry.status == LedgerStatus.FROZEN
    assert entry.reason == "deposit:crypto:0xabc123"
    assert entry.frozen_until is not None
    assert entry.origin_payment_id is None
    assert entry.id is not None
    assert entry.created_at is not None


@pytest.mark.asyncio
async def test_record_active_ledger_confirmed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record confirmed active ledger entry -> no frozen_until needed."""
    user_id = await _create_user(client, "al_conf")

    entry = await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=50000,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xdef456",
    )
    await db_session.commit()

    assert entry.status == LedgerStatus.CONFIRMED
    assert entry.frozen_until is None
    assert entry.amount_cents == 50000


# ---------------------------------------------------------------------------
# record_passive_ledger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_passive_ledger_frozen(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record frozen passive ledger entry -> correct fields stored."""
    user_id = await _create_user(client, "pl_frozen")
    frozen_until = datetime.now(UTC) + timedelta(hours=24)

    entry = await record_passive_ledger(
        db_session,
        user_id=user_id,
        amount_cents=5000,
        status=LedgerStatus.FROZEN,
        reason="saga:company_revenue:test-purchase-id",
        frozen_until=frozen_until,
    )
    await db_session.commit()

    assert isinstance(entry, PassiveLedger)
    assert entry.user_id == user_id
    assert entry.amount_cents == 5000
    assert entry.status == LedgerStatus.FROZEN
    assert entry.frozen_until is not None


@pytest.mark.asyncio
async def test_record_passive_ledger_confirmed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record confirmed passive ledger entry -> no frozen_until."""
    user_id = await _create_user(client, "pl_conf")

    entry = await record_passive_ledger(
        db_session,
        user_id=user_id,
        amount_cents=3000,
        status=LedgerStatus.CONFIRMED,
        reason="saga:platform_fee:test-purchase-id",
    )
    await db_session.commit()

    assert entry.status == LedgerStatus.CONFIRMED
    assert entry.frozen_until is None


# ---------------------------------------------------------------------------
# Debit (negative amount) and origin_payment_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_active_ledger_debit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record negative amount_cents (debit) -> works correctly."""
    user_id = await _create_user(client, "al_debit")

    entry = await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=-25000,
        status=LedgerStatus.CONFIRMED,
        reason="purchase:test-purchase-id",
    )
    await db_session.commit()

    assert entry.amount_cents == -25000


@pytest.mark.asyncio
async def test_record_active_ledger_with_origin_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record entry with origin_payment_id -> stored correctly."""
    user_id = await _create_user(client, "al_origin")
    from uuid import uuid4
    payment_id = uuid4()

    entry = await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=10000,
        status=LedgerStatus.FROZEN,
        reason="deposit:crypto:0xorigin",
        origin_payment_id=payment_id,
    )
    await db_session.commit()

    assert entry.origin_payment_id == payment_id


# ---------------------------------------------------------------------------
# get_active_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_balance_split(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get active balance -> frozen and confirmed calculated separately."""
    user_id = await _create_user(client, "bal_split")

    # Two frozen entries.
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=10000,
        status=LedgerStatus.FROZEN,
        reason="deposit:crypto:0x001",
    )
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=20000,
        status=LedgerStatus.FROZEN,
        reason="deposit:crypto:0x002",
    )

    # One confirmed entry.
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=50000,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0x003",
    )

    # One confirmed debit.
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=-15000,
        status=LedgerStatus.CONFIRMED,
        reason="purchase:test-purchase-1",
    )

    await db_session.commit()

    balance = await get_active_balance(db_session, user_id)

    assert balance["frozen"] == 30000       # 10000 + 20000
    assert balance["confirmed"] == 35000    # 50000 - 15000


@pytest.mark.asyncio
async def test_get_active_balance_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get active balance for user with no entries -> zeros."""
    user_id = await _create_user(client, "bal_empty")

    balance = await get_active_balance(db_session, user_id)

    assert balance["frozen"] == 0
    assert balance["confirmed"] == 0


@pytest.mark.asyncio
async def test_get_active_balance_excludes_reversed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reversed entries are excluded from balance calculation."""
    user_id = await _create_user(client, "bal_rev_a")

    # Confirmed entry.
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=10000,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:crypto:0xrev1",
    )

    # Reversed entry (should NOT count).
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=50000,
        status=LedgerStatus.REVERSED,
        reason="deposit:crypto:0xrev2",
    )

    await db_session.commit()

    balance = await get_active_balance(db_session, user_id)

    assert balance["confirmed"] == 10000
    assert balance["frozen"] == 0


# ---------------------------------------------------------------------------
# get_passive_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_passive_balance_split(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get passive balance -> frozen and confirmed calculated separately."""
    user_id = await _create_user(client, "pbal_split")

    await record_passive_ledger(
        db_session,
        user_id=user_id,
        amount_cents=8000,
        status=LedgerStatus.FROZEN,
        reason="saga:company_revenue:test-1",
    )

    await record_passive_ledger(
        db_session,
        user_id=user_id,
        amount_cents=12000,
        status=LedgerStatus.CONFIRMED,
        reason="saga:company_revenue:test-2",
    )

    await db_session.commit()

    balance = await get_passive_balance(db_session, user_id)

    assert balance["frozen"] == 8000
    assert balance["confirmed"] == 12000


@pytest.mark.asyncio
async def test_get_passive_balance_excludes_reversed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reversed passive entries are excluded from balance."""
    user_id = await _create_user(client, "pbal_rev")

    await record_passive_ledger(
        db_session,
        user_id=user_id,
        amount_cents=20000,
        status=LedgerStatus.CONFIRMED,
        reason="commission:l1:agent1:purchase1",
    )

    # Reversed entry.
    await record_passive_ledger(
        db_session,
        user_id=user_id,
        amount_cents=5000,
        status=LedgerStatus.REVERSED,
        reason="commission:l1:agent1:purchase2",
    )

    await db_session.commit()

    balance = await get_passive_balance(db_session, user_id)

    assert balance["confirmed"] == 20000
    assert balance["frozen"] == 0


# ---------------------------------------------------------------------------
# validate_route (AML matrix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_route_active_to_passive_forbidden() -> None:
    """Active -> Passive route raises AMLViolationError."""
    with pytest.raises(AMLViolationError):
        validate_route("active", "passive")


@pytest.mark.asyncio
async def test_validate_route_active_to_active_allowed() -> None:
    """Active -> Active route is allowed."""
    validate_route("active", "active")


@pytest.mark.asyncio
async def test_validate_route_passive_to_active_allowed() -> None:
    """Passive -> Active route is allowed."""
    validate_route("passive", "active")


@pytest.mark.asyncio
async def test_validate_route_passive_to_passive_allowed() -> None:
    """Passive -> Passive route is allowed."""
    validate_route("passive", "passive")
