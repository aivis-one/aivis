# =============================================================================
# AIVIS.ONE Backend -- the first admin (H30 P-118)
# =============================================================================
#
# app/modules/staff/bootstrap.py is the ONE copy of the bypass that makes an
# admin without an admin actor: `aivis bootstrap-admin <email>` on a
# production box, and the seed on test stands. These tests drive
# bootstrap_first_admin directly -- scripts/bootstrap_admin.py only reads
# the argument and reports.
#
# Every refusal is paired with "nothing was written": no staff profile, no
# role change, no staff.bootstrapped audit row, no membership event. The
# success test is the other half: the user is staff, is_admin() holds on
# the profile, one audit row with the system as actor, one membership
# event.
#
# Axes:
#   REPEAT    -- a second call after a success; the address in another
#                case and with surrounding blanks finds the same person
#   EMPTINESS -- a profile that exists but is inactive or not all-True
#                (not an admin, still refused); an unknown address
#   SHORTAGE  -- an unverified address; a blocked account
#
# The membership event is observed by replacing emit_support_membership:
# whether the real one writes an outbox row depends on comms being
# configured in the test environment, and that is not what is tested here.
# =============================================================================

import json
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.support.service as support_service
from app.modules.staff.bootstrap import (
    BootstrapRefusedError,
    bootstrap_first_admin,
    find_any_admin,
)
from app.modules.staff.constants import is_admin
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User, UserRole
from tests.helpers import create_staff_user, register_user


@pytest.fixture
def memberships(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    """Capture membership events instead of writing them."""
    seen: list[UUID] = []

    async def capture(session: AsyncSession, *, user_id: UUID, **_: Any) -> None:
        seen.append(user_id)

    monkeypatch.setattr(support_service, "emit_support_membership", capture)
    return seen


@pytest.fixture
async def no_admin(db_session: AsyncSession):
    """Start from a box with no active admin, and leave the database as found.

    Other suites leave admins behind in the shared test database. This
    takes every existing profile down to non-admin for the test (one
    permission false), then puts each one back exactly -- and keeps any
    admin the test itself made non-admin, so no later suite inherits it.
    """
    saved = (
        await db_session.execute(
            text("SELECT user_id, permissions FROM staff_profiles")
        )
    ).all()
    demote = text(
        "UPDATE staff_profiles SET permissions = "
        "permissions || '{\"user_block\": false}'::jsonb"
    )
    await db_session.execute(demote)
    await db_session.commit()
    assert await find_any_admin(db_session) is None

    yield

    await db_session.rollback()
    await db_session.execute(demote)
    for user_id, permissions in saved:
        await db_session.execute(
            text(
                "UPDATE staff_profiles SET permissions = CAST(:p AS jsonb) "
                "WHERE user_id = :uid"
            ),
            {"p": json.dumps(permissions), "uid": str(user_id)},
        )
    await db_session.commit()


async def _verify(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        text(
            "UPDATE users SET credentials = jsonb_set(credentials, "
            "'{email,verified}', 'true'::jsonb) WHERE id = :uid"
        ),
        {"uid": user_id},
    )
    await session.commit()
    # The session may hold this user from an earlier step (create_staff_user
    # builds it through the same session); a raw UPDATE does not refresh it.
    session.expire_all()


async def _registered(
    client: AsyncClient, session: AsyncSession, *, verified: bool = True
) -> dict[str, Any]:
    data = await register_user(client)
    if verified:
        await _verify(session, data["user"]["id"])
    return data


async def _bootstrapped_rows(session: AsyncSession, user_id: str | UUID) -> int:
    result = await session.execute(
        text(
            "SELECT count(*) FROM audit_log WHERE event = 'staff.bootstrapped' "
            "AND target_id = :uid"
        ),
        {"uid": str(user_id)},
    )
    return int(result.scalar_one())


async def _refused(session: AsyncSession, email: str) -> str:
    with pytest.raises(BootstrapRefusedError) as exc:
        await bootstrap_first_admin(session, email)
    await session.rollback()
    return str(exc.value)


async def _assert_untouched(
    session: AsyncSession, user_id: str | UUID, memberships: list[UUID]
) -> None:
    session.expire_all()
    user = (
        await session.execute(select(User).where(User.id == UUID(str(user_id))))
    ).scalar_one()
    assert user.role != UserRole.STAFF
    profile = (
        await session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    assert profile is None
    assert await _bootstrapped_rows(session, user_id) == 0
    assert memberships == []


# ---------------------------------------------------------------------------
# Success, and the second call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_admin_is_made_and_a_second_call_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    no_admin: None,
    memberships: list[UUID],
) -> None:
    """The registered, verified user -- found by the address in another
    case and with blanks around it -- becomes staff with every permission,
    one audit row with the system as actor, one membership event. A second
    call, for anyone, is refused: the box has an admin now."""
    data = await _registered(client, db_session)
    user_id = UUID(data["user"]["id"])

    user = await bootstrap_first_admin(db_session, f"  {data['email'].upper()} ")
    await db_session.commit()

    assert user.id == user_id
    assert user.role == UserRole.STAFF
    profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user_id)
        )
    ).scalar_one()
    assert profile.is_active is True
    assert profile.permissions
    assert is_admin(profile.permissions)
    assert (await find_any_admin(db_session)).id == user_id
    assert memberships == [user_id]

    row = (
        await db_session.execute(
            text(
                "SELECT actor_id, actor_type FROM audit_log "
                "WHERE event = 'staff.bootstrapped' AND target_id = :uid"
            ),
            {"uid": str(user_id)},
        )
    ).all()
    assert row == [(None, "system")]

    other = await _registered(client, db_session)
    message = await _refused(db_session, other["email"])
    assert "already has an admin" in message
    assert memberships == [user_id]
    await _assert_untouched(db_session, other["user"]["id"], [])


