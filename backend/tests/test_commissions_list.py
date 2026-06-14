# =============================================================================
# CBSHOME Backend -- Commission List Tests (review follow-up)
# =============================================================================
#
# Covers GET /api/v1/agent/commissions/me (the history LIST endpoint --
# the summary endpoint has its own suite). Locks the response contract:
#   1: every item carries its underlying PassiveLedger id; commission
#      and volume_bonus rows surface with the right type; reversed
#      entries ARE listed (the list does not filter by status).
#   2: non-agent -> 403.
#
# Commission/volume-bonus reasons point at random uuids; the enrichment
# JOINs miss (investor_name/product_name/rank stay null) but the entry
# still surfaces -- which is exactly what the shape test needs.
# =============================================================================

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import LedgerStatus, PassiveLedger
from app.modules.users.models import User, UserRole
from tests.helpers import auth_headers, register_user


def _commission_reason() -> str:
    return f"commission:l1:{uuid4()}:{uuid4()}"


async def _make_agent(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[UUID, str]:
    data = await register_user(client)
    user_id = UUID(data["user"]["id"])
    user = (await db_session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    return user_id, data["session_token"]


def _ledger_row(
    agent_id: UUID,
    *,
    amount_cents: int,
    status: str,
    reason: str,
) -> PassiveLedger:
    return PassiveLedger(
        user_id=agent_id,
        amount_cents=amount_cents,
        status=status,
        reason=reason,
    )


@pytest.mark.asyncio
async def test_commissions_list_items_carry_id_and_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Each item exposes its PassiveLedger id; commission + volume_bonus
    surface with the right type; a reversed commission is listed too."""
    agent_id, token = await _make_agent(client, db_session)

    commission = _ledger_row(
        agent_id, amount_cents=1_500,
        status=LedgerStatus.CONFIRMED, reason=_commission_reason(),
    )
    bonus = _ledger_row(
        agent_id, amount_cents=700,
        status=LedgerStatus.CONFIRMED,
        reason=f"volume_bonus:monthly:{uuid4()}",
    )
    reversed_commission = _ledger_row(
        agent_id, amount_cents=500,
        status=LedgerStatus.REVERSED, reason=_commission_reason(),
    )
    db_session.add_all([commission, bonus, reversed_commission])
    await db_session.commit()

    commission_id = str(commission.id)
    bonus_id = str(bonus.id)
    reversed_id = str(reversed_commission.id)

    resp = await client.get(
        "/api/v1/agent/commissions/me", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 3
    items = body["items"]
    assert len(items) == 3

    # Every row carries its ledger id -- and the reversed entry is among
    # them (the list does not filter by status).
    by_id = {item["id"]: item for item in items}
    assert set(by_id) == {commission_id, bonus_id, reversed_id}

    # Type discrimination.
    assert by_id[commission_id]["type"] == "commission"
    assert by_id[bonus_id]["type"] == "volume_bonus"
    assert by_id[bonus_id]["period_type"] == "monthly"
    assert by_id[reversed_id]["type"] == "commission"

    # Status round-trips as a non-empty string (exact tokens are the
    # ledger's concern; honesty of the field is what matters here).
    assert isinstance(by_id[commission_id]["status"], str)
    assert by_id[commission_id]["status"]
    assert isinstance(by_id[reversed_id]["status"], str)
    assert by_id[reversed_id]["status"]


@pytest.mark.asyncio
async def test_commissions_list_non_agent_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A plain investor cannot read the commission list."""
    investor = await register_user(client)
    resp = await client.get(
        "/api/v1/agent/commissions/me",
        headers=auth_headers(investor["session_token"]),
    )
    assert resp.status_code == 403
