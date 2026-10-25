# =============================================================================
# AIVIS.ONE Backend -- the support spam bin (H40 item 7)
# =============================================================================
#
# A spam ticket can come back ("not spam") for SUPPORT_SPAM_RETENTION_DAYS;
# then the bin deletes it with its conversation, ours first, comms second,
# and keeps only the date of the appeal and its category (purge.py). Pinned:
#
#   1. only spam, and only past its retention, is taken;
#   2. what is taken leaves a tombstone and a purge row, and no pointer, no
#      ticket, no translation job;
#   3. comms' DELETE (204 -> None) clears the purge row; comms failing
#      keeps it, counted; a repeat is harmless;
#   4. a ticket somebody holds under its row lock is skipped, not waited
#      for (SKIP LOCKED) -- "not spam" and the bin never both get it;
#   5. a ticket the bin took is gone for "back to work": a 404.
#
# comms is the fake of tests/support_fake.py.
# =============================================================================

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session_factory
from app.core.events.models import OutboxEvent
from app.modules.support import purge
from app.modules.support.models import (
    SupportSpamTombstone,
    SupportThread,
    SupportThreadPurge,
    SupportTicket,
    SupportTranslationJob,
)
from tests.helpers import auth_headers, create_staff_user, register_user
from tests.support_fake import FakeComms, install


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    return install(monkeypatch)


async def _wipe(session: AsyncSession) -> None:
    # Spam residue of other suites would be buried by these steps and
    # counted here; each test starts from no spam at all.
    await session.execute(delete(SupportTicket).where(SupportTicket.status == "spam"))
    await session.execute(delete(SupportThreadPurge))
    await session.execute(delete(SupportSpamTombstone))
    await session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.payload["type"].astext.like("support.%")
            | OutboxEvent.payload["idempotency_key"].astext.like(
                "aivis:llm-support-tr:%"
            )
        )
    )
    await session.commit()


@pytest.fixture(autouse=True)
async def _clean(db_session: AsyncSession) -> Any:
    await _wipe(db_session)
    yield
    await _wipe(db_session)


