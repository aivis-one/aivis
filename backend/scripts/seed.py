#!/usr/bin/env python3
# =============================================================================
# AIVIS.ONE Backend -- Profile-driven database seed (T-72)
# =============================================================================
#
# USAGE (through the management command, which carries the contour gate):
#   aivis seed                          -- seed from the default profile
#   aivis seed --profile default        -- seed from a named profile
#   aivis seed --reset                  -- wipe seeded data, then seed
#   aivis seed --list                   -- list available profiles
#   aivis seed-portfolio <email>        -- fill one live user's dashboard
#
# DIRECTLY (inside the app container):
#   python scripts/seed.py [--profile NAME] [--reset] [--reset-only]
#                          [--list] [--dry-run] [--allow-live-staff]
#   python scripts/seed.py --portfolio-for EMAIL [--deposit N] [--purchases N]
#
# -----------------------------------------------------------------------------
# WHY THIS REPLACED FOUR SCRIPTS
#
# seed_test_accounts.py, seed_storefront.py, seed_user_portfolio.py and
# seed_admin.py all wrote users, staff profiles or company owners with
# bare ORM: `User(...)` plus `session.add`. That is invisible to half the
# product. A user created that way gets no recipient in comms (T-64), so
# nothing this product ever sends them arrives; a staff profile created
# that way emits no membership event (T-67), so the person does not serve
# the support queue. Every one of those scripts also had to hand-set
# onboarding_step and kyc_status, because it had skipped the funnel that
# sets them -- and each hand-set them slightly differently, which is how
# seed_admin.py and seed_test_accounts.py ended up disagreeing about
# which step a seeded staff member should start on.
#
# So this script keeps one rule and drops everything else:
# EVERY ROW IS CREATED THROUGH THE PATH THE APPLICATION ITSELF USES.
#
#   users        -> auth.service.register_email        (recipient free)
#   e-mail       -> auth.service.verify_email_code
#   profile      -> users.service.update_user
#   role         -> users.service.select_role
#   kyc          -> kyc.service.submit_kyc + process_webhook
#   documents    -> documents.service.sign_document
#   staff        -> staff.service.create_staff         (membership free)
#   agents       -> agent_applications submit + approve
#   companies    -> companies.service.create_company   (recipient free)
#   pools        -> pools.service.create_pool
#   products     -> products.service.create_product
#   money        -> ledgers.service.record_active_ledger
#   purchases    -> purchases.service.execute_purchase
#
# process_webhook deserves a note, because it looks like a back door and
# is not one: KYC approval arrives from SumSub as a webhook, the
# signature check lives in the router, and the service function below it
# takes (user_id, status, session) like any other. The seed calls the
# service, exactly as the router does after it has checked the signature.
# Nothing here writes kyc_status by hand.
#
# -----------------------------------------------------------------------------
# THE ONE BYPASS: THE FIRST ADMIN
#
# create_staff(target_user_id, admin, session) promotes an existing user
# and takes an admin as the actor. On a stand with no admin there is
# nobody to be that actor, so the first one cannot be made through the
# path -- chicken and egg, not an oversight. The bypass is therefore as
# narrow as it can be: the admin's USER goes through the full ladder like
# everybody else, and only the promotion is written by hand -- the role
# flip, the StaffProfile row, and the membership event, which are the
# three things create_staff does internally. Every later staff member
# goes through create_staff with this admin as the actor.
#
# The admin signs in with the profile's demo_password like everybody
# else. This repository is the TEST server's, the seed refuses to run on
# a production contour, and there is no production stand to protect --
# so a separate secret for the admin would buy nothing and cost a
# prompt, an environment variable and two code paths. It had all three
# for a while; owner ruling: do not complicate for imagined safety.
#
# -----------------------------------------------------------------------------
# PROFILES
#
# A profile is one JSON file in scripts/seed_profiles/. It describes WHAT
# to seed; this file describes HOW. Adding a demo means adding a JSON
# file, not editing Python.
#
# NO RELATIVE DATES, AND THIS IS DELIBERATE. The reference implementation
# carries day_offset because its profiles seed practices, whose start
# time the caller chooses; a profile pinned to absolute dates there shows
# an empty screen a week later. Nothing this profile seeds takes a
# caller-chosen date through its application path -- companies, pools,
# products, installment templates, ledger entries and purchases are all
# stamped now() by the service that writes them. A day_offset field here
# would have no consumer, and a seed that backdated rows behind the
# services' backs would be exactly the hand-writing this file exists to
# end. If a dated entity appears later, the field arrives with it.
#
# -----------------------------------------------------------------------------
# LIVE PEOPLE ARE NEVER TOUCHED BY --reset
#
# Every row this script creates carries users.seeded_profile = the
# profile name (migration 0044). --reset deletes by that marker and by
# nothing else: no e-mail domain, no name prefix, no id range. A person
# who registered at the demo domain by hand has a NULL marker and
# survives.
#
# Deletion is written out table by table rather than left to the
# database, because 26 of the 30 foreign keys into `users` are ON DELETE
# RESTRICT. That is a feature here: a table this function forgets makes
# --reset fail loudly with the constraint name instead of leaving
# half-deleted residue nobody notices.
#
# -----------------------------------------------------------------------------
# THE LIVE-STAFF REFUSAL
#
# Declaring an operator for the support section is not additive. comms
# serves a section with NO declared members from every operator; the
# moment ONE member is declared, everybody else stops serving it (see
# support.service.emit_support_membership). So seeding support staff onto
# a stand that already has live staff can silently take those live people
# off the queue.
#
# Whether the live ones are already declared is not a question this
# product can answer: the roster lives in comms, and the only local trace
# -- the section_membership_changed row in the outbox -- carries the
# operator id inside its payload, which is redacted seven days after
# publication (PAYLOAD_RETENTION_DAYS). On any stand older than a week
# the honest answer is "unknown".
#
# So the seed does not ask the question it cannot answer. It asks a local
# one -- "is there an ACTIVE staff profile that is not mine" -- and
# refuses the whole run when there is, before writing anything, naming
# the consequence and the two ways out. That refusal fires on healthy
# stands too, where the live staff happen to be declared and no harm
# would follow. That false positive is the price of not guessing;
# --allow-live-staff is how a human says they know better.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

