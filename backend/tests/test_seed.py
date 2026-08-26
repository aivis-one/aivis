# =============================================================================
# AIVIS.ONE Backend -- tests for the profile-driven seed (T-72)
# =============================================================================
#
# WHAT THESE TESTS ARE FOR. The rule the seed exists to enforce is "every
# row goes through the path the application itself uses", and the visible
# consequence of that rule is that comms hears about the people it makes.
# So the assertions below are about the PATH being walked, not about the
# rows looking right.
#
# WHY THE OUTBOX IS NOT THE ASSERTION ON ITS OWN. ensure_recipient has
# THREE outcomes, not two, and only one of them writes an outbox row:
#
#   comms not configured    -> no HTTP call, and NO outbox row either
#   configured + reachable  -> synchronous upsert, no outbox row
#   configured + unreachable-> user_upserted lands in the outbox
#
# The test database has no comms address, so it is permanently in the
# first state. "Every seeded user has an outbox row" would therefore be
# false on a healthy stand and on healthy code -- which is why the
# acceptance is split three ways below: the unconfigured case asserts the
# seed does not DEPEND on comms, the unreachable case asserts the
# recipient path was actually walked, and membership is asserted
# separately because emit_support_membership has no such gate and writes
# every time.
#
# ISOLATION. conftest gives per-RUN isolation only, so every test here
# builds its own tiny profile with a uuid-suffixed marker and e-mail
# domain. Two tests can then seed, reset and refuse without seeing each
# other's rows.
# =============================================================================

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

import scripts.seed as seed
from app.core.events.models import OutboxEvent
from app.core.events.service import (
    EVENT_SECTION_MEMBERSHIP_CHANGED,
    EVENT_USER_UPSERTED,
)
from app.modules.staff.models import StaffProfile
from app.modules.users.models import OnboardingStep, User, UserRole

pytestmark = pytest.mark.asyncio


