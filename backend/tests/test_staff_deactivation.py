# =============================================================================
# AIVIS.ONE Backend -- Taking a staff member off duty (T-80)
# =============================================================================
#
# Until this delivery a staff member could not be removed at all:
# is_active was written once, True, at creation, and block_user refuses
# anyone whose role is STAFF. So what is pinned here is a path that had
# no predecessor -- and three refusals that matter more than the happy
# path:
#
#   * you cannot remove yourself;
#   * you cannot remove the last admin, because promotion and permission
#     grants both sit behind _require_admin and there would be nobody
#     left to hand admin back;
#   * a removal that is refused emits NOTHING -- no roster event, no
#     audit line. A journal that records removals which did not happen
#     is worse than no journal.
#
# And one thing that is easy to miss and is the reason item 3 existed:
# the avatar token is deliberately NOT in the user's session index, so
# logging the person out everywhere does not end an impersonation they
# are inside. That has its own test.
# =============================================================================

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_SECTION_MEMBERSHIP_CHANGED
from app.modules.staff import service as staff_service
from app.modules.staff.models import (
    AvatarSession,
    AvatarSessionStatus,
    StaffProfile,
)
from app.modules.staff.service import _active_admin_user_ids
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)


async def _profile_of(session: AsyncSession, user_id: UUID) -> StaffProfile:
    result = await session.execute(
        select(StaffProfile).where(StaffProfile.user_id == user_id)
    )
    return result.scalar_one()


async def _membership_events(session: AsyncSession) -> list[OutboxEvent]:
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.event_type == EVENT_SECTION_MEMBERSHIP_CHANGED)
        .order_by(OutboxEvent.id)
    )
    return list(result.scalars().all())


def _url(profile_id: UUID) -> str:
    return f"/api/v1/staff/users/{profile_id}/deactivate"


# ---------------------------------------------------------------------------
# 1. The path itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivation_flips_the_flag_and_tells_the_roster(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The two halves that must not be able to disagree: off duty here,
    off the roster there, one transaction."""
    _admin, admin_token = await create_admin_user(client, db_session)
    target, _token = await create_staff_user(client, db_session)
    profile = await _profile_of(db_session, target.id)
    before = len(await _membership_events(db_session))

    response = await client.post(
        _url(profile.id), headers=auth_headers(admin_token)
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(profile)
    assert profile.is_active is False

    events = await _membership_events(db_session)
    assert len(events) == before + 1
    assert events[-1].payload["operator_id"] == str(target.id)
    assert events[-1].payload["member"] is False


@pytest.mark.asyncio
async def test_a_deactivated_operator_stops_passing_the_support_gate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The positive half first, deliberately: a check that only proved
    the door was shut afterwards would pass just as well if it had never
    been open."""
    _admin, admin_token = await create_admin_user(client, db_session)
    target, target_token = await create_staff_user(client, db_session)
    profile = await _profile_of(db_session, target.id)

    before = await client.get(
        "/api/v1/staff/support/threads", headers=auth_headers(target_token)
    )
    assert before.status_code in (200, 502), before.text

    await client.post(_url(profile.id), headers=auth_headers(admin_token))

    after = await client.get(
        "/api/v1/staff/support/threads", headers=auth_headers(target_token)
    )
    assert after.status_code in (401, 403), after.text


@pytest.mark.asyncio
async def test_an_open_impersonation_is_closed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reason this is not covered by killing sessions: the avatar
    token is not in the user's session index, so delete_all_sessions
    cannot reach it. Without this the removed staff member sits inside
    somebody else's account until the TTL runs out."""
    _admin, admin_token = await create_admin_user(client, db_session)
    target, _token = await create_staff_user(client, db_session)
    profile = await _profile_of(db_session, target.id)
    # A REGISTERED user, not a fresh uuid: target_user_id is a real
    # foreign key. Same lesson as ip_address one line down -- a fixture
    # written from the model's column list rather than from what
    # start_avatar actually passes does not insert.
    victim_body = await register_user(client)
    victim = UUID(victim_body["user"]["id"])
    # Built the way start_avatar builds it, not the way the model
    # reads: ip_address is NOT NULL, and a row assembled from the
    # column list alone does not insert.
    avatar = AvatarSession(
        staff_id=target.id,
        target_user_id=victim,
        status=AvatarSessionStatus.ACTIVE,
        ip_address="203.0.113.7",
    )
    db_session.add(avatar)
    await db_session.commit()

    await client.post(_url(profile.id), headers=auth_headers(admin_token))

    await db_session.refresh(avatar)
    assert avatar.status == AvatarSessionStatus.ENDED
    assert avatar.ended_at is not None


