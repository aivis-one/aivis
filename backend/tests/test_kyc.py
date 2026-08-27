# =============================================================================
# AIVIS.ONE Backend -- KYC Tests (Sprint 2.1)
# =============================================================================
#
# Tests cover:
#   1: Submit KYC -> 201, status=submitted, User.kyc_status synced
#   2: Duplicate submit (pending exists) -> 409
#   3: GET /kyc/status -> current status + application info
#   4: Webhook approved -> application + User.kyc_status updated
#   5: Rejected -> resubmit -> approved (history: 2 applications)
#   6: Webhook with non-existent user_id -> 404
#   7: Webhook with invalid status -> 422
#   8: Webhook approved/rejected -> notification_request on the outbox
#      (TASK-24 batch 3, 2026-08-27 -- the first aivis producer of this
#      event; see comms-profile/types.yaml)
#   9: Webhook with comms NOT configured -> no outbox row (same gate as
#      comms_sync.ensure_recipient / support.service's membership emitter)
#
# Email prefix: "s21_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_NOTIFICATION_REQUEST
from app.modules.kyc.models import KYCApplication
from tests.helpers import auth_headers, register_user



def webhook_headers() -> dict[str, str]:
    """Build headers with webhook secret for KYC webhook calls."""
    return {"X-Webhook-Secret": settings.kyc_webhook_secret}


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_kyc_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Submit KYC -> 201, status=submitted, User.kyc_status synced."""
    data = await register_user(client)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "submitted"

    # Verify User.kyc_status is synced.
    resp_me = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp_me.json()["kyc_status"] == "submitted"


@pytest.mark.asyncio
async def test_submit_kyc_duplicate(client: AsyncClient) -> None:
    """Submit KYC when pending application exists -> 409."""
    data = await register_user(client)
    token = data["session_token"]

    # First submit.
    resp1 = await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )
    assert resp1.status_code == 201

    # Second submit -> conflict.
    resp2 = await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_kyc_status(client: AsyncClient) -> None:
    """GET /kyc/status returns current status and application info."""
    data = await register_user(client)
    token = data["session_token"]

    # Before submit.
    resp = await client.get(
        "/api/v1/kyc/status",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kyc_status"] == "not_started"
    assert body["application_id"] is None

    # After submit.
    await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )

    resp2 = await client.get(
        "/api/v1/kyc/status",
        headers=auth_headers(token),
    )
    body2 = resp2.json()
    assert body2["kyc_status"] == "submitted"
    assert body2["application_id"] is not None
    assert body2["application_status"] == "submitted"


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_approved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Webhook approved -> application and User.kyc_status updated."""
    data = await register_user(client)
    token = data["session_token"]
    user_id = data["user"]["id"]

    # Submit KYC first.
    await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )

    # Webhook: approved.
    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "approved"},
        headers=webhook_headers(),
    )
    assert resp.status_code == 200

    # Verify via GET /users/me.
    resp_me = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp_me.json()["kyc_status"] == "approved"


@pytest.mark.asyncio
async def test_webhook_rejected_then_resubmit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rejected -> resubmit -> approved. Two KYCApplication rows."""
    data = await register_user(client)
    token = data["session_token"]
    user_id = data["user"]["id"]

    # Submit -> reject.
    await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )
    await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "rejected"},
        headers=webhook_headers(),
    )

    # Verify rejected.
    resp_me = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp_me.json()["kyc_status"] == "rejected"

    # Resubmit (no pending anymore, should succeed).
    resp2 = await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 201

    # Approve the new one.
    await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "approved"},
        headers=webhook_headers(),
    )

    resp_final = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp_final.json()["kyc_status"] == "approved"

    # Verify history: 2 KYCApplication rows.
    await db_session.rollback()  # Clear any stale state.
    stmt = (
        select(KYCApplication)
        .where(KYCApplication.user_id == user_id)
        .order_by(KYCApplication.created_at)
    )
    result = await db_session.execute(stmt)
    apps = result.scalars().all()
    assert len(apps) == 2
    assert apps[0].status == "rejected"
    assert apps[1].status == "approved"


@pytest.mark.asyncio
async def test_webhook_nonexistent_user(client: AsyncClient) -> None:
    """Webhook with non-existent user_id -> 404."""
    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": str(uuid4()), "status": "approved"},
        headers=webhook_headers(),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_invalid_status(client: AsyncClient) -> None:
    """Webhook with invalid status (not approved/rejected) -> 422."""
    data = await register_user(client)
    user_id = data["user"]["id"]

    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "bogus"},
        headers=webhook_headers(),
    )
    # Pydantic schema regex rejects "bogus" -> 422.
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Notification emission (TASK-24 batch 3)
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
async def test_webhook_approved_emits_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approved webhook, with comms configured, puts kyc.approved on the
    outbox -- through the transaction, not a direct call, same discipline
    as every other emitter in this tree."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    data = await register_user(client)
    token = data["session_token"]
    user_id = data["user"]["id"]
    before = len(await _notification_events(db_session))

    await client.post("/api/v1/kyc/submit", headers=auth_headers(token))
    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "approved"},
        headers=webhook_headers(),
    )
    assert resp.status_code == 200

    events = await _notification_events(db_session)
    assert len(events) == before + 1
    payload = events[-1].payload
    assert payload["type"] == "kyc.approved"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == user_id
    assert payload["idempotency_key"].startswith("kyc-decision:")
    assert payload["title"] and payload["body"]


@pytest.mark.asyncio
async def test_webhook_rejected_emits_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejected webhook emits kyc.rejected, not the approved type key."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    data = await register_user(client)
    token = data["session_token"]
    user_id = data["user"]["id"]

    await client.post("/api/v1/kyc/submit", headers=auth_headers(token))
    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "rejected"},
        headers=webhook_headers(),
    )
    assert resp.status_code == 200

    events = await _notification_events(db_session)
    assert events[-1].payload["type"] == "kyc.rejected"


@pytest.mark.asyncio
async def test_webhook_without_comms_emits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comms address -> no outbox row, same gate as the two existing
    emitters (ensure_recipient, emit_support_membership): the relay is
    disabled by the same empty setting, so a row here would sit unshipped
    forever -- growth, not delivery, exactly the reasoning comms_sync.py
    states for its own gate."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    data = await register_user(client)
    token = data["session_token"]
    user_id = data["user"]["id"]
    before = len(await _notification_events(db_session))

    await client.post("/api/v1/kyc/submit", headers=auth_headers(token))
    resp = await client.post(
        "/api/v1/kyc/webhook",
        json={"user_id": user_id, "status": "approved"},
        headers=webhook_headers(),
    )
    assert resp.status_code == 200

    assert len(await _notification_events(db_session)) == before
