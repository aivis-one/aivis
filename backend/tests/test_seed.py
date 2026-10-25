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
# WHY THE OUTBOX IS NOT THE ASSERTION ON ITS OWN. sync_recipient has
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
# separately because it answers a different question.
#
# T-93 UPDATE: emit_support_membership now carries the SAME gate as
# sync_recipient -- no comms address, no row -- so the membership
# assertion below states the address it needs instead of relying on
# whichever .env the box happens to run pytest with.
#
# ISOLATION. conftest gives per-RUN isolation only, so every test here
# builds its own tiny profile with a uuid-suffixed marker and uuid-tagged
# e-mail local parts. (Until H37 the tag sat in the profile's
# email_domain; the domain is now the host of FRONTEND_BASE_URL, which the
# `stand` fixture pins.) Two tests can then seed, reset and refuse without
# seeing each other's rows.
#
# THE ADMIN (H37). The seed no longer makes the first admin: it acts as
# the stand's active admin and refuses a stand without one. The `stand`
# fixture therefore provides a real admin and pins the lookup to it --
# the shared database decides nothing about which branch a test takes.
# =============================================================================

from __future__ import annotations

import argparse
import copy
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

import scripts.seed as seed
from app.core.comms import UpsertOutcome
from app.core.config import settings as seed_settings
from app.core.events.models import OutboxEvent
from app.core.events.service import (
    EVENT_SECTION_MEMBERSHIP_CHANGED,
    EVENT_USER_UPSERTED,
)
from app.modules.staff.models import StaffProfile
from app.modules.users.models import OnboardingStep, User, UserRole
from tests.helpers import create_admin_user

pytestmark = pytest.mark.asyncio


SEED_HOST = "seedtest.example.com"