@pytest.fixture
def clean_stand(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend this stand has no administrator yet.

    Not a convenience: the admin bootstrap is defined by the absence of
    an admin, and the test database is SHARED across the whole run, so
    any other test file that promotes somebody to staff would otherwise
    decide which branch these tests take. Patching the lookup fixes the
    STATE the branch keys on, not the branch.
    """

    async def _none(_session: object) -> None:
        return None

    monkeypatch.setattr(seed, "_find_any_admin", _none)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(**overrides: Any) -> dict[str, Any]:
    """A minimal profile with a marker no other test can collide with."""
    tag = uuid.uuid4().hex[:8]
    profile: dict[str, Any] = {
        "description": f"test profile {tag}",
        "marker": f"pytest_{tag}",
        "email_domain": f"{tag}.seedtest.invalid",
        "demo_password": "seedpass123",
        "admin": {
            "email_local": "admin",
            "first_name": "Admin",
            "last_name": "Test",
            "country": "NL",
        },
        "staff": [
            {
                "email_local": "support1",
                "first_name": "Sup",
                "last_name": "One",
                "country": "NL",
            }
        ],
        "investors": [
            {
                "email_local": "investor1",
                "first_name": "Inv",
                "last_name": "One",
                "country": "NL",
            }
        ],
    }
    profile.update(overrides)
    return profile


async def _seeded_users(session: Any, marker: str) -> list[User]:
    stmt = select(User).where(User.seeded_profile == marker)
    return list((await session.execute(stmt)).scalars())


async def _events(session: Any, event_type: str, user_ids: set[str]) -> int:
    """Count outbox rows of a type whose payload names one of these ids.

    Both event shapes are checked because they disagree on the key --
    user_upserted carries `recipient_id`, section_membership_changed
    carries `operator_id` -- and a count that only knew one of them
    would silently return zero for the other.
    """
    stmt = select(OutboxEvent).where(OutboxEvent.event_type == event_type)
    rows = list((await session.execute(stmt)).scalars())
    hits = 0
    for row in rows:
        payload = row.payload or {}
        ident = payload.get("recipient_id") or payload.get("operator_id")
        if ident in user_ids:
            hits += 1
    return hits


# ---------------------------------------------------------------------------
# The rule: the seed does not depend on comms
# ---------------------------------------------------------------------------


async def test_seed_runs_with_comms_unconfigured_and_writes_no_outbox_rows(
    db_session: Any, clean_stand: None
) -> None:
    """comms absent: the seed completes, and emits no recipient events.

    This is the state the test DB is in, and it is the state a laptop is
    in. The assertion is deliberately "zero", not "some": ensure_recipient
    refuses to write an outbox row when there is no comms address,
    because the relay that would ship it is disabled by the same empty
    address and the row would grow the table forever without ever
    leaving it.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    assert len(users) == 3, "admin + support + investor"

    ids = {str(u.id) for u in users}
    assert await _events(db_session, EVENT_USER_UPSERTED, ids) == 0


async def test_seed_defers_recipients_to_outbox_when_comms_is_unreachable(
    db_session: Any, monkeypatch: pytest.MonkeyPatch, clean_stand: None
) -> None:
    """comms configured but down: every seeded user gets one event.

    This is the assertion that the RECIPIENT PATH WAS WALKED. It cannot
    be made by looking at the rows the seed wrote -- a user built with
    bare ORM looks identical -- so it is made by putting comms in the
    one state where walking the path leaves a trace.
    """
    comms_sync = _comms_sync()
    monkeypatch.setattr(comms_sync, "comms_configured", lambda: True)
    monkeypatch.setattr(comms_sync, "upsert_recipient", _always_fail)

    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    ids = {str(u.id) for u in users}
    assert await _events(db_session, EVENT_USER_UPSERTED, ids) == len(users)


async def test_every_seeded_staff_member_is_declared_to_the_section(
    db_session: Any, clean_stand: None
) -> None:
    """Membership is emitted for the admin and for the support staff.

    Unconditional on comms: emit_support_membership goes straight to the
    outbox with no comms_configured gate, so this holds in the same
    environment where the recipient test above asserts zero.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    staff_ids = {str(u.id) for u in users if u.role == UserRole.STAFF}
    assert len(staff_ids) == 2, "the bootstrapped admin and one operator"

    assert await _events(
        db_session, EVENT_SECTION_MEMBERSHIP_CHANGED, staff_ids
    ) == len(staff_ids)


# ---------------------------------------------------------------------------
# REPEAT -- a second run changes nothing
# ---------------------------------------------------------------------------


async def test_second_run_without_reset_is_a_no_op(
    db_session: Any, clean_stand: None
) -> None:
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()
    first = await _seeded_users(db_session, profile["marker"])

    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()
    second = await _seeded_users(db_session, profile["marker"])

    assert {u.id for u in first} == {u.id for u in second}


async def test_seed_refuses_to_adopt_a_user_it_did_not_create(
    db_session: Any, clean_stand: None
) -> None:
    """A live person at a seeded address is not taken over.

    Adoption would be worse than the collision it papers over: the row
    would acquire a marker, and the next --reset would delete a person
    the seed never made.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    investor_email = seed._email(profile, "investor1")
    user = await seed.find_user_by_email(db_session, investor_email)
    assert user is not None
    user.seeded_profile = None
    await db_session.flush()

    with pytest.raises(seed.SeedRefusedError):
        await seed.seed_profile(db_session, profile, "adminpass123")


# ---------------------------------------------------------------------------
# EMPTY / SHORTAGE
# ---------------------------------------------------------------------------


async def test_profile_without_required_keys_is_refused_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed, "PROFILES_DIR", tmp_path)
    (tmp_path / "broken.json").write_text('{"marker": "x"}', encoding="utf-8")

    with pytest.raises(seed.SeedRefusedError) as excinfo:
        seed.load_profile("broken")
    assert "email_domain" in str(excinfo.value)


async def test_unknown_profile_names_the_ones_that_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed, "PROFILES_DIR", tmp_path)
    (tmp_path / "alpha.json").write_text("{}", encoding="utf-8")

    with pytest.raises(seed.SeedRefusedError) as excinfo:
        seed.load_profile("nope")
    assert "alpha" in str(excinfo.value)


