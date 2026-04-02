# =============================================================================
# CBSHOME Backend -- Audit Log Tests
# =============================================================================
#
# Tests cover:
#   1. record_audit() creates AuditLog entry with correct fields
#   2. record_audit() reads trace_id from structlog contextvars
#   3. record_audit() does NOT commit (P-01) -- caller manages transaction
#   4. Avatar context (performed_by + on_behalf_of) is recorded correctly
# =============================================================================

from uuid import uuid4

import pytest
import structlog.contextvars
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog, record_audit


@pytest.mark.asyncio
async def test_record_audit_creates_entry(db_session: AsyncSession) -> None:
    """record_audit() creates an AuditLog entry with correct fields."""
    user_id = uuid4()

    entry = await record_audit(
        session=db_session,
        event="user.registered",
        actor_id=user_id,
        actor_type="user",
        target_type="user",
        target_id=user_id,
        data={"role": "investor"},
    )
    await db_session.commit()

    # Verify entry is in DB.
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.id == entry.id)
    )
    saved = result.scalar_one()

    assert saved.event == "user.registered"
    assert saved.actor_id == user_id
    assert saved.actor_type == "user"
    assert saved.target_type == "user"
    assert saved.target_id == user_id
    assert saved.data == {"role": "investor"}
    assert saved.performed_by is None
    assert saved.on_behalf_of is None


@pytest.mark.asyncio
async def test_record_audit_reads_trace_id_from_contextvars(
    db_session: AsyncSession,
) -> None:
    """record_audit() picks up trace_id from structlog contextvars."""
    expected_trace = "test-trace-id-42"
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=expected_trace)

    user_id = uuid4()
    entry = await record_audit(
        session=db_session,
        event="user.login",
        actor_id=user_id,
        actor_type="user",
        target_type="user",
        target_id=user_id,
    )
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.id == entry.id)
    )
    saved = result.scalar_one()
    assert saved.trace_id == expected_trace

    structlog.contextvars.clear_contextvars()


@pytest.mark.asyncio
async def test_record_audit_does_not_commit(db_session: AsyncSession) -> None:
    """record_audit() flushes but does not commit -- caller manages transaction."""
    user_id = uuid4()

    entry = await record_audit(
        session=db_session,
        event="test.no_commit",
        actor_id=user_id,
        actor_type="system",
        target_type="user",
        target_id=user_id,
    )

    # Entry is flushed (has ID) but not yet committed.
    assert entry.id is not None

    # Roll back -- entry should not persist.
    await db_session.rollback()

    # Verify entry is NOT in DB after rollback.
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.id == entry.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_record_audit_avatar_context(db_session: AsyncSession) -> None:
    """Avatar context fields (performed_by, on_behalf_of) are stored correctly."""
    staff_id = uuid4()
    target_user_id = uuid4()
    resource_id = uuid4()

    entry = await record_audit(
        session=db_session,
        event="staff.avatar_started",
        actor_id=staff_id,
        actor_type="staff",
        target_type="user",
        target_id=target_user_id,
        performed_by=staff_id,
        on_behalf_of=target_user_id,
        data={"resource_id": str(resource_id)},
    )
    await db_session.commit()

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.id == entry.id)
    )
    saved = result.scalar_one()

    assert saved.performed_by == staff_id
    assert saved.on_behalf_of == target_user_id
    assert saved.actor_type == "staff"
    assert saved.event == "staff.avatar_started"