@pytest.fixture
async def stand(
    client: AsyncClient, db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> User:
    """A stand with one active admin, and the box address pinned.

    The admin is a real one (helpers.create_admin_user), and the seed's
    lookup is pinned to it: the test database is SHARED across the run, so
    without the pin another file's admins would decide which one acts.
    FRONTEND_BASE_URL is pinned because the seeded addresses are built on
    its host (H37); the test default (localhost) is refused by design.
    """
    monkeypatch.setattr(seed_settings, "frontend_base_url", f"https://{SEED_HOST}")
    admin, _token = await create_admin_user(client, db_session)
    admin = await db_session.get(User, admin.id)

    async def _this_admin(_session: object) -> User:
        return admin

    monkeypatch.setattr(seed, "find_any_admin", _this_admin)
    return admin


@pytest.fixture
def no_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand with no active admin (the lookup answers None)."""
    monkeypatch.setattr(seed_settings, "frontend_base_url", f"https://{SEED_HOST}")

    async def _none(_session: object) -> None:
        return None

    monkeypatch.setattr(seed, "find_any_admin", _none)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(**overrides: Any) -> dict[str, Any]:
    """A minimal profile with a marker and addresses no other test can
    collide with."""
    tag = uuid.uuid4().hex[:8]
    profile: dict[str, Any] = {
        "description": f"test profile {tag}",
        "marker": f"pytest_{tag}",
        "staff": [
            {
                "email_local": f"support1-{tag}",
                "first_name": "Sup",
                "last_name": "One",
                "country": "NL",
            }
        ],
        "investors": [
            {
                "email_local": f"investor1-{tag}",
                "first_name": "Inv",
                "last_name": "One",
                "country": "NL",
            }
        ],
    }
    profile.update(overrides)
    return profile


def _investor_email(profile: dict[str, Any]) -> str:
    return seed._email(profile["investors"][0]["email_local"])


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
    db_session: Any, stand: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """comms absent: the seed completes, and emits no recipient events.

    The assertion is deliberately "zero", not "some": sync_recipient
    refuses to write an outbox row when there is no comms address,
    because the relay that would ship it is disabled by the same empty
    address and the row would grow the table forever without ever
    leaving it.

    THE STATE IS NOW PINNED HERE INSTEAD OF INHERITED. The docstring
    used to say "this is the state the test DB is in, and it is the
    state a laptop is in" -- true of a laptop, and true of the test DB
    only because nobody had pointed that box at comms. It made the
    result depend on the .env the run happened to pick up: the same
    code passed or failed by deployment. T-93 already moved the
    membership test off that footing (see the file header); this is the
    same move, applied to the emitter's other half.

    Same shape as the payments tests, which have never needed a
    configured stand: state built inside the test, not around it.
    """
    monkeypatch.setattr(seed_settings, "comms_api_url", "")

    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    # admin + support + investor until H37, when the seed stopped making
    # the admin: it acts as the stand's own, which carries no marker.
    assert len(users) == 2, "support + investor"

    ids = {str(u.id) for u in users}
    assert await _events(db_session, EVENT_USER_UPSERTED, ids) == 0


async def test_seed_defers_recipients_to_outbox_when_comms_is_unreachable(
    db_session: Any, monkeypatch: pytest.MonkeyPatch, stand: User
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
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    ids = {str(u.id) for u in users}
    assert await _events(db_session, EVENT_USER_UPSERTED, ids) == len(users)


async def test_every_seeded_staff_member_is_declared_to_the_section(
    db_session: Any, stand: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Membership is emitted for the seeded support staff.

    Until H37 the bootstrapped admin was seeded too and counted here; the
    seed now acts as the stand's own admin and makes none.

    The comms address is set here rather than assumed. Until T-93 this
    emitter wrote whatever the box was configured with, and the test
    passed for that reason rather than for the reason it states; now the
    gate is real, and the state the assertion needs is named.
    """
    monkeypatch.setattr(seed_settings, "comms_api_url", "http://comms.test")
    monkeypatch.setattr(seed_settings, "comms_service_token", "test-token")

    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    users = await _seeded_users(db_session, profile["marker"])
    staff_ids = {str(u.id) for u in users if u.role == UserRole.STAFF}
    assert len(staff_ids) == 1, "the one seeded operator"

    assert await _events(
        db_session, EVENT_SECTION_MEMBERSHIP_CHANGED, staff_ids
    ) == len(staff_ids)


# ---------------------------------------------------------------------------
# REPEAT -- a second run changes nothing
# ---------------------------------------------------------------------------


async def test_second_run_without_reset_is_a_no_op(
    db_session: Any, stand: User
) -> None:
    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()
    first = await _seeded_users(db_session, profile["marker"])

    await seed.seed_profile(db_session, profile)
    await db_session.flush()
    second = await _seeded_users(db_session, profile["marker"])

    assert {u.id for u in first} == {u.id for u in second}


async def test_seed_refuses_to_adopt_a_user_it_did_not_create(
    db_session: Any, stand: User
) -> None:
    """A live person at a seeded address is not taken over.

    Adoption would be worse than the collision it papers over: the row
    would acquire a marker, and the next --reset would delete a person
    the seed never made.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    investor_email = _investor_email(profile)
    user = await seed.find_user_by_email(db_session, investor_email)
    assert user is not None
    user.seeded_profile = None
    await db_session.flush()

    with pytest.raises(seed.SeedRefusedError):
        await seed.seed_profile(db_session, profile)


# ---------------------------------------------------------------------------
# EMPTY / SHORTAGE
# ---------------------------------------------------------------------------


async def test_retired_profile_keys_are_refused_by_name(
    no_admin: None,
) -> None:
    """A profile still carrying the keys H37 retired is refused, naming
    the key, before any write.

    Until H37 this test checked that a profile WITHOUT email_domain was
    refused: email_domain and demo_password were required then. Both are
    gone (the domain is the box's, passwords are random), and so are
    `admin` and the single `company`; a profile that still has one of
    them must not run with it silently ignored.
    """
    for key, value in (
        ("email_domain", "example.com"),
        ("demo_password", "x" * 12),
        ("admin", {"email_local": "admin"}),
        ("company", {"name": "Old"}),
    ):
        with pytest.raises(seed.SeedRefusedError) as excinfo:
            seed.validate_profile(_profile(**{key: value}))
        assert repr(key) in str(excinfo.value)


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


async def test_shipped_default_profile_passes_the_pre_write_checks(
    no_admin: None,
) -> None:
    """The profile the stand runs is valid as a whole, before any write:
    its texts, its project files, its configs against the services'
    validators. That it actually SEEDS is the next test's job
    (test_the_shipped_default_profile_seeds_resets_and_seeds_again)."""
    profile = seed.load_profile("default")
    assert profile["marker"] == "default"
    seed.validate_profile(profile)
    assert profile["companies"], "the storefront cannot be empty"
    assert not profile.get("staff"), "the default must run without --allow-live-staff"
    locals_ = [i["email_local"] for i in profile["investors"]]
    assert locals_ == ["test01", "test02", "test03", "test04", "test05"]


# ---------------------------------------------------------------------------
# The live-staff refusal
# ---------------------------------------------------------------------------


async def test_refuses_when_active_staff_are_not_this_profiles(
    db_session: Any, stand: User
) -> None:
    """Declaring seeded operators can silence live ones -- so it refuses.

    The guard is local on purpose: whether the live staff are declared
    in the comms roster is not answerable from here (the outbox payload
    that would say so is redacted after seven days), so the seed asks a
    question it CAN answer and errs towards refusing.
    """
    other = _profile()
    await seed.seed_profile(db_session, other)
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
    db_session: Any, stand: User
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
    await seed.seed_profile(db_session, profile)
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
    db_session: Any, stand: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row that says "no longer an operator" is written, not skipped.

    Without it comms keeps a roster of operators that no longer exist,
    and because a section with ANY declared member is served only by
    those members, a reset that deleted the only declared ones would
    leave the section served by nobody at all.

    THE ADDRESS IS SET HERE, AND UNTIL NOW IT WAS NOT. emit_support_
    membership is gated on comms_configured(), so this assertion only
    held on a box that happened to have an address configured -- and a
    box WITHOUT one is a supported configuration, not a
    misconfiguration (config.py:395-403 gates its validator on comms
    being intended for that box at all). So the red this test produced
    on such a box was never a report about the deployment: it said
    "membership is not being emitted" when the truth was "this box is
    set up one of the two allowed ways". It should not have gone red
    there.

    It also went red UNREADABLY -- `assert 0 == 0 + 2`, which reads as
    a broken roster rather than as an unset variable, and cost a whole
    pass chasing it as a delivery defect.

    upsert_recipient is stubbed to succeed rather than left alone: with
    an address set and no stub, the seed's recipient path would open a
    real socket to a hostname that does not exist. The product's own
    branch is untouched -- only the wire is fake, which is the shape
    test_crypto_invoices.py:160 uses for payments.
    """
    monkeypatch.setattr(seed_settings, "comms_api_url", "http://comms.test")
    monkeypatch.setattr(seed_settings, "comms_service_token", "test-token")
    monkeypatch.setattr(_comms_sync(), "upsert_recipient", _always_succeed)

    profile = _profile()
    await seed.seed_profile(db_session, profile)
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
    db_session: Any, stand: User
) -> None:
    mine = _profile()
    theirs = _profile()
    await seed.seed_profile(db_session, mine)
    await seed.seed_profile(db_session, theirs)
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
    db_session: Any, stand: User
) -> None:
    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    investor_email = _investor_email(profile)
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
    db_session: Any, stand: User
) -> None:
    """A seeded person can actually sign in and use the product.

    register_email leaves REGISTERED / NOT_STARTED, and the frontend
    guards send anyone short of ONBOARDING_COMPLETE back into the
    funnel. The scripts this replaced solved that by writing the two
    columns by hand; this one walks the steps.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    user = await seed.find_user_by_email(
        db_session, _investor_email(profile)
    )
    assert user is not None
    assert user.onboarding_step == OnboardingStep.ONBOARDING_COMPLETE
    assert user.credentials["email"]["verified"] is True


async def test_the_seed_acts_as_the_stands_admin_and_mints_none(
    db_session: Any, stand: User
) -> None:
    """Every seeded row is made with the stand's admin as the actor, and
    no seeded user becomes an admin.

    Until H37 this test said "an existing admin is reused and no second
    one is minted": the seed then bootstrapped an admin when the stand
    had none. It no longer can (the next test), so the property left is
    the stronger one -- the seed never makes an admin at all.
    """
    profile = _profile()
    await seed.seed_profile(db_session, profile)
    await db_session.flush()

    seeded_ids = {u.id for u in await _seeded_users(db_session, profile["marker"])}
    assert stand.id not in seeded_ids
    admins = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id.in_(seeded_ids))
        )
    ).scalars().all()
    assert all(not all(p.permissions.values()) for p in admins), (
        "a seeded staff member holds every permission -- the seed made an admin"
    )


async def test_a_stand_without_an_admin_is_refused_before_any_write(
    db_session: Any, no_admin: None
) -> None:
    """No active admin -> refused, naming `aivis bootstrap-admin`, with
    not one row written.

    Replaces test_the_bootstrapped_admin_has_every_permission, which
    checked the admin the seed used to bootstrap on such a stand (right
    while the seed was a path to the first admin; H37 removed that path,
    the first admin comes only from `aivis bootstrap-admin`).
    """
    profile = _profile()
    with pytest.raises(seed.SeedRefusedError) as excinfo:
        await seed.seed_profile(db_session, profile)
    assert "aivis bootstrap-admin" in str(excinfo.value)
    assert await _seeded_users(db_session, profile["marker"]) == []


# ---------------------------------------------------------------------------
# H37: projects, files, passwords, domain
# ---------------------------------------------------------------------------
#
# Axes:
#   REPEAT    -- the shipped profile seeded twice: no new row, no new object;
#                every account's password different from every other
#   EMPTINESS -- a profile without staff on a stand with a live admin; a
#                project without files; a reset whose objects are gone
#   SHORTAGE  -- a missing file, a refused type, an oversized logo, no "en",
#                an invalid distribution_config, a package bigger than the
#                pool, a host that carries no mail: refused before any row
#                or object; a delete_object failure at reset is a warning
#
# These talk to the real storage of the test environment (RustFS), like
# test_project_media.py: the seed uploads through the services.

_DEMO_DIR = Path(seed.__file__).resolve().parent / "templates" / "projects" / "demo"


async def _objects(prefix: str = "companies/") -> set[str]:
    from app.core.storage import list_objects

    return set(await list_objects(prefix))


async def _company_of(db_session: Any, marker: str) -> Any:
    from app.modules.companies.models import CompanyProfile

    stmt = (
        select(CompanyProfile)
        .join(User, User.id == CompanyProfile.user_id)
        .where(User.seeded_profile == marker)
    )
    return (await db_session.execute(stmt)).scalars().all()


def _demo_project(**overrides: Any) -> dict[str, Any]:
    """The shipped demo project entry, for a profile of the test's own."""
    shipped = json.loads(
        (seed.PROFILES_DIR / "default.json").read_text(encoding="utf-8")
    )
    project = copy.deepcopy(shipped["companies"][0])
    project["email_local"] = f"demo-{uuid.uuid4().hex[:8]}"
    project.update(overrides)
    return project