async def test_empty_profiles_directory_lists_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed, "PROFILES_DIR", tmp_path)
    assert seed.list_profiles() == []


async def test_shipped_default_profile_parses_and_declares_the_demo(
    db_session: Any,
) -> None:
    """The profile the stand actually runs is not left unchecked.

    Parsing only -- seeding it here would put its fixed e-mail addresses
    into the shared test database and collide with the next run.
    """
    profile = seed.load_profile("default")
    assert profile["marker"] == "default"
    assert profile["email_domain"] == "test.aivis.one"
    assert profile["admin"], "the demo has to be able to bootstrap staff"
    assert profile["staff"], "the support queue needs somebody to serve it"
    assert profile["company"]["products"], "the storefront cannot be empty"


# ---------------------------------------------------------------------------
# The live-staff refusal
# ---------------------------------------------------------------------------


async def test_refuses_when_active_staff_are_not_this_profiles(
    db_session: Any, clean_stand: None
) -> None:
    """Declaring seeded operators can silence live ones -- so it refuses.

    The guard is local on purpose: whether the live staff are declared
    in the comms roster is not answerable from here (the outbox payload
    that would say so is redacted after seven days), so the seed asks a
    question it CAN answer and errs towards refusing.
    """
    other = _profile()
    await seed.seed_profile(db_session, other, "adminpass123")
    await db_session.flush()

    mine = _profile()
    with pytest.raises(seed.SeedRefusedError) as excinfo:
        await seed.assert_no_live_staff(
            db_session, mine["marker"], allow_live_staff=False
        )
    assert "--allow-live-staff" in str(excinfo.value)

    # And the escape hatch is what it says it is.
    await seed.assert_no_live_staff(
        db_session, mine["marker"], allow_live_staff=True
    )


async def test_the_refusal_never_counts_this_profiles_own_staff(
    db_session: Any, clean_stand: None
) -> None:
    """Our own operators are not "live staff" to us.

    NOT WRITTEN AS "no refusal happens", which is what it said first and
    why it failed: conftest gives per-RUN isolation only, so by the time
    this file runs, other test modules have promoted staff of their own
    and the stand is never clean. A test that can only pass when it runs
    first is a flake, not a guard.

    So the assertion is on the PREDICATE instead of on the outcome: the
    refusal may well fire because of somebody else's staff, but the ids
    it names must never include ours. That is the actual contract --
    `IS DISTINCT FROM marker` -- and it holds in a dirty database.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    ours = {
        str(u.id)
        for u in await _seeded_users(db_session, profile["marker"])
        if u.role == UserRole.STAFF
    }
    assert ours, "the profile seeds staff; without them this proves nothing"

    try:
        await seed.assert_no_live_staff(
            db_session, profile["marker"], allow_live_staff=False
        )
    except seed.SeedRefusedError as exc:
        named = str(exc)
        for staff_id in ours:
            assert staff_id not in named, (
                f"the guard named our own staff member {staff_id} as "
                f"foreign; the marker comparison is not doing its job"
            )


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


async def test_reset_undeclares_staff_before_deleting_them(
    db_session: Any, clean_stand: None
) -> None:
    """The row that says "no longer an operator" is written, not skipped.

    Without it comms keeps a roster of operators that no longer exist,
    and because a section with ANY declared member is served only by
    those members, a reset that deleted the only declared ones would
    leave the section served by nobody at all.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    staff_ids = {str(u.id) for u in users if u.role == UserRole.STAFF}
    before = await _events(
        db_session, EVENT_SECTION_MEMBERSHIP_CHANGED, staff_ids
    )

    await seed.reset_seed_data(db_session, profile["marker"])
    await db_session.flush()

    after = await _events(
        db_session, EVENT_SECTION_MEMBERSHIP_CHANGED, staff_ids
    )
    assert after == before + len(staff_ids), (
        "one member=False event per seeded staff member, on top of the "
        "member=True events their creation emitted"
    )

    stmt = select(func.count()).select_from(OutboxEvent).where(
        OutboxEvent.event_type == EVENT_SECTION_MEMBERSHIP_CHANGED
    )
    assert (await db_session.execute(stmt)).scalar_one() > 0


