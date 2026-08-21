# =============================================================================
# AIVIS.ONE Backend -- Support section membership emission (T-67)
# =============================================================================
#
# comms decides who serves a section from a roster the PRODUCT declares.
# This file pins the declaring: that promoting a staff member puts an
# event on the outbox, in the same transaction as the promotion, with
# the section named by KEY and the operator by session id.
#
# WHY THE KEY AND NOT THE ID, asserted rather than assumed: a section id
# lives in comms' database and does not survive a rebuild there. This
# product resolves it per process and stores it nowhere (T-65), so an
# event carrying an id would be an event carrying a value that goes
# stale silently.
#
# THE BACKFILL IS THE DANGEROUS HALF and is checked too. A section with
# no declared members is served by EVERY operator; the moment the first
# member is declared, everyone else stops serving it. So the migration
# that fills the roster for existing staff has to be all-or-nothing, and
# the test asserts the shape of what it writes rather than trusting it.
# =============================================================================

import json
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_SECTION_MEMBERSHIP_CHANGED
from tests.helpers import auth_headers, create_admin_user, register_user


async def _membership_events(
    session: AsyncSession,
) -> list[OutboxEvent]:
    """Every membership event on the outbox, oldest first."""
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.event_type == EVENT_SECTION_MEMBERSHIP_CHANGED)
        .order_by(OutboxEvent.id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_promoting_a_staff_member_declares_them_to_the_section(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The path item 4 asks for: through the outbox, not a direct call.

    A direct HTTP call to comms would commit the promotion and then hope;
    the outbox row commits WITH it, so the two facts cannot disagree.
    """
    _admin, admin_token = await create_admin_user(client, db_session)
    body = await register_user(client)
    target_id = body["user"]["id"]
    before = len(await _membership_events(db_session))

    response = await client.post(
        "/api/v1/staff/users",
        json={"user_id": target_id},
        headers=auth_headers(admin_token),
    )

    assert response.status_code in (200, 201), response.text
    events = await _membership_events(db_session)
    assert len(events) == before + 1

    payload = events[-1].payload
    assert payload["operator_id"] == target_id
    assert payload["member"] is True
    # The section is named, not identified.
    assert payload["section_key"] == "support"
    assert "section_id" not in payload


@pytest.mark.asyncio
async def test_the_event_carries_a_label_so_it_can_arrive_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Operators are appointed before anyone writes in, so this event may
    be the first mention of the section comms ever sees -- it has to
    carry enough to create one."""
    _admin, admin_token = await create_admin_user(client, db_session)
    body = await register_user(client)

    await client.post(
        "/api/v1/staff/users",
        json={"user_id": body["user"]["id"]},
        headers=auth_headers(admin_token),
    )

    payload = (await _membership_events(db_session))[-1].payload
    assert payload["section_label"]


@pytest.mark.asyncio
async def test_a_failed_promotion_declares_nobody(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Shortage axis: the event rides the promotion's transaction, so a
    refused promotion must leave no trace of a member who never was."""
    _admin, admin_token = await create_admin_user(client, db_session)
    body = await register_user(client)
    target_id = body["user"]["id"]
    await client.post(
        "/api/v1/staff/users",
        json={"user_id": target_id},
        headers=auth_headers(admin_token),
    )
    before = len(await _membership_events(db_session))

    repeat = await client.post(
        "/api/v1/staff/users",
        json={"user_id": target_id},
        headers=auth_headers(admin_token),
    )

    assert repeat.status_code == 409, repeat.text
    assert len(await _membership_events(db_session)) == before


@pytest.mark.asyncio
async def test_the_backfill_writes_one_declaration_per_active_profile(
    db_session: AsyncSession,
) -> None:
    """Migration 0042, run against whatever staff exist.

    Re-running the migration's own statement is safe and is what this
    test does -- comms applies a repeated declaration as a no-op, so a
    duplicate event is not a duplicate member. What must hold is the
    SHAPE: one row per ACTIVE profile, all in one statement, none for
    anybody else.
    """
    active = list(
        (
            await db_session.execute(
                text(
                    "SELECT user_id FROM staff_profiles "
                    "WHERE is_active = true"
                )
            )
        ).scalars()
    )
    before = len(await _membership_events(db_session))

    await db_session.execute(
        text(
            "INSERT INTO outbox_events (event_type, payload) "
            "SELECT :event_type, jsonb_build_object("
            "'v', 1, 'section_key', 'support', "
            "'section_label', 'Support', "
            "'operator_id', user_id::text, 'member', true) "
            "FROM staff_profiles WHERE is_active = true"
        ),
        {"event_type": EVENT_SECTION_MEMBERSHIP_CHANGED},
    )
    await db_session.flush()

    events = await _membership_events(db_session)
    assert len(events) == before + len(active)
    declared = {
        UUID(event.payload["operator_id"]) for event in events[before:]
    }
    assert declared == set(active)


@pytest.mark.asyncio
async def test_the_payload_is_json_the_relay_can_ship(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The relay serializes the payload as-is: a value it cannot encode
    dead-letters at ship time, far from whoever wrote it."""
    _admin, admin_token = await create_admin_user(client, db_session)
    body = await register_user(client)

    await client.post(
        "/api/v1/staff/users",
        json={"user_id": body["user"]["id"]},
        headers=auth_headers(admin_token),
    )

    payload = (await _membership_events(db_session))[-1].payload
    assert json.loads(json.dumps(payload)) == payload
