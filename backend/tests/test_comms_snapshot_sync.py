# =============================================================================
# AIVIS.ONE Backend -- every change of the snapshot reaches comms (H23 P-113)
# =============================================================================
#
# comms rechecks `active` before every send against its OWN copy of the
# person, and renders in the language it holds. Until H23 that copy was
# written once, at creation; a blocked or self-deactivated person kept
# receiving, and a changed language never arrived. core/comms_sync.py
# names the sites and how they were found; each is driven here through
# its real route, and what is asserted is the snapshot comms received.
#
# The recipient upsert is replaced by a recorder that answers STORED: the
# claim is "a new snapshot with a higher version was sent", and the wire
# form of that call is test_comms_client.py's subject.
# =============================================================================

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import comms_sync
from app.core.comms import UpsertOutcome
from app.core.config import settings
from tests.helpers import auth_headers, create_admin_user, register_user


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[UUID, dict[str, Any]]]:
    """Every snapshot sync_recipient hands to comms, in order."""
    log: list[tuple[UUID, dict[str, Any]]] = []

    async def _record(recipient_id: UUID, snapshot: dict[str, Any]) -> UpsertOutcome:
        log.append((recipient_id, dict(snapshot)))
        return UpsertOutcome.STORED

    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    monkeypatch.setattr(settings, "comms_service_token", "t")
    monkeypatch.setattr(comms_sync, "upsert_recipient", _record)
    return log


def _for(log: list[tuple[UUID, dict[str, Any]]], user_id: str) -> list[dict[str, Any]]:
    return [snap for rid, snap in log if str(rid) == user_id]


@pytest.mark.asyncio
async def test_a_language_change_sends_a_new_snapshot(
    client: AsyncClient, sent: list
) -> None:
    data = await register_user(client)
    user_id = data["user"]["id"]
    created = _for(sent, user_id)

    response = await client.patch(
        "/api/v1/users/me",
        json={"language": "ru"},
        headers=auth_headers(data["session_token"]),
    )

    assert response.status_code == 200, response.text
    snapshots = _for(sent, user_id)
    assert len(snapshots) == len(created) + 1
    assert snapshots[-1]["locale"] == "ru"
    assert snapshots[-1]["version"] > created[-1]["version"]


@pytest.mark.asyncio
async def test_setting_the_same_language_sends_nothing(
    client: AsyncClient, sent: list
) -> None:
    """The twin: not every PATCH is a change of the snapshot."""
    data = await register_user(client)
    user_id = data["user"]["id"]
    created = len(_for(sent, user_id))

    response = await client.patch(
        "/api/v1/users/me",
        json={"language": "en"},
        headers=auth_headers(data["session_token"]),
    )

    assert response.status_code == 200, response.text
    assert len(_for(sent, user_id)) == created


@pytest.mark.asyncio
async def test_self_deactivation_sends_an_inactive_snapshot(
    client: AsyncClient, sent: list
) -> None:
    password = "Password123!"
    data = await register_user(client, password=password)
    user_id = data["user"]["id"]

    response = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": password},
        headers=auth_headers(data["session_token"]),
    )

    assert response.status_code in (200, 204), response.text
    assert _for(sent, user_id)[-1]["active"] is False


@pytest.mark.asyncio
async def test_block_and_unblock_each_send_a_snapshot(
    client: AsyncClient, db_session: AsyncSession, sent: list
) -> None:
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)
    user_id = data["user"]["id"]

    blocked = await client.patch(
        f"/api/v1/staff/users/{user_id}/block",
        json={"reason": "test block"},
        headers=auth_headers(admin_token),
    )
    assert blocked.status_code == 204, blocked.text
    after_block = _for(sent, user_id)[-1]
    assert after_block["active"] is False

    unblocked = await client.patch(
        f"/api/v1/staff/users/{user_id}/unblock",
        json={"reason": "test unblock"},
        headers=auth_headers(admin_token),
    )
    assert unblocked.status_code in (200, 204), unblocked.text
    after_unblock = _for(sent, user_id)[-1]
    assert after_unblock["active"] is True
    # Two changes, two versions, in order: comms applies the higher one.
    assert after_unblock["version"] == after_block["version"] + 1


@pytest.mark.asyncio
async def test_a_support_email_change_sends_the_new_address(
    client: AsyncClient, db_session: AsyncSession, sent: list
) -> None:
    """H28 P-105: comms delivers to its own copy of the address, so each
    change sends a snapshot carrying the new one, and two changes in a row
    are two versions in order."""
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)
    user_id = data["user"]["id"]
    before = _for(sent, user_id)[-1]
    assert before["email"] == data["email"]

    versions = []
    for address in ("first_move@example.com", "second_move@example.com"):
        address = address.replace("@", f"_{user_id[:8]}@")
        changed = await client.patch(
            f"/api/v1/staff/users/{user_id}/email",
            json={"email": address, "reason": "identity checked by support"},
            headers=auth_headers(admin_token),
        )
        assert changed.status_code == 204, changed.text
        snapshot = _for(sent, user_id)[-1]
        assert snapshot["email"] == address
        versions.append(snapshot["version"])

    assert versions == [before["version"] + 1, before["version"] + 2]