# ---------------------------------------------------------------------------
# Refusals -- each with nothing written
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_address_is_refused(
    db_session: AsyncSession, no_admin: None, memberships: list[UUID]
) -> None:
    message = await _refused(db_session, "nobody-registered-this@example.com")
    assert "Nobody is registered" in message
    assert memberships == []


@pytest.mark.asyncio
async def test_an_unverified_address_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    no_admin: None,
    memberships: list[UUID],
) -> None:
    data = await _registered(client, db_session, verified=False)
    message = await _refused(db_session, data["email"])
    assert "not verified" in message
    await _assert_untouched(db_session, data["user"]["id"], memberships)


@pytest.mark.asyncio
async def test_a_blocked_account_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    no_admin: None,
    memberships: list[UUID],
) -> None:
    data = await _registered(client, db_session)
    await db_session.execute(
        text("UPDATE users SET is_active = false WHERE id = :uid"),
        {"uid": data["user"]["id"]},
    )
    await db_session.commit()

    message = await _refused(db_session, data["email"])
    assert "blocked" in message
    await _assert_untouched(db_session, data["user"]["id"], memberships)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_state", ["not-all-true", "inactive"])
async def test_an_existing_staff_profile_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    no_admin: None,
    memberships: list[UUID],
    profile_state: str,
) -> None:
    """A staff member whose profile is not an admin -- fewer rights, or
    deactivated -- does not make the box "have an admin", and is still
    refused: appointing staff is the interface's job."""
    staff, _token = await create_staff_user(client, db_session)
    # Read before any expire_all: the instance belongs to this session.
    staff_id, staff_email = staff.id, staff.email
    if profile_state == "inactive":
        await db_session.execute(
            text("UPDATE staff_profiles SET is_active = false WHERE user_id = :uid"),
            {"uid": str(staff_id)},
        )
    await _verify(db_session, str(staff_id))
    assert await find_any_admin(db_session) is None

    before = (
        await db_session.execute(
            select(StaffProfile.permissions, StaffProfile.is_active).where(
                StaffProfile.user_id == staff_id
            )
        )
    ).one()

    message = await _refused(db_session, staff_email)
    assert "already has a staff profile" in message
    db_session.expire_all()
    after = (
        await db_session.execute(
            select(StaffProfile.permissions, StaffProfile.is_active).where(
                StaffProfile.user_id == staff_id
            )
        )
    ).one()
    assert after == before
    assert await _bootstrapped_rows(db_session, staff_id) == 0
    assert memberships == []