async def _ticket(client: AsyncClient, *, topic: str = "kyc") -> str:
    body = await register_user(client)
    resp = await client.post(
        "/api/v1/support/tickets",
        json={"topic": topic, "body": "buy now"},
        headers={
            **auth_headers(body["session_token"]),
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ticket"]["id"]


async def _mark(
    session: AsyncSession, thread_id: str, *, status: str, age: timedelta
) -> None:
    await session.execute(
        text(
            "UPDATE support_tickets SET status = :s, status_changed_at = :at "
            "WHERE support_thread_id = (SELECT id FROM support_threads "
            "WHERE comms_thread_id = :t)"
        ),
        {"s": status, "at": datetime.now(UTC) - age, "t": UUID(thread_id)},
    )
    await session.commit()


def _retention() -> timedelta:
    return timedelta(days=settings.support_spam_retention_days)


async def _pointer(session: AsyncSession, thread_id: str) -> SupportThread | None:
    session.expire_all()
    return (
        await session.execute(
            select(SupportThread).where(
                SupportThread.comms_thread_id == UUID(thread_id)
            )
        )
    ).scalar_one_or_none()


async def _purges(session: AsyncSession) -> dict[str, SupportThreadPurge]:
    session.expire_all()
    rows = (await session.execute(select(SupportThreadPurge))).scalars()
    return {str(r.comms_thread_id): r for r in rows}


# ---------------------------------------------------------------------------
# 1-2. What the bin takes, and what it leaves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_spam_past_its_retention_is_taken(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    old_spam = await _ticket(client, topic="withdrawal")
    young_spam = await _ticket(client)
    old_resolved = await _ticket(client)
    over = _retention() + timedelta(minutes=1)
    await _mark(db_session, old_spam, status="spam", age=over)
    await _mark(
        db_session, young_spam, status="spam", age=_retention() - timedelta(minutes=5)
    )
    await _mark(db_session, old_resolved, status="resolved", age=over)

    buried, cleared = await purge.purge_spam_step()
    assert (buried, cleared) == (1, 1)
    assert await _pointer(db_session, old_spam) is None
    assert await _pointer(db_session, young_spam) is not None
    assert await _pointer(db_session, old_resolved) is not None
    assert old_spam not in comms.threads
    assert {young_spam, old_resolved} <= set(comms.threads)


@pytest.mark.asyncio
async def test_a_tombstone_keeps_the_date_and_the_category_and_nothing_else(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    tid = await _ticket(client, topic="withdrawal")
    pointer_id = (await _pointer(db_session, tid)).id  # a value, not the row
    appealed = (
        await db_session.execute(
            select(SupportTicket.created_at).where(
                SupportTicket.support_thread_id == pointer_id
            )
        )
    ).scalar_one()
    await _mark(db_session, tid, status="spam", age=_retention() + timedelta(hours=1))
    async with get_session_factory()() as session, session.begin():
        assert await purge.bury_spam(session, now=datetime.now(UTC)) == 1

    db_session.expire_all()
    [stone] = (await db_session.execute(select(SupportSpamTombstone))).scalars().all()
    assert (stone.appealed_at, stone.category) == (appealed, "withdrawals")
    columns = set(SupportSpamTombstone.__table__.columns.keys())
    assert columns == {"id", "appealed_at", "category"}
    assert list(await _purges(db_session)) == [tid]
    assert await _pointer(db_session, tid) is None
    gone = (
        await db_session.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.support_thread_id == pointer_id)
        )
    ).scalar_one()
    jobs_after = (
        await db_session.execute(
            select(func.count())
            .select_from(SupportTranslationJob)
            .where(SupportTranslationJob.support_thread_id == pointer_id)
        )
    ).scalar_one()
    assert (gone, jobs_after) == (0, 0)


@pytest.mark.asyncio
async def test_no_spam_is_a_step_that_does_nothing(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    await _ticket(client)
    assert await purge.purge_spam_step() == (0, 0)
    assert comms.calls_to("DELETE", "") == []


# ---------------------------------------------------------------------------
# 3. comms second
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_down_keeps_the_purge_row_for_the_next_step(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    tid = await _ticket(client)
    await _mark(db_session, tid, status="spam", age=_retention() + timedelta(hours=1))
    comms.fail[("DELETE", tid)] = purge.CommsUnavailableError()

    assert await purge.purge_spam_step() == (1, 0)
    row = (await _purges(db_session))[tid]
    assert (row.attempts, row.last_error_at is not None) == (1, True)
    assert await _pointer(db_session, tid) is None  # ours went first

    comms.fail.clear()
    assert await purge.purge_spam_step() == (0, 1)
    assert await _purges(db_session) == {}
    assert tid not in comms.threads


@pytest.mark.asyncio
async def test_a_thread_comms_no_longer_has_is_still_a_clean_delete(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    tid = await _ticket(client)
    await _mark(db_session, tid, status="spam", age=_retention() + timedelta(hours=1))
    comms.threads.pop(tid)  # deleted already -- comms still answers 204
    assert await purge.purge_spam_step() == (1, 1)
    assert await _purges(db_session) == {}


# ---------------------------------------------------------------------------
# 4-5. The bin and "not spam" never both get a ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_ticket_held_under_its_lock_is_skipped_not_waited_for(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    held = await _ticket(client)
    free = await _ticket(client)
    for tid in (held, free):
        await _mark(
            db_session, tid, status="spam", age=_retention() + timedelta(hours=1)
        )
    pointer = await _pointer(db_session, held)

    factory = get_session_factory()
    async with factory() as holder, holder.begin():
        await holder.execute(
            select(SupportTicket)
            .where(SupportTicket.support_thread_id == pointer.id)
            .with_for_update()
        )
        async with factory() as session, session.begin():
            assert await purge.bury_spam(session, now=datetime.now(UTC)) == 1
    assert await _pointer(db_session, held) is not None
    assert await _pointer(db_session, free) is None


@pytest.mark.asyncio
async def test_a_ticket_the_bin_took_is_gone_for_back_to_work(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    user, token = await create_staff_user(client, db_session)
    comms.serve(user.id)
    tid = await _ticket(client)
    await _mark(db_session, tid, status="spam", age=_retention() + timedelta(hours=1))
    await purge.purge_spam_step()
    resp = await client.post(
        f"/api/v1/staff/support/tickets/{tid}/reopen", headers=auth_headers(token)
    )
    assert resp.status_code == 404
    card = await client.get(
        f"/api/v1/staff/support/tickets/{tid}", headers=auth_headers(token)
    )
    assert card.status_code == 404