async def test_reset_deletes_only_rows_carrying_this_marker(
    db_session: Any, clean_stand: None
) -> None:
    mine = _profile()
    theirs = _profile()
    await seed.seed_profile(db_session, mine, "adminpass123")
    await seed.seed_profile(
        db_session, theirs, "adminpass123"
    )
    await db_session.flush()

    theirs_ids = {u.id for u in await _seeded_users(db_session, theirs["marker"])}

    await seed.reset_seed_data(db_session, mine["marker"])
    await db_session.flush()

    assert await _seeded_users(db_session, mine["marker"]) == []
    survivors = {
        u.id for u in await _seeded_users(db_session, theirs["marker"])
    }
    assert survivors == theirs_ids


async def test_reset_leaves_unmarked_people_alone(
    db_session: Any, clean_stand: None
) -> None:
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    investor_email = seed._email(profile, "investor1")
    user = await seed.find_user_by_email(db_session, investor_email)
    assert user is not None
    # This person "registered by hand" at the demo domain.
    user.seeded_profile = None
    survivor_id = user.id
    await db_session.flush()

    await seed.reset_seed_data(db_session, profile["marker"])
    await db_session.flush()

    still_there = (
        await db_session.execute(select(User).where(User.id == survivor_id))
    ).scalar_one_or_none()
    assert still_there is not None, (
        "a NULL marker means the seed did not make this person, and "
        "--reset must not delete them even at the demo domain"
    )


async def test_reset_on_a_marker_with_no_rows_is_a_no_op(
    db_session: Any,
) -> None:
    counts = await seed.reset_seed_data(db_session, f"absent_{uuid.uuid4().hex}")
    assert counts["users"] == 0


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------


async def test_seeded_investor_finishes_the_onboarding_funnel(
    db_session: Any, clean_stand: None
) -> None:
    """A seeded person can actually sign in and use the product.

    register_email leaves REGISTERED / NOT_STARTED, and the frontend
    guards send anyone short of ONBOARDING_COMPLETE back into the
    funnel. The scripts this replaced solved that by writing the two
    columns by hand; this one walks the steps.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    user = await seed.find_user_by_email(
        db_session, seed._email(profile, "investor1")
    )
    assert user is not None
    assert user.onboarding_step == OnboardingStep.ONBOARDING_COMPLETE
    assert user.credentials["email"]["verified"] is True


async def test_an_existing_admin_is_reused_and_no_second_one_is_minted(
    db_session: Any
) -> None:
    """The bypass runs once per stand, not once per seed run.

    No clean_stand fixture here on purpose: this test is about the
    branch that fires when an admin already exists, and the profile
    seeded first is what makes it exist.
    """
    first = _profile()
    await seed.seed_profile(db_session, first, "adminpass123")
    await db_session.flush()

    second = _profile()
    await seed.seed_profile(db_session, second, "adminpass123")
    await db_session.flush()

    second_users = await _seeded_users(db_session, second["marker"])
    emails = {
        (u.credentials or {}).get("email", {}).get("email")
        for u in second_users
    }
    assert seed._email(second, "admin") not in emails, (
        "an admin already existed, so the second run must have used it "
        "as its actor instead of creating another administrator"
    )


async def test_the_bootstrapped_admin_has_every_permission(
    db_session: Any, clean_stand: None
) -> None:
    profile = _profile()
    await seed.seed_profile(db_session, profile, "adminpass123")
    await db_session.flush()

    admin = await seed.find_user_by_email(
        db_session, seed._email(profile, "admin")
    )
    assert admin is not None
    assert admin.role == UserRole.STAFF

    staff_profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == admin.id)
        )
    ).scalar_one()
    assert all(staff_profile.permissions.values())


# ---------------------------------------------------------------------------
# Local helpers that need the module under test imported first
# ---------------------------------------------------------------------------


def _comms_sync() -> Any:
    from app.core import comms_sync

    return comms_sync


async def _always_fail(*_args: Any, **_kwargs: Any) -> bool:
    return False
