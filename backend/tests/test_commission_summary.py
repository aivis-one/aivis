# =============================================================================
# AIVIS.ONE Backend -- Commission Summary Tests (Task 2b Block C)
# =============================================================================
#
# Tests cover:
#   1: month-to-date sum: frozen + confirmed commission AND volume-bonus
#      entries of the current UTC month are summed; reversed entries and
#      a previous-month entry are excluded
#   2: empty agent -> 0; non-agent -> 403
#   3: /commissions/me offset pagination is stable when rows share
#      created_at (id tie-breaker) -- no duplicate/skip across pages
#
# Previous-month entry is inserted as a direct PassiveLedger row with
# an explicit created_at (the service helper always stamps "now").
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commissions.constants import current_month_start
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
    created_at: datetime | None = None,
) -> PassiveLedger:
    row = PassiveLedger(
        user_id=agent_id,
        amount_cents=amount_cents,
        status=status,
        reason=reason,
    )
    if created_at is not None:
        row.created_at = created_at
    return row


@pytest.mark.asyncio
async def test_commission_summary_month_window_and_status_parity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """frozen+confirmed commission AND volume-bonus of the current month
    in; reversed and previous-month entries out."""
    agent_id, token = await _make_agent(client, db_session)

    month_start = current_month_start()
    prev_month_dt = datetime(
        month_start.year, month_start.month, month_start.day, tzinfo=UTC
    ) - timedelta(days=1)

    db_session.add_all([
        _ledger_row(
            agent_id, amount_cents=1_000,
            status=LedgerStatus.FROZEN, reason=_commission_reason(),
        ),
        _ledger_row(
            agent_id, amount_cents=2_000,
            status=LedgerStatus.CONFIRMED, reason=_commission_reason(),
        ),
        # Clawed-back commission -- excluded.
        _ledger_row(
            agent_id, amount_cents=5_000,
            status=LedgerStatus.REVERSED, reason=_commission_reason(),
        ),
        # Volume bonus -- part of monthly agent earnings, INCLUDED.
        _ledger_row(
            agent_id, amount_cents=700,
            status=LedgerStatus.CONFIRMED,
            reason=f"volume_bonus:monthly:{uuid4()}",
        ),
        # Previous month -- outside the window.
        _ledger_row(
            agent_id, amount_cents=9_000,
            status=LedgerStatus.CONFIRMED, reason=_commission_reason(),
            created_at=prev_month_dt,
        ),
    ])
    await db_session.commit()

    resp = await client.get(
        "/api/v1/agent/commissions/summary", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    # 1000 + 2000 (commissions) + 700 (volume bonus); 5000 reversed and
    # 9000 previous-month excluded.
    assert resp.json() == {"month_to_date_cents": 3_700}


@pytest.mark.asyncio
async def test_commission_summary_empty_and_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Fresh agent -> 0; plain investor -> 403."""
    _, token = await _make_agent(client, db_session)
    resp = await client.get(
        "/api/v1/agent/commissions/summary", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json() == {"month_to_date_cents": 0}

    investor = await register_user(client)
    resp2 = await client.get(
        "/api/v1/agent/commissions/summary",
        headers=auth_headers(investor["session_token"]),
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_commissions_list_pagination_stable_on_equal_created_at(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rows written in one transaction share created_at (func.now()).
    Offset pagination must still be total-order stable via the id
    tie-breaker -- no row duplicated or skipped across pages."""
    agent_id, token = await _make_agent(client, db_session)

    # Three commission rows in ONE commit -> identical created_at.
    db_session.add_all([
        _ledger_row(
            agent_id, amount_cents=amt,
            status=LedgerStatus.CONFIRMED, reason=_commission_reason(),
        )
        for amt in (1_000, 2_000, 3_000)
    ])
    await db_session.commit()

    # Page one row at a time; collect ids.
    seen: list[str] = []
    for offset in range(3):
        resp = await client.get(
            f"/api/v1/agent/commissions/me?limit=1&offset={offset}",
            headers=auth_headers(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 1
        seen.append(body["items"][0]["id"])

    # All three distinct -> no dup, no skip across pages.
    assert len(set(seen)) == 3