# -- sys.path bootstrap (same shape as the scripts this file replaces) -------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
for _p in (_SCRIPTS_DIR, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import structlog  # noqa: E402
from fastapi import BackgroundTasks  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.database import dispose_engine, get_session_factory  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.modules.agent_applications.models import AgentApplication  # noqa: E402
from app.modules.agent_applications.service import (  # noqa: E402
    submit_application,
)
from app.modules.agent_applications.staff_service import (  # noqa: E402
    agent_application_approve,
)
from app.modules.auth.service import (  # noqa: E402
    register_email,
    verify_email_code,
)
from app.modules.companies.constants import CompanyStatus  # noqa: E402
from app.modules.companies.models import (  # noqa: E402
    CompanyPriceHistory,
    CompanyProfile,
)
from app.modules.companies.schemas import (  # noqa: E402
    CreateCompanyRequest,
    UpdateCompanyRequest,
)
from app.modules.companies.service import (  # noqa: E402
    create_company,
    update_company,
)
from app.modules.documents.models import (  # noqa: E402
    Document,
    DocumentSigning,
    DocumentStatus,
)
from app.modules.documents.service import sign_document  # noqa: E402
from app.modules.kyc.models import KYCApplication  # noqa: E402
from app.modules.kyc.service import process_webhook, submit_kyc  # noqa: E402
from app.modules.ledgers.models import (  # noqa: E402
    ActiveLedger,
    LedgerStatus,
    PassiveLedger,
)
from app.modules.ledgers.service import (  # noqa: E402
    get_active_balance,
    record_active_ledger,
)
from app.modules.pools.models import OptionPool  # noqa: E402
from app.modules.pools.schemas import CreatePoolRequest  # noqa: E402
from app.modules.pools.service import create_pool, get_active_pool  # noqa: E402
from app.modules.products.constants import ProductStatus  # noqa: E402
from app.modules.products.models import Product, ProductInstallment  # noqa: E402
from app.modules.products.service import (  # noqa: E402
    create_product,
    update_product_status,
)
from app.modules.purchases.models import Purchase  # noqa: E402
from app.modules.purchases.service import execute_purchase  # noqa: E402
from app.modules.referrals.models import (  # noqa: E402
    ReferralAttribution,
    ReferralLink,
)
from app.modules.referrals.service import create_link  # noqa: E402
from app.modules.staff.constants import VALID_PERMISSION_KEYS, is_admin  # noqa: E402
from app.modules.staff.models import StaffProfile  # noqa: E402
from app.modules.staff.service import create_staff  # noqa: E402
from app.modules.support.service import emit_support_membership  # noqa: E402
from app.modules.transactions.models import Transaction  # noqa: E402
from app.modules.users.models import (  # noqa: E402
    KYCStatus,
    OnboardingStep,
    User,
    UserRole,
)
from app.modules.users.schemas import UserUpdate  # noqa: E402
from app.modules.users.service import select_role, update_user  # noqa: E402

logger = structlog.get_logger()

PROFILES_DIR = _SCRIPTS_DIR / "seed_profiles"

# The seed acts as a person would; sign_document records where from.
_SEED_IP = "127.0.0.1"
_SEED_USER_AGENT = "aivis-seed"

# -- Console output (palette shared with the scripts this file replaces) -----
C = "\033[0;36m"
Y = "\033[1;33m"
G = "\033[0;32m"
R = "\033[0;31m"
N = "\033[0m"


def info(msg: str) -> None:
    print(f"{C}[SEED]{N} {msg}")


def ok(msg: str) -> None:
    print(f"{G}[SEED]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


class SeedRefusedError(Exception):
    """The run stops before writing anything. Carries the reason."""


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def list_profiles() -> list[str]:
    """Names of the profiles on disk, without the .json suffix."""
    if not PROFILES_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def load_profile(name: str) -> dict[str, Any]:
    """Read one profile and check the keys this file dereferences.

    The check is deliberately shallow -- presence and type of the top
    level only. A profile that is missing a section gets a message
    naming the section; a profile that is malformed deeper down fails
    at the service that rejects it, which gives a better message than
    anything this function could invent.
    """
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        available = ", ".join(list_profiles()) or "(none)"
        raise SeedRefusedError(
            f"No profile named {name!r} in {PROFILES_DIR}. Available: "
            f"{available}"
        )

    with path.open(encoding="utf-8") as handle:
        profile: dict[str, Any] = json.load(handle)

    for key in ("email_domain", "demo_password"):
        if not profile.get(key):
            raise SeedRefusedError(f"Profile {name!r} has no {key!r}")

    # The marker written into users.seeded_profile. Defaults to the file
    # name so a profile cannot silently share another profile's rows.
    profile.setdefault("marker", name)
    return profile


def _email(profile: dict[str, Any], local: str) -> str:
    return f"{local}@{profile['email_domain']}".lower()


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


async def assert_no_live_staff(
    session: AsyncSession, marker: str, *, allow_live_staff: bool
) -> None:
    """Refuse the run if somebody else's staff are on duty.

    See the header: declaring seeded operators can take live, possibly
    undeclared ones off the support queue, and this product cannot check
    whether they are declared. `IS DISTINCT FROM` rather than `IS NOT
    NULL` -- a profile seeded by a DIFFERENT profile is not ours either.
    """
    stmt = (
        select(User.id)
        .join(StaffProfile, StaffProfile.user_id == User.id)
        .where(
            StaffProfile.is_active.is_(True),
            User.seeded_profile.is_distinct_from(marker),
        )
        .limit(5)
    )
    foreign = list((await session.execute(stmt)).scalars())
    if not foreign:
        return

    if allow_live_staff:
        warn(
            f"{len(foreign)} active staff profile(s) are not mine; "
            f"--allow-live-staff was passed, continuing"
        )
        return

    raise SeedRefusedError(
        "This stand has active staff profiles that this seed did not "
        "create (for example "
        + ", ".join(str(i) for i in foreign[:3])
        + "). Declaring seeded operators for the support section would "
        "stop every operator that is NOT declared from serving that "
        "section -- and whether these are declared is a fact that lives "
        "in comms, not here, so it cannot be checked. Nothing has been "
        "written. Either re-run with --allow-live-staff if you know "
        "those people are declared (or that this stand is yours to "
        "change), or clear the stand first."
    )


# ---------------------------------------------------------------------------
# Users -- the ladder
# ---------------------------------------------------------------------------


async def find_user_by_email(
    session: AsyncSession, email: str
) -> User | None:
    """Look a user up the way the login path does."""
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email.lower()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _sign_required_documents(
    session: AsyncSession, user: User
) -> int:
    """Sign every active document this user's role requires.

    Signing is what moves KYC_DONE to ONBOARDING_COMPLETE for roles that
    have required documents; roles with none are already there via the
    cascade inside submit_kyc. Documents the user has signed already are
    skipped rather than re-signed -- sign_document raises ConflictError
    on a second signature, and a seed re-run must be a no-op.
    """
    required_stmt = select(Document.id, Document.type).where(
        Document.status == DocumentStatus.ACTIVE,
        Document.required_for_roles.contains([user.role]),
    )
    required = list((await session.execute(required_stmt)).all())
    if not required:
        return 0

    signed_stmt = select(DocumentSigning.document_id).where(
        DocumentSigning.user_id == user.id
    )
    already = set((await session.execute(signed_stmt)).scalars())

    # One signature per TYPE is what maybe_complete_onboarding counts,
    # so signing one language of each type is enough and signing all of
    # them would only add rows nobody reads.
    seen_types: set[str] = set()
    signed = 0
    for document_id, doc_type in required:
        if doc_type in seen_types:
            continue
        if document_id in already:
            seen_types.add(doc_type)
            continue
        await sign_document(
            user.id, document_id, _SEED_IP, _SEED_USER_AGENT, session
        )
        seen_types.add(doc_type)
        signed += 1
    return signed


async def walk_onboarding(
    session: AsyncSession, user: User, *, role: str, marker: str
) -> User:
    """Take a freshly created user to ONBOARDING_COMPLETE, step by step.

    Every step is gated on the state it would change, so this is safe to
    call on a user who is already half-way (or all the way) through --
    which is what makes a second seed run a no-op and what lets a run
    that died mid-profile be finished by re-running it.

    The entry point differs by role and that is fine: a user made by
    register_email starts at REGISTERED, a company owner made by
    create_company starts at ROLE_SELECTED with no e-mail token at all.
    """
    credentials = user.credentials or {}
    email_creds = credentials.get("email", {})
    onboarding = credentials.get("onboarding", {})
    token = onboarding.get("email_token")

    if token and not email_creds.get("verified"):
        await verify_email_code(user, token, session)

    if user.onboarding_step == OnboardingStep.EMAIL_VERIFIED:
        await update_user(
            user,
            UserUpdate(
                profile={
                    "first_name": user.profile.get("first_name") or "Seed",
                    "last_name": user.profile.get("last_name") or "User",
                    "country": user.profile.get("country") or "NL",
                }
            ),
            session,
        )

    if user.onboarding_step == OnboardingStep.PROFILE_COMPLETE:
        await select_role(user, role, session)

    if user.kyc_status == KYCStatus.NOT_STARTED:
        await submit_kyc(user, session)

    if user.kyc_status == KYCStatus.SUBMITTED:
        await process_webhook(user.id, "approved", session)
        await session.refresh(user)

    await _sign_required_documents(session, user)

    user.seeded_profile = marker
    await session.flush()
    await session.refresh(user)
    return user


async def ensure_user(
    session: AsyncSession,
    profile: dict[str, Any],
    spec: dict[str, Any],
    *,
    role: str,
    referral_code: str | None = None,
) -> User:
    """Create one person through registration, or return the seeded one.

    A user who exists at this address but carries somebody else's marker
    (or none) is NOT adopted: the seed refuses rather than take over a
    row it did not make. Adoption would mean a later --reset deleting a
    person the seed never created.
    """
    marker = profile["marker"]
    email = _email(profile, spec["email_local"])

    existing = await find_user_by_email(session, email)
    if existing is not None:
        if existing.seeded_profile != marker:
            raise SeedRefusedError(
                f"{email} already exists and was not created by profile "
                f"{marker!r} (marker: {existing.seeded_profile!r}). The "
                f"seed does not take over rows it did not make. Pick "
                f"another e-mail domain in the profile, or clear that "
                f"user by hand."
            )
        # Idempotent path: finish any step a previous run left undone.
        return await walk_onboarding(
            session, existing, role=role, marker=marker
        )

    user = await register_email(
        email,
        profile["demo_password"],
        session,
        BackgroundTasks(),
        referral_code=referral_code,
    )
    # register_email schedules the verification e-mail on the
    # BackgroundTasks object above. Nothing ever runs it: FastAPI runs
    # background tasks after a response, and there is no response here.
    # The task dies with the object and no mail leaves the box.

    user.profile = {
        "first_name": spec.get("first_name", "Seed"),
        "last_name": spec.get("last_name", "User"),
        "country": spec.get("country", "NL"),
    }
    user.language = spec.get("language", "en")
    await session.flush()

    return await walk_onboarding(session, user, role=role, marker=marker)


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


async def _find_any_admin(session: AsyncSession) -> User | None:
    """The first active admin on this stand, or None.

    is_admin() is a permission-set predicate, not a column, so this
    reads the profiles rather than filtering in SQL.
    """
    stmt = (
        select(StaffProfile, User)
        .join(User, User.id == StaffProfile.user_id)
        .where(StaffProfile.is_active.is_(True))
    )
    for staff_profile, user in (await session.execute(stmt)).all():
        if is_admin(staff_profile.permissions):
            return user
    return None


async def ensure_admin(
    session: AsyncSession, profile: dict[str, Any]
) -> User:
    """Return the admin every later call uses as its actor.

    An admin that already exists is used as-is -- the seed does not mint
    a second administrator on a stand that has one. Only when there is
    none does the bypass described in the header run.
    """
    existing = await _find_any_admin(session)
    if existing is not None:
        info(f"Using the existing admin as actor: {existing.id}")
        return existing

    spec = profile.get("admin")
    if not spec:
        raise SeedRefusedError(
            "This stand has no admin and the profile declares none, so "
            "there is nobody to create staff, companies or products."
        )

    user = await ensure_user(session, profile, spec, role=UserRole.INVESTOR)

    # -- THE BYPASS. Three writes, and they are the three create_staff
    # makes internally: the role, the profile row, and the membership
    # event. The user above came through the ordinary ladder, so the
    # comms recipient is already there and is NOT part of this.
    #
    # GATED ON THE ROW IT WOULD WRITE, like every other step in this
    # file. Reaching here does NOT prove there is no staff profile for
    # this person: _find_any_admin answers "is there an ACTIVE profile
    # whose permissions are all True", and a profile that is inactive,
    # or that an operator has since taken a permission away from, makes
    # it say None while staff_profiles.user_id -- which is UNIQUE --
    # still holds a row. Without this check the insert dies on
    # uq_staff_profiles_user_id and takes the whole run with it.
    existing_profile = (
        await session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    if existing_profile is not None:
        # Already promoted by an earlier run. The permissions are left
        # exactly as they are: this function's job is to produce an
        # actor, not to restore rights somebody may have removed on
        # purpose. The membership event is not re-emitted either -- the
        # first promotion already sent it, and a second one would make
        # a repeat run write to the outbox, which is precisely what
        # "a second run is a no-op" forbids.
        user.role = UserRole.STAFF
        await session.flush()
        await session.refresh(user)
        return user

    user.role = UserRole.STAFF
    staff_profile = StaffProfile(
        user_id=user.id,
        permissions={key: True for key in VALID_PERMISSION_KEYS},
        is_active=True,
    )
    session.add(staff_profile)
    await session.flush()
    await emit_support_membership(session, user_id=user.id)
    await session.refresh(user)

    ok(f"Bootstrapped the first admin: {user.id}")
    return user


async def ensure_staff(
    session: AsyncSession,
    profile: dict[str, Any],
    spec: dict[str, Any],
    admin: User,
) -> User:
    """Create a support staff member through create_staff."""
    user = await ensure_user(
        session, profile, spec, role=UserRole.INVESTOR
    )

    if user.role == UserRole.STAFF:
        return user

    await create_staff(user.id, admin, session)
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Storefront
# ---------------------------------------------------------------------------


async def ensure_company(
    session: AsyncSession,
    profile: dict[str, Any],
    spec: dict[str, Any],
    admin: User,
) -> CompanyProfile:
    """Create the company account and its profile through the service."""
    marker = profile["marker"]
    email = _email(profile, spec["email_local"])

    existing_user = await find_user_by_email(session, email)
    if existing_user is not None:
        if existing_user.seeded_profile != marker:
            raise SeedRefusedError(
                f"{email} already exists and is not mine "
                f"(marker: {existing_user.seeded_profile!r})."
            )
        stmt = select(CompanyProfile).where(
            CompanyProfile.user_id == existing_user.id
        )
        company = (await session.execute(stmt)).scalar_one_or_none()
        if company is not None:
            await walk_onboarding(
                session, existing_user, role=UserRole.COMPANY, marker=marker
            )
            return await _activate_company(session, company, admin)

    company = await create_company(
        CreateCompanyRequest(
            email=email,
            password=profile["demo_password"],
            name=spec["name"],
            description=spec.get("description"),
            price_per_unit_cents=spec["price_per_unit_cents"],
            distribution_config=spec["distribution_config"],
            total_supply=spec["total_supply"],
            shares_per_option=spec.get("shares_per_option", 1),
        ),
        admin,
        session,
    )

    # create_company writes status=HIDDEN, and a hidden company is not
    # on the storefront and cannot be bought from. The demo needs it
    # visible, so the status moves through the same state machine a
    # staff member would drive from the admin panel.
    await _activate_company(session, company, admin)

    owner = await find_user_by_email(session, email)
    if owner is None:  # pragma: no cover -- create_company just made it
        raise SeedRefusedError(f"Company owner {email} vanished after creation")
    owner.profile = {
        "first_name": spec.get("first_name", "Company"),
        "last_name": spec.get("last_name", "Owner"),
        "country": spec.get("country", "NL"),
    }
    await session.flush()
    # The company owner starts at ROLE_SELECTED with no e-mail token;
    # the ladder skips the steps that do not apply and walks the rest.
    await walk_onboarding(
        session, owner, role=UserRole.COMPANY, marker=marker
    )
    return company


async def _activate_company(
    session: AsyncSession, company: CompanyProfile, admin: User
) -> CompanyProfile:
    """Put a company on the storefront through the state machine.

    Guarded on the current status rather than called blindly: the
    transition table has no active -> active edge, so a second seed run
    would fail on a company it had already activated.
    """
    if company.status == CompanyStatus.ACTIVE:
        return company
    return await update_company(
        company.id,
        UpdateCompanyRequest(status=CompanyStatus.ACTIVE),
        admin,
        session,
    )


async def ensure_pool(
    session: AsyncSession,
    company: CompanyProfile,
    spec: dict[str, Any],
    admin: User,
) -> OptionPool:
    """Create the company's single active pool, or return it."""
    existing = await get_active_pool(company.id, session)
    if existing is not None:
        return existing

    return await create_pool(
        company.id,
        CreatePoolRequest(equity_percent=spec["equity_percent"]),
        admin,
        session,
    )


async def ensure_product(
    session: AsyncSession,
    company: CompanyProfile,
    spec: dict[str, Any],
    admin: User,
) -> Product:
    """Create one product, or return the one with this name."""
    stmt = select(Product).where(
        Product.company_id == company.id,
        Product.name == spec["name"],
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        if existing.status == ProductStatus.ACTIVE:
            return existing
        return await update_product_status(
            existing.id, ProductStatus.ACTIVE, admin, session
        )

    product = await create_product(
        company.id,
        spec["name"],
        spec["package_size"],
        admin,
        session,
        description=spec.get("description"),
    )
    # Same reason as the company above: create_product writes HIDDEN,
    # and execute_purchase refuses anything that is not ACTIVE.
    return await update_product_status(
        product.id, ProductStatus.ACTIVE, admin, session
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


async def ensure_agent(
    session: AsyncSession,
    profile: dict[str, Any],
    spec: dict[str, Any],
    admin: User,
) -> tuple[User, ReferralLink]:
    """Take one person from investor to approved agent with a link."""
    user = await ensure_user(
        session, profile, spec, role=UserRole.INVESTOR
    )

    if user.role != UserRole.AGENT:
        application = await submit_application(user, session)
        await agent_application_approve(application.id, admin, session)
        await session.refresh(user)

    link_stmt = select(ReferralLink).where(ReferralLink.agent_id == user.id)
    link = (await session.execute(link_stmt)).scalars().first()
    if link is None:
        link = await create_link(user, session)

    return user, link


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


async def ensure_portfolio(
    session: AsyncSession,
    user: User,
    spec: dict[str, Any],
    products: list[Product],
) -> dict[str, int]:
    """Give one investor money and a few purchases.

    The deposit is idempotent by balance floor, the way the script this
    replaces did it. The purchases are made idempotent differently and
    on purpose: execute_purchase has no natural key to check, so the
    guard is "this investor already owns something". Without it a second
    seed run would double every portfolio, which is what made the old
    script non-idempotent and what a no-op re-run has to prevent.
    """
    stats = {"deposited_cents": 0, "purchases": 0}

    target = int(spec.get("deposit_cents", 0))
    if target > 0:
        balance = await get_active_balance(session, user.id)
        confirmed = balance["confirmed"]
        if confirmed < target:
            delta = target - confirmed
            await record_active_ledger(
                session,
                user_id=user.id,
                amount_cents=delta,
                status=LedgerStatus.CONFIRMED,
                reason="deposit:seed",
            )
            stats["deposited_cents"] = delta

    wanted = int(spec.get("purchases", 0))
    if wanted <= 0 or not products:
        return stats

    owned_stmt = select(func.count()).where(Purchase.investor_id == user.id)
    owned = (await session.execute(owned_stmt)).scalar_one()
    if owned:
        return stats

    for product in products[:wanted]:
        purchases = await execute_purchase(product.id, user, session)
        stats["purchases"] += len(purchases)

    return stats


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


async def reset_seed_data(
    session: AsyncSession, marker: str
) -> dict[str, int]:
    """Remove what this profile created, and nothing else.

    THE UN-DECLARATION COMES FIRST, AND IN THIS TRANSACTION. Deleting a
    seeded staff member without telling comms they no longer serve the
    section leaves the roster holding an operator id that no longer
    exists -- and if the seeded ones were the only declared members,
    NOBODY serves the section afterwards: the live operators were
    excluded by the very act of declaring, and the declared ones are
    gone. Emitting first and in the same transaction means a reset that
    fails half-way rolls back both facts rather than leaving that state
    behind.

    emit_support_membership rather than deactivate_staff: the latter
    also closes avatar sessions and kills Redis sessions, raises when
    Redis is down (deliberately -- "better not removed at all than
    removed halfway"), and needs an admin actor. For a reset that trade
    is backwards. The fact we need is one outbox row.

    ORDER. Children before parents, users last, and users themselves in
    referrer order: users.referred_by is ON DELETE RESTRICT, so an agent
    cannot go before the investors they referred.
    """
    counts = {
        "users": 0,
        "staff_unpublished": 0,
        "companies": 0,
        "products": 0,
        "purchases": 0,
    }

    id_stmt = select(User.id).where(User.seeded_profile == marker)
    user_ids = list((await session.execute(id_stmt)).scalars())
    if not user_ids:
        return counts

    # -- 1. Tell comms the seeded operators are off duty. --
    staff_stmt = select(StaffProfile.user_id).where(
        StaffProfile.user_id.in_(user_ids)
    )
    staff_ids = list((await session.execute(staff_stmt)).scalars())
    for staff_user_id in staff_ids:
        await emit_support_membership(
            session, user_id=staff_user_id, member=False
        )
    counts["staff_unpublished"] = len(staff_ids)

    # -- 2. Company-owned rows. --
    company_stmt = select(CompanyProfile.id).where(
        CompanyProfile.user_id.in_(user_ids)
    )
    company_ids = list((await session.execute(company_stmt)).scalars())

    product_ids: list[UUID] = []
    if company_ids:
        product_stmt = select(Product.id).where(
            Product.company_id.in_(company_ids)
        )
        product_ids = list((await session.execute(product_stmt)).scalars())

    # -- 3. Rows that point at purchases, then the purchases. --
    purchase_stmt = select(Purchase.id).where(
        Purchase.investor_id.in_(user_ids)
    )
    purchase_ids = list((await session.execute(purchase_stmt)).scalars())
    if purchase_ids:
        await session.execute(
            delete(ReferralAttribution).where(
                ReferralAttribution.purchase_id.in_(purchase_ids)
            )
        )
        await session.execute(
            delete(Purchase).where(Purchase.id.in_(purchase_ids))
        )
        counts["purchases"] = len(purchase_ids)

    # -- 4. Everything else keyed straight off the users. --
    for statement in (
        delete(ActiveLedger).where(ActiveLedger.user_id.in_(user_ids)),
        delete(PassiveLedger).where(PassiveLedger.user_id.in_(user_ids)),
        delete(Transaction).where(Transaction.user_id.in_(user_ids)),
        delete(DocumentSigning).where(
            DocumentSigning.user_id.in_(user_ids)
        ),
        delete(KYCApplication).where(KYCApplication.user_id.in_(user_ids)),
        delete(AgentApplication).where(
            AgentApplication.user_id.in_(user_ids)
        ),
        delete(ReferralLink).where(ReferralLink.agent_id.in_(user_ids)),
        delete(StaffProfile).where(StaffProfile.user_id.in_(user_ids)),
    ):
        await session.execute(statement)

    if product_ids:
        await session.execute(
            delete(ProductInstallment).where(
                ProductInstallment.product_id.in_(product_ids)
            )
        )
        await session.execute(
            delete(Product).where(Product.id.in_(product_ids))
        )
        counts["products"] = len(product_ids)

    if company_ids:
        await session.execute(
            delete(OptionPool).where(OptionPool.company_id.in_(company_ids))
        )
        await session.execute(
            delete(CompanyPriceHistory).where(
                CompanyPriceHistory.company_id.in_(company_ids)
            )
        )
        await session.execute(
            delete(CompanyProfile).where(CompanyProfile.id.in_(company_ids))
        )
        counts["companies"] = len(company_ids)

    await session.flush()

    # -- 5. The users, referred-to before referrer. --
    remaining = set(user_ids)
    while remaining:
        # Seeded ids somebody still points at as their referrer. The
        # self-reference exclusion is for the Platform user, which is
        # its own referrer and is never in `remaining` anyway -- it is
        # written out so that a future self-referencing row cannot
        # deadlock this loop.
        referenced_stmt = (
            select(User.referred_by)
            .distinct()
            .where(
                User.referred_by.in_(remaining),
                User.id != User.referred_by,
            )
        )
        referenced = set((await session.execute(referenced_stmt)).scalars())
        # A seeded user nobody (seeded or live) still points at.
        deletable = [uid for uid in remaining if uid not in referenced]
        if not deletable:
            blocked = ", ".join(str(uid) for uid in sorted(remaining, key=str))
            raise SeedRefusedError(
                "Cannot delete these seeded users because somebody still "
                f"references them as a referrer: {blocked}. That is "
                "almost always a LIVE person who registered through a "
                "seeded agent's link -- deleting the agent would take "
                "their referral history with it, so the reset stops "
                "instead. Nothing has been deleted."
            )
        await session.execute(delete(User).where(User.id.in_(deletable)))
        counts["users"] += len(deletable)
        remaining.difference_update(deletable)
        await session.flush()

    return counts


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def seed_profile(
    session: AsyncSession, profile: dict[str, Any]
) -> dict[str, int]:
    """Walk the profile top to bottom and report what was made."""
    marker = profile["marker"]
    stats = {
        "staff": 0,
        "companies": 0,
        "products": 0,
        "agents": 0,
        "investors": 0,
        "purchases": 0,
    }

    admin = await ensure_admin(session, profile)

    for spec in profile.get("staff", []):
        await ensure_staff(session, profile, spec, admin)
        stats["staff"] += 1
    info(f"staff: {stats['staff']}")

    products: list[Product] = []
    company_spec = profile.get("company")
    if company_spec:
        company = await ensure_company(session, profile, company_spec, admin)
        stats["companies"] = 1
        await ensure_pool(session, company, company_spec["pool"], admin)
        for product_spec in company_spec.get("products", []):
            products.append(
                await ensure_product(session, company, product_spec, admin)
            )
        stats["products"] = len(products)
        info(f"company: {company.name}, products: {stats['products']}")

    link_by_key: dict[str, ReferralLink] = {}
    for spec in profile.get("agents", []):
        _, link = await ensure_agent(session, profile, spec, admin)
        link_by_key[spec["key"]] = link
        stats["agents"] += 1
    info(f"agents: {stats['agents']}")

    for spec in profile.get("investors", []):
        referrer_key = spec.get("referred_by_agent")
        code = link_by_key[referrer_key].code if referrer_key else None
        investor = await ensure_user(
            session,
            profile,
            spec,
            role=UserRole.INVESTOR,
            referral_code=code,
        )
        stats["investors"] += 1

        portfolio = spec.get("portfolio")
        if portfolio:
            result = await ensure_portfolio(
                session, investor, portfolio, products
            )
            stats["purchases"] += result["purchases"]

    info(f"investors: {stats['investors']}, purchases: {stats['purchases']}")
    logger.info("seed_profile_applied", marker=marker, **stats)
    return stats


async def _run_profile(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    marker = profile["marker"]

    factory = get_session_factory()
    async with factory() as session:
        try:
            await assert_no_live_staff(
                session, marker, allow_live_staff=args.allow_live_staff
            )

            if args.dry_run:
                info(f"profile {args.profile!r}: {profile.get('description')}")
                info(f"marker: {marker}, domain: {profile['email_domain']}")
                info(
                    "would seed: "
                    f"{len(profile.get('staff', []))} staff, "
                    f"{1 if profile.get('company') else 0} company, "
                    f"{len(profile.get('agents', []))} agent(s), "
                    f"{len(profile.get('investors', []))} investor(s)"
                )
                if args.reset:
                    info("would reset first")
                return 0

            if args.reset:
                counts = await reset_seed_data(session, marker)
                ok(f"reset: {counts}")
                await session.commit()

            if args.reset_only:
                return 0

            stats = await seed_profile(session, profile)
            await session.commit()
            ok(f"seeded: {stats}")
            return 0
        except SeedRefusedError as exc:
            await session.rollback()
            err(str(exc))
            return 2
        except Exception:
            await session.rollback()
            raise


async def _run_portfolio(args: argparse.Namespace) -> int:
    """--portfolio-for: top up one LIVE user, marker untouched.

    This is the old `aivis seed-portfolio` verb. It is here rather than
    in a second script because two seeding mechanisms would drift, but
    it is deliberately NOT profile work: the target is a person who
    already exists, chosen by e-mail, and this never sets the marker --
    a live person must not become deletable by --reset because somebody
    filled their dashboard once.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            user = await find_user_by_email(session, args.portfolio_for)
            if user is None:
                err(f"No user at {args.portfolio_for}")
                return 1

            product_stmt = (
                select(Product)
                .where(Product.status == ProductStatus.ACTIVE)
                .limit(max(args.purchases, 0))
            )
            products = list((await session.execute(product_stmt)).scalars())

            stats = await ensure_portfolio(
                session,
                user,
                {
                    "deposit_cents": args.deposit,
                    "purchases": args.purchases,
                },
                products,
            )
            await session.commit()
            ok(f"{args.portfolio_for}: {stats}")
            return 0
        except SeedRefusedError as exc:
            await session.rollback()
            err(str(exc))
            return 2
        except Exception:
            await session.rollback()
            raise


async def main_async(args: argparse.Namespace) -> int:
    setup_logging()
    try:
        if args.portfolio_for:
            return await _run_portfolio(args)
        return await _run_profile(args)
    except SeedRefusedError as exc:
        err(str(exc))
        return 2
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the stand from a profile (test contour only)."
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="profile name in scripts/seed_profiles/ (default: default)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="remove this profile's rows first (live people survive)",
    )
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="remove this profile's rows and stop, without seeding again",
    )
    parser.add_argument(
        "--list", action="store_true", help="list available profiles"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without writing anything",
    )
    parser.add_argument(
        "--allow-live-staff",
        action="store_true",
        help=(
            "seed even though this stand has staff the seed did not "
            "create -- see the refusal message for what this accepts"
        ),
    )
    parser.add_argument(
        "--portfolio-for",
        metavar="EMAIL",
        default=None,
        help="fill one existing user's dashboard instead of seeding",
    )
    parser.add_argument(
        "--deposit",
        type=int,
        default=10_000_000,
        help="--portfolio-for: target confirmed balance in cents",
    )
    parser.add_argument(
        "--purchases",
        type=int,
        default=5,
        help="--portfolio-for: how many products to buy",
    )
    args = parser.parse_args()

    if args.list:
        for name in list_profiles() or []:
            print(name)
        return 0

    if args.reset_only:
        args.reset = True

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