async def test_the_shipped_default_profile_seeds_resets_and_seeds_again(
    db_session: Any, stand: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The profile the stand runs, seeded WHOLE: project, files, investors.

    Until H37 this was refused on principle -- "parsing only -- seeding it
    here would put its fixed e-mail addresses into the shared test
    database and collide with the next run". That was right while the
    domain was written in the profile: every run would have created the
    same <local>@example.com addresses. H37 moved the domain to
    FRONTEND_BASE_URL, so a test pins a host of its own and the shipped
    addresses no longer collide; the marker is the test's own for the same
    reason.

    And the refusal cost exactly what this test exists for: the shipped
    profile could never seed (company_pct 1.0 refused by create_company,
    and ensure_pool tripped on get_active_pool raising), and nothing
    noticed for two months because nothing ran it.

    H38 changed two of its numbers, by design: the shipped project now
    carries media/ru/cover.png, so the run uploads one language variant
    and the project's prefix holds eight objects, not seven; and the
    Russian texts of the profile, which H37 dropped, are now in the rows'
    translations. Asserted here as exact values, not loosened.
    """
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(
        seed_settings, "frontend_base_url", f"https://{tag}.{SEED_HOST}"
    )
    profile = seed.load_profile("default")
    profile["marker"] = f"pytest_default_{tag}"

    stats = await seed.seed_profile(db_session, profile)
    await db_session.commit()
    assert stats["companies"] == 1
    assert stats["investors"] == 5
    assert stats["purchases"] > 0
    assert stats["pictures"] == 3
    assert stats["attachments"] == 1
    assert stats["roadmap_items"] == 2
    assert stats["picture_variants"] == 1

    (company,) = await _company_of(db_session, profile["marker"])
    prefix = f"companies/{company.id}/"
    assert company.logo_storage_key and company.logo_dark_storage_key
    assert company.cover_storage_key
    objects = await _objects(prefix)
    # logo, dark logo, cover, its Russian variant, product cover, the
    # deck, two roadmap covers
    assert len(objects) == 8
    assert {company.logo_storage_key, company.cover_storage_key} <= objects
    ru_cover = company.media_variants["ru"]["cover"]
    assert ru_cover == f"{prefix}media/ru/cover.png" and ru_cover in objects
    assert company.name == "Demo Project"
    assert company.translations["ru"]["name"] == "Демо-проект"

    from app.modules.companies.models import CompanyAttachment, CompanyRoadmapItem
    from app.modules.products.models import Product, ProductInstallment

    products = (
        await db_session.execute(select(Product).where(Product.company_id == company.id))
    ).scalars().all()
    assert sorted(p.name for p in products) == ["Growth package", "Starter package"]
    assert sorted(p.translations["ru"]["name"] for p in products) == [
        "Пакет роста",
        "Стартовый пакет",
    ]
    assert all(p.status == "active" for p in products)
    installments = (
        await db_session.execute(
            select(ProductInstallment).where(
                ProductInstallment.product_id.in_([p.id for p in products])
            )
        )
    ).scalars().all()
    assert [i.name for i in installments] == ["Two payments"]
    items = (
        await db_session.execute(
            select(CompanyRoadmapItem).where(CompanyRoadmapItem.company_id == company.id)
        )
    ).scalars().all()
    assert all(i.cover_storage_key for i in items) and len(items) == 2

    # REPEAT: the second run writes nothing.
    again = await seed.seed_profile(db_session, profile)
    await db_session.commit()
    for key in (
        "pictures", "picture_variants", "attachments", "roadmap_items", "purchases"
    ):
        assert again[key] == 0, key
    assert await _objects(prefix) == objects
    count = (
        await db_session.execute(
            select(func.count()).select_from(CompanyAttachment).where(
                CompanyAttachment.company_id == company.id
            )
        )
    ).scalar_one()
    assert count == 1

    # Reset: the rows, then -- after the commit -- the objects.
    ids = await seed.seeded_company_ids(db_session, profile["marker"])
    assert ids == [company.id]
    counts = await seed.reset_seed_data(db_session, profile["marker"])
    await db_session.commit()
    assert counts["attachments"] == 1 and counts["roadmap_items"] == 2
    assert counts["users"] == 6
    purged = await seed.purge_seeded_objects(ids)
    assert purged == {"objects": 8, "failed": 0}
    assert await _objects(prefix) == set()
    assert await _seeded_users(db_session, profile["marker"]) == []


async def test_every_seeded_account_has_its_own_password_and_none_is_shown(
    db_session: Any,
    stand: User,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """REPEAT: each account's password is drawn for it alone, it is the
    one its hash verifies, and it appears in no output and no log."""
    from app.modules.auth.service import verify_password

    drawn: list[str] = []
    real = seed._random_password

    def _spy() -> str:
        value = real()
        drawn.append(value)
        return value

    monkeypatch.setattr(seed, "_random_password", _spy)
    profile = _profile(
        staff=[],
        companies=[_demo_project()],
        investors=[
            {"email_local": f"pw{i}-{uuid.uuid4().hex[:6]}", "first_name": "P"}
            for i in range(3)
        ],
    )
    drawn.clear()
    await seed.seed_profile(db_session, profile)
    await db_session.commit()

    users = await _seeded_users(db_session, profile["marker"])
    assert len(users) == 4, "three investors and the project's owner"
    assert len(set(drawn)) == len(drawn) >= 4
    hashes = [u.credentials["email"]["password_hash"] for u in users]
    for user_hash in hashes:
        assert sum([await verify_password(p, user_hash) for p in drawn]) == 1

    shown = capsys.readouterr()
    logged = caplog.text
    for password in drawn:
        assert password not in shown.out
        assert password not in shown.err
        assert password not in logged


async def test_a_profile_without_staff_runs_beside_a_live_admin(
    stand: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """EMPTINESS: no staff[] -> no live-staff check, no flag needed. With
    staff[], the same stand refuses, and says the admin is staff too."""
    monkeypatch.setattr(seed, "PROFILES_DIR", tmp_path)
    plain = _profile(staff=[])
    (tmp_path / "plain.json").write_text(json.dumps(plain), encoding="utf-8")
    with_staff = _profile()
    (tmp_path / "staffed.json").write_text(json.dumps(with_staff), encoding="utf-8")

    def _args(name: str) -> argparse.Namespace:
        return argparse.Namespace(
            profile=name, reset=False, reset_only=False, dry_run=False,
            allow_live_staff=False,
        )

    assert await seed._run_profile(_args("plain")) == 0
    capsys.readouterr()
    assert await seed._run_profile(_args("staffed")) == 2
    message = capsys.readouterr().out
    assert "--allow-live-staff" in message
    assert "admin is staff too" in message


@pytest.mark.parametrize(
    "breakage, needle",
    [
        ("missing_file", "no file at"),
        ("attachment_type", "attachments[0]"),
        ("big_logo", "over the 1048576-byte limit"),
        ("no_en", '.name has no "en" text'),
        ("ru_only_string", "must be a dictionary of languages"),
        ("distribution", "distribution_config"),
        ("package_over_pool", "exceeds the pool's"),
        ("outside_folder", "leaves the project folder"),
        ("bad_installment", "installments[0]"),
    ],
)
async def test_a_bad_project_is_refused_before_any_row_or_object(
    db_session: Any,
    stand: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    breakage: str,
    needle: str,
) -> None:
    """SHORTAGE: every refusal a project can earn comes from
    validate_profile, before the first write -- no seeded row, no new
    object. A refusal mid-run would leave uploaded objects behind (the
    KNOWN CEILING in seed_profile)."""
    root = tmp_path / "projects"
    shutil.copytree(_DEMO_DIR, root / "demo")
    monkeypatch.setattr(seed, "PROJECTS_DIR", root)
    project = _demo_project()

    if breakage == "missing_file":
        (root / "demo" / "media" / "cover.png").unlink()
    elif breakage == "attachment_type":
        (root / "demo" / "documents" / "en" / "evil.exe").write_bytes(b"MZ")
        project["attachments"][0]["file"] = "documents/en/evil.exe"
    elif breakage == "big_logo":
        big = root / "demo" / "media" / "logo.png"
        big.write_bytes(big.read_bytes() + b"\0" * (1024 * 1024))
    elif breakage == "no_en":
        project["name"] = {"ru": "Только по-русски"}
    elif breakage == "ru_only_string":
        project["name"] = "Demo"
    elif breakage == "distribution":
        project["distribution_config"] = {"company_pct": 1.0, "agent_levels": []}
    elif breakage == "package_over_pool":
        project["products"][0]["package_size"] = 10_000_000
    elif breakage == "outside_folder":
        project["cover"] = "../../escape.png"
    elif breakage == "bad_installment":
        project["products"][1]["installments"][0]["plan_config"]["tranches"][0][
            "amount_cents"
        ] = 1

    profile = _profile(staff=[], companies=[project])
    before = await _objects()
    with pytest.raises(seed.SeedRefusedError) as excinfo:
        await seed.seed_profile(db_session, profile)
    assert needle in str(excinfo.value)
    assert await _seeded_users(db_session, profile["marker"]) == []
    assert await _objects() == before


async def test_investor_entries_are_checked_before_any_write(
    db_session: Any, stand: User
) -> None:
    """SHORTAGE: an unknown agent key and a negative deposit are refused
    by validate_profile, not half-way through the run."""
    tag = uuid.uuid4().hex[:6]
    for investor, needle in (
        ({"email_local": f"r-{tag}", "referred_by_agent": "ghost"}, "names no agent"),
        (
            {"email_local": f"d-{tag}", "portfolio": {"deposit_cents": -1}},
            "deposit_cents must be a whole number",
        ),
    ):
        profile = _profile(staff=[], investors=[investor])
        with pytest.raises(seed.SeedRefusedError) as excinfo:
            await seed.seed_profile(db_session, profile)
        assert needle in str(excinfo.value)
        assert await _seeded_users(db_session, profile["marker"]) == []


@pytest.mark.parametrize(
    "address", ["http://localhost:5173", "https://127.0.0.1", "https://[::1]:8080", ""]
)
async def test_a_host_that_carries_no_mail_is_refused(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    """SHORTAGE: the seeded addresses are <local>@<host of FRONTEND_BASE_URL>;
    a host without a dot or an IP refuses, naming the setting."""
    monkeypatch.setattr(seed_settings, "frontend_base_url", address)
    with pytest.raises(seed.SeedRefusedError) as excinfo:
        seed.validate_profile(_profile(staff=[]))
    assert "FRONTEND_BASE_URL" in str(excinfo.value)


async def test_a_reset_survives_an_object_it_cannot_delete(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SHORTAGE at the end: the rows are gone; a storage failure leaves an
    orphan and a warning, not a failed reset."""
    from app.core.storage import upload_object

    company_id = uuid.uuid4()
    key = f"companies/{company_id}/media/logo.png"
    await upload_object(key, b"x", "image/png")

    async def _refuse(_key: str) -> None:
        raise seed.StorageError("delete refused")

    monkeypatch.setattr(seed, "delete_object", _refuse)
    stats = await seed.purge_seeded_objects([company_id])
    assert stats == {"objects": 0, "failed": 1}
    assert "could not delete" in capsys.readouterr().out
    monkeypatch.undo()
    assert await seed.purge_seeded_objects([company_id]) == {"objects": 1, "failed": 0}


async def test_two_roadmap_items_with_one_title_are_not_guessed_between(
    db_session: Any, stand: User
) -> None:
    """A second item with the seeded title, made by hand, makes the next
    run refuse rather than pick one."""
    from app.modules.companies.service import create_roadmap_item

    profile = _profile(staff=[], companies=[_demo_project()])
    await seed.seed_profile(db_session, profile)
    await db_session.commit()
    (company,) = await _company_of(db_session, profile["marker"])
    await create_roadmap_item(company.id, "Platform launch", stand, db_session)
    await db_session.flush()

    with pytest.raises(seed.SeedRefusedError) as excinfo:
        await seed.seed_profile(db_session, profile)
    assert "Platform launch" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Local helpers that need the module under test imported first
# ---------------------------------------------------------------------------


def _comms_sync() -> Any:
    from app.core import comms_sync

    return comms_sync


async def _always_fail(*_args: Any, **_kwargs: Any) -> UpsertOutcome:
    # UNDELIVERED is the outcome that sends sync_recipient to the outbox
    # (comms unreachable); the other two refusals, by design, do not.
    return UpsertOutcome.UNDELIVERED


async def _always_succeed(*_args: Any, **_kwargs: Any) -> bool:
    """A comms that answers. Returns what the real upsert returns on a
    successful PUT -- True -- so sync_recipient takes its synchronous
    branch and writes no outbox row."""
    return True
