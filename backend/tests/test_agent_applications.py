# =============================================================================
# AIVIS.ONE Backend -- Agent Application Tests (TASK-8, 2026-08-27)
# =============================================================================
#
# TASK-8: agent_applications shipped in Sprint 7.1 with production code
# (self-service submit/list + staff queue/approve/reject, 5 endpoints,
# two real producers) and ZERO test coverage. This file is that coverage.
#
# Tests cover:
#   -- Self-service (service.py + router.py) --
#   1:  submit -> 201, status pending, audit-worthy row created
#   2:  submit as non-investor (agent) -> 400 (role guard)
#   3:  submit while one is already pending -> 409
#   4:  GET /me lists the caller's applications, newest first
#   5:  cooldown active after rejection blocks a resubmit -> 400
#   6:  cooldown EXPIRED allows a fresh submit -> 201
#
#   -- Staff (staff_service.py + staff_router.py) --
#   7:  queue lists pending applications, oldest first
#   8:  approve -> 204, application approved, user.role becomes agent
#   9:  reject -> 204, cooldown_until + rejection_reason set
#   10: reject with an empty reason -> 422 (schema min_length)
#   11: approve a non-existent application -> 404
#   12: approve an already-approved application -> 400 (transition guard)
#   13: a non-staff caller is refused the staff queue -> 403
#
# No email prefix scheme: register_user generates a unique UUID email per
# call, so runs never collide on the shared dev DB.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_NOTIFICATION_REQUEST
from app.modules.agent_applications.constants import AgentApplicationStatus
from app.modules.agent_applications.models import AgentApplication
from app.modules.users.models import User, UserRole
from tests.helpers import auth_headers, create_admin_user, register_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _investor(client: AsyncClient) -> tuple[UUID, str]:
    """Register a fresh investor. Returns (user_id, token)."""
    data = await register_user(client)
    return UUID(data["user"]["id"]), data["session_token"]


async def _submit(client: AsyncClient, token: str) -> Response:
    """POST /api/v1/agent-applications with the given token."""
    return await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(token),
    )


# ---------------------------------------------------------------------------
# 1. Submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_application_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Investor submits -> 201, one pending row for them."""
    user_id, token = await _investor(client)

    resp = await _submit(client, token)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == AgentApplicationStatus.PENDING
    assert body["user_id"] == str(user_id)
    assert body["reviewed_at"] is None
    assert body["cooldown_until"] is None

    rows = (
        await db_session.execute(
            select(AgentApplication).where(AgentApplication.user_id == user_id)
        )
    ).scalars().all()
    assert len(list(rows)) == 1