# ---------------------------------------------------------------------------
# 2. The refusals -- and none of them may leave a trace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_you_cannot_deactivate_yourself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, admin_token = await create_admin_user(client, db_session)
    profile = await _profile_of(db_session, admin.id)
    before = len(await _membership_events(db_session))

    response = await client.post(
        _url(profile.id), headers=auth_headers(admin_token)
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "staff_self_deactivation"
    await db_session.refresh(profile)
    assert profile.is_active is True
    assert len(await _membership_events(db_session)) == before


@pytest.mark.asyncio
async def test_the_admin_count_sees_admins_and_ignores_plain_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Half one of the last-admin rule: the counting itself, for real.

    "Admin" is not a role in this product -- it is the state of holding
    every permission key -- so the count has to resolve each active
    profile's effective matrix. A plain staff member must not be counted
    as one, or the guard would think there are more admins than there
    are and let the last one go.
    """
    admin, _token = await create_admin_user(client, db_session)
    plain, _ = await create_staff_user(client, db_session)

    admin_ids = await _active_admin_user_ids(db_session)

    assert admin.id in admin_ids
    assert plain.id not in admin_ids


@pytest.mark.asyncio
async def test_the_last_admin_cannot_be_deactivated(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half two: the refusal, with the count forced to one.

    The count is forced rather than arranged, and that is a deliberate
    trade: this suite shares one database across a whole run, every
    other test creates its own admin, and they stay active -- so a
    genuine "one admin left" state cannot be reached here without
    deactivating other tests' fixtures out from under them. The counting
    is covered honestly by the test above; this covers the branch that
    reads it.

    What it protects: promotion and permission grants both sit behind
    _require_admin, so a product with no active admin has no way to
    grant admin back from inside.
    """
    _admin, admin_token = await create_admin_user(client, db_session)
    victim, _ = await create_admin_user(client, db_session)
    profile = await _profile_of(db_session, victim.id)
    before = len(await _membership_events(db_session))

    async def _only_the_victim(session: AsyncSession) -> list[UUID]:
        return [victim.id]

    monkeypatch.setattr(
        staff_service, "_active_admin_user_ids", _only_the_victim
    )

    response = await client.post(
        _url(profile.id), headers=auth_headers(admin_token)
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "staff_last_admin"
    await db_session.refresh(profile)
    assert profile.is_active is True
    assert len(await _membership_events(db_session)) == before


@pytest.mark.asyncio
async def test_deactivating_twice_is_refused_and_emits_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Repetition axis. Not an idempotent success: this action writes an
    audit record, and a second 'removed' line for a removal that did not
    happen is a lie to whoever reads the journal later."""
    _admin, admin_token = await create_admin_user(client, db_session)
    target, _token = await create_staff_user(client, db_session)
    profile = await _profile_of(db_session, target.id)

    first = await client.post(
        _url(profile.id), headers=auth_headers(admin_token)
    )
    after_first = len(await _membership_events(db_session))
    second = await client.post(
        _url(profile.id), headers=auth_headers(admin_token)
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"] == "staff_already_inactive"
    assert len(await _membership_events(db_session)) == after_first


@pytest.mark.asyncio
async def test_an_unknown_profile_is_a_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Shortage axis."""
    _admin, admin_token = await create_admin_user(client, db_session)
    before = len(await _membership_events(db_session))

    response = await client.post(
        _url(uuid4()), headers=auth_headers(admin_token)
    )

    assert response.status_code == 404, response.text
    assert len(await _membership_events(db_session)) == before


@pytest.mark.asyncio
async def test_a_plain_staff_member_cannot_deactivate_anyone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Granting staff and taking it away are one right: this endpoint is
    behind the same admin check as promotion."""
    _plain, plain_token = await create_staff_user(client, db_session)
    target, _ = await create_staff_user(client, db_session)
    profile = await _profile_of(db_session, target.id)
    before = len(await _membership_events(db_session))

    response = await client.post(
        _url(profile.id), headers=auth_headers(plain_token)
    )

    assert response.status_code == 403, response.text
    await db_session.refresh(profile)
    assert profile.is_active is True
    assert len(await _membership_events(db_session)) == before