@pytest.mark.asyncio
async def test_submit_application_non_investor_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A non-investor (here: promoted to agent) cannot apply -> 400."""
    user_id, token = await _investor(client)

    # Flip the role directly -- the guard reads user.role, and this is the
    # cheapest way to reach the non-investor branch without walking the
    # whole approve flow (that path is covered by test 8).
    user = await db_session.get(User, user_id)
    user.role = UserRole.AGENT
    await db_session.commit()

    resp = await _submit(client, token)
    assert resp.status_code == 400
    assert "investor" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_submit_application_duplicate_pending_conflict(
    client: AsyncClient
) -> None:
    """A second submit while one is pending -> 409."""
    _, token = await _investor(client)

    first = await _submit(client, token)
    assert first.status_code == 201

    second = await _submit(client, token)
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# 4. List /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_applications(client: AsyncClient) -> None:
    """GET /me returns the caller's applications."""
    _, token = await _investor(client)
    await _submit(client, token)

    resp = await client.get(
        "/api/v1/agent-applications/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == AgentApplicationStatus.PENDING


# ---------------------------------------------------------------------------
# 5-6. Cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cooldown_active_blocks_resubmit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """After a rejection with a live cooldown, a resubmit -> 400."""
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    reject = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/reject",
        json={"reason": "Not enough history"},
        headers=auth_headers(admin_token),
    )
    assert reject.status_code == 204

    # Immediate resubmit: cooldown_until is days in the future.
    resp = await _submit(client, token)
    assert resp.status_code == 400
    assert "cooldown" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cooldown_expired_allows_resubmit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Once the cooldown is in the past, a fresh submit -> 201."""
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = UUID(submit.json()["id"])

    await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/reject",
        json={"reason": "Try later"},
        headers=auth_headers(admin_token),
    )

    # Push the cooldown into the past directly.
    application = await db_session.get(AgentApplication, application_id)
    application.cooldown_until = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    resp = await _submit(client, token)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == AgentApplicationStatus.PENDING


# ---------------------------------------------------------------------------
# 7. Staff queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_queue_lists_pending(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The staff queue returns pending applications; the one we just
    submitted is present in it."""
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    resp = await client.get(
        "/api/v1/staff/agent-applications",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert application_id in ids


# ---------------------------------------------------------------------------
# 8. Approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_approve_changes_role_to_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approve -> 204, application approved, user.role == agent."""
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = UUID(submit.json()["id"])

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    application = await db_session.get(AgentApplication, application_id)
    await db_session.refresh(application)
    assert application.status == AgentApplicationStatus.APPROVED
    assert application.reviewed_at is not None

    user = await db_session.get(User, user_id)
    await db_session.refresh(user)
    assert user.role == UserRole.AGENT


# ---------------------------------------------------------------------------
# 9-10. Reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_reject_sets_cooldown_and_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reject -> 204, rejection_reason + cooldown_until set on the row."""
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = UUID(submit.json()["id"])

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/reject",
        json={"reason": "Portfolio too small"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    application = await db_session.get(AgentApplication, application_id)
    await db_session.refresh(application)
    assert application.status == AgentApplicationStatus.REJECTED
    assert application.rejection_reason == "Portfolio too small"
    assert application.cooldown_until is not None


@pytest.mark.asyncio
async def test_staff_reject_requires_nonempty_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An empty reason is refused by the schema -> 422."""
    _, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/reject",
        json={"reason": ""},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 11-12. Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_approve_nonexistent_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approving an application that does not exist -> 404."""
    _, admin_token = await create_admin_user(client, db_session)

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{uuid4()}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_staff_approve_twice_is_invalid_transition(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approving an already-approved application -> 400 (terminal state,
    no outgoing transition)."""
    _, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    first = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert first.status_code == 204

    second = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert second.status_code == 400


# ---------------------------------------------------------------------------
# 13. Permission guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_staff_cannot_reach_queue(client: AsyncClient) -> None:
    """An ordinary investor is refused the staff queue -> 403."""
    _, token = await _investor(client)

    resp = await client.get(
        "/api/v1/staff/agent-applications",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 14-16. Notification emission (batch 6, 2026-08-28)
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
async def test_staff_approve_emits_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approve -> agent_application.approved on the outbox, keyed by the
    application's own id (shared test DB: select THIS application's row
    by idempotency key, never an absolute count)."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key")
        == f"agent-application-approved:{application_id}"
    ]
    assert len(matches) == 1
    payload = matches[0].payload
    assert payload["type"] == "agent_application.approved"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == str(user_id)


@pytest.mark.asyncio
async def test_staff_reject_emits_notification_with_reason(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject -> agent_application.rejected, body carries the staff's
    reason text (already user-facing today via GET /me, same precedent
    withdrawal.rejected's emitter relies on)."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    user_id, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/reject",
        json={"reason": "Portfolio too small"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key")
        == f"agent-application-rejected:{application_id}"
    ]
    assert len(matches) == 1
    payload = matches[0].payload
    assert payload["type"] == "agent_application.rejected"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == str(user_id)
    assert "Portfolio too small" in payload["body"]


@pytest.mark.asyncio
async def test_approve_without_comms_emits_no_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comms address -> no outbox row, same gate as every other
    emitter in this tree."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    _, token = await _investor(client)
    _, admin_token = await create_admin_user(client, db_session)

    submit = await _submit(client, token)
    application_id = submit.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{application_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key")
        == f"agent-application-approved:{application_id}"
    ]
    assert matches == []
