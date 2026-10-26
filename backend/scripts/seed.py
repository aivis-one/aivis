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
#   kyc          -> kyc.service.decide_by_user (free manual approval)
#   documents    -> documents.service.sign_document
#   staff        -> staff.service.create_staff         (membership free)
#   agents       -> agent_applications submit + approve
#   companies    -> companies.service.create_company   (recipient free)
#   pools        -> pools.service.create_pool
#   products     -> products.service.create_product
#   installments -> products.service.create_installment
#   pictures     -> companies.service.set_company_media,
#                   products.service.set_product_cover    (H36)
#   attachments  -> companies.service.create_attachment
#   roadmap      -> companies.service.create_roadmap_item
#                   + set_roadmap_cover
#   money        -> ledgers.service.record_active_ledger
#   purchases    -> purchases.service.execute_purchase
#
# decide_by_user deserves a note, because it looks like a back door and
# is not one: since H10 it is the ONLY route to an approved account, and
# the same one staff use from the panel for a person who has no queued
# application. The seed calls the service exactly as the staff endpoint
# does. Nothing here writes kyc_status by hand.
#
# The seed cannot go through submit_kyc any more: a submission now costs
# ten dollars, and it runs long before the seeded user has a balance --
# so it would fail on insufficient funds. Manual approval is free, which
# is what makes it the right door for a fixture.
#
# -----------------------------------------------------------------------------
# NO ADMIN IS MADE HERE (H37 P-130)
#
# The seed needs an admin: create_staff, create_company, create_pool and
# create_product all take one as the actor. It no longer makes one. The
# first admin of a box comes from `aivis bootstrap-admin <email>` (the
# production path, app/modules/staff/bootstrap.py), and a seed run on a
# box without an active admin is refused before anything is written --
# the reset included -- with that command in the message. --reset-only
# needs no actor and runs without an admin.
#
# Until H37 the seed bootstrapped the admin itself, from a profile
# section, with the profile's shared demo password. Both are gone.
#
# -----------------------------------------------------------------------------
# PASSWORDS ARE RANDOM AND NEVER SHOWN (H37 P-130)
#
# Every account the seed creates gets its own secrets.token_urlsafe
# password, handed straight to register_email / create_company and kept
# nowhere: not printed, not logged, not written to the profile or the
# repository. A second run does not touch an existing account's
# password. The owner enters seeded accounts through the administrator's
# avatar mode, not by password.
#
# -----------------------------------------------------------------------------
# THE E-MAIL DOMAIN IS THE BOX'S (H37 P-130)
#
# A profile names local parts only (`test01`, `sankord`). The domain is the
# host of FRONTEND_BASE_URL -- the same source the letters read
# (core/email_vars.py) -- so a seeded address is <local>@<this box>, and
# no deployment address is written into the repository. A host that
# cannot carry mail (no dot, an IP address) refuses the run.
#
# -----------------------------------------------------------------------------
# PROFILES
#
# A profile is one JSON file in scripts/seed_profiles/. It describes WHAT
# to seed; this file describes HOW. Adding a project or an account means adding a JSON
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
# The one caller-chosen date there is now -- a roadmap item's target_date
# / valid_until (H37) -- is a fact of the project (the day a milestone
# was reached or is planned), written as an absolute date on purpose: a
# roadmap that drifted with the day the seed ran would be untrue.
#
# -----------------------------------------------------------------------------
# PROJECTS (H37 P-130)
#
# `companies` is a list. Each project has a `key` and a folder
# scripts/templates/projects/<key>/ holding its files:
#
#   media/                       logo.png, logo-dark.png, cover.png, product.png
#   roadmap/<item-key>.png       roadmap covers
#   documents/<lang>/<category>/<file>.pdf    attachments
#
#   media/<lang>/, roadmap/<lang>/   language variants of those pictures
#
# Paths in the profile are relative to that folder and may not leave it.
#
# LANGUAGES (H38 P-132). Texts a screen shows (company and product name and
# description, roadmap title and description) are written as
# {"en": ..., "ru": ...}: "en" goes to the column -- the base and the
# fallback -- and every other language to the row's `translations`.
# A picture's variant for a language is the file of the same name in the
# `<lang>/` subfolder of the picture's folder: media/ru/logo.png is the
# Russian logo when the profile's logo is media/logo.png. English is the
# common file itself, so media/en/ is refused; so is a subfolder that is
# not a two-letter code and a file there that is a variant of no picture
# the profile names.
#
# Every refusal that a profile can earn -- a missing "en", a bad language
# code, a missing file, a file type the services would refuse, a picture
# over its size limit, a metadata block its schema rejects -- happens in
# validate_profile(), BEFORE the first write, so a refused run leaves no
# row and no object behind.
#
# Each piece is idempotent on its own natural key: a picture on the key
# column being set (a variant on its language's key in media_variants), an attachment on (category, title, language) among the
# undeleted ones (the match reconcile_attachments.py uses), a roadmap item
# on its English title, an installment on its name. A changed file in the
# folder is NOT re-uploaded over an existing one, and the translations of
# a row that already exists are not rewritten; --reset is how a project
# is laid down afresh.
#
# -----------------------------------------------------------------------------
# THE STARTING PICTURE AND SUPPORT
#
# An investor's `portfolio` is a deposit and the steps `purchases` (a
# product at once, or with a `plan` its first instalment) and `gifts`
# (parts the stand's admin grants from the project's reserve and the
# investor accepts); see ensure_portfolio. Products are named by the
# project's key and their English name, so a profile names nothing the
# database does not hold.
#
# SUPPORT: any active staff member may claim a ticket in the product, and
# comms serves the support section from its declared roster -- an EMPTY
# roster is served by every operator, a roster with members only by them.
# The seed declares the operators it makes (create_staff) and, with the
# first of them, the admin it acts as (ensure_staff), so the admin keeps
# claiming whatever comms held before this run.
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
# THE CHECK RUNS ONLY FOR A PROFILE THAT DECLARES staff[] (H37). A
# profile of projects and investors declares nobody and cannot take
# anybody off the queue. And since a seed run needs a live admin, which is
# itself staff the seed did not make, a profile that DOES declare staff
# always meets this refusal: that is the risk being real, not a false
# alarm -- declaring operators would take the admin off the queue too.
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
import io
import ipaddress
import json
import secrets
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

# -- sys.path bootstrap (same shape as the scripts this file replaces) -------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
for _p in (_SCRIPTS_DIR, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import structlog  # noqa: E402
from pydantic import EmailStr, TypeAdapter  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import dispose_engine, get_session_factory  # noqa: E402
from app.core.email_vars import site_host  # noqa: E402
from app.core.exceptions import BadRequestError  # noqa: E402
from app.core.i18n import (  # noqa: E402
    BASE_LANGUAGE,
    is_language_code,
    normalize_translations,
)
from app.core.logging import setup_logging  # noqa: E402
from app.core.storage import (  # noqa: E402
    StorageError,
    delete_object,
    list_objects,
)
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
from app.modules.companies.constants import (  # noqa: E402
    ROADMAP_COVER_MAX_BYTES,
    CompanyMediaSlot,
    CompanyStatus,
    RoadmapItemStatus,
    validate_distribution_config,
)
from app.modules.companies.media import (  # noqa: E402
    COMPANY_MEDIA_COLUMN,
    company_media_max_bytes,
    stored_key,
)
from app.modules.companies.models import (  # noqa: E402
    CompanyAttachment,
    CompanyDocumentTemplate,
    CompanyPriceHistory,
    CompanyProfile,
    CompanyRoadmapItem,
)
from app.modules.companies.schemas import (  # noqa: E402
    AttachmentInboxMetadata,
    CreateCompanyRequest,
    CreateRoadmapItemRequest,
    UpdateCompanyRequest,
)
from app.modules.companies.service import (  # noqa: E402
    create_attachment,
    create_company,
    create_roadmap_item,
    set_company_media,
    set_roadmap_cover,
    update_company,
    validate_attachment_mime_by_filename,
    validate_roadmap_cover_mime_by_filename,
)
from app.modules.documents.models import (  # noqa: E402
    Document,
    DocumentSigning,
    DocumentStatus,
)
from app.modules.documents.service import sign_document  # noqa: E402
from app.modules.installments.models import (  # noqa: E402
    InstallmentPlan,
    InstallmentTranche,
)
from app.modules.installments.service import create_plan  # noqa: E402
from app.modules.kyc.models import KYCApplication  # noqa: E402
from app.modules.kyc.service import decide_by_user  # noqa: E402
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
from app.modules.pools.service import (  # noqa: E402
    _compute_total_options,
    create_pool,
    get_active_pool_or_none,
)
from app.modules.processors.validators import (  # noqa: E402
    validate_purchase_config,
)
from app.modules.products.constants import (  # noqa: E402
    ProductStatus,
    validate_plan_config,
)
from app.modules.products.models import Product, ProductInstallment  # noqa: E402
from app.modules.products.schemas import (  # noqa: E402
    CreateInstallmentRequest,
    CreateProductRequest,
)
from app.modules.products.service import (  # noqa: E402
    create_installment,
    create_product,
    set_product_cover,
    update_product_status,
)
from app.modules.purchases.constants import (  # noqa: E402
    PurchaseLegalBasis,
    PurchaseStatus,
)
from app.modules.purchases.gift_service import (  # noqa: E402
    accept_gift,
    grant_gift,
)
from app.modules.purchases.models import Purchase  # noqa: E402
from app.modules.purchases.service import execute_purchase  # noqa: E402
from app.modules.referrals.models import (  # noqa: E402
    ReferralAttribution,
    ReferralLink,
)
from app.modules.referrals.service import create_link  # noqa: E402
from app.modules.staff.bootstrap import find_any_admin  # noqa: E402
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
from app.modules.users.schemas import (  # noqa: E402
    PROFILE_NAME_KEYS,
    UserUpdate,
    profile_name_problem,
)
from app.modules.users.service import select_role, update_user  # noqa: E402

logger = structlog.get_logger()

PROFILES_DIR = _SCRIPTS_DIR / "seed_profiles"
# One folder per project, keyed by the project's `key` (H37). The platform
# templates live beside it in templates/_default/ and are not read here.
PROJECTS_DIR = _SCRIPTS_DIR / "templates" / "projects"

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
    """Read one profile from disk. Its content is checked by
    validate_profile(), which every seed run calls before writing."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        available = ", ".join(list_profiles()) or "(none)"
        raise SeedRefusedError(
            f"No profile named {name!r} in {PROFILES_DIR}. Available: "
            f"{available}"
        )

    with path.open(encoding="utf-8") as handle:
        profile: dict[str, Any] = json.load(handle)

    # The marker written into users.seeded_profile. Defaults to the file
    # name so a profile cannot silently share another profile's rows.
    profile.setdefault("marker", name)
    return profile


# Keys a profile used to carry and does not any more (H37). Present ->
# refused by name, so an old profile cannot run with its passwords,
# domain or admin silently ignored.
_RETIRED_KEYS = {
    "email_domain": "the domain is the host of FRONTEND_BASE_URL",
    "demo_password": "every seeded account gets its own random password",
    "admin": "the seed does not make an admin; run `aivis bootstrap-admin <email>`",
    "company": "projects are a list now: `companies`",
}

# EmailStr as the request schemas apply it, for the seeded addresses.
_EMAIL = TypeAdapter(EmailStr)

# The keys of a roadmap entry; everything else is refused by name.
_ROADMAP_KEYS = {
    "key", "title", "description", "kind", "status", "target_date",
    "valid_until", "external_url", "cover",
}


def mail_domain() -> str:
    """The domain of every seeded address: the host of FRONTEND_BASE_URL.

    Raises:
        SeedRefusedError: the host is empty, has no dot, or is an IP
            address -- none of them carries mail, and create_company's
            e-mail validation would refuse the address half-way through.
    """
    host = site_host()
    refusal = (
        f"FRONTEND_BASE_URL host {host!r} cannot carry seeded e-mail "
        f"addresses: the seed writes <local>@<host of FRONTEND_BASE_URL>, "
        f"which needs a domain name with a dot. Nothing has been written."
    )
    if not host or "." not in host:
        raise SeedRefusedError(refusal)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host.lower()
    raise SeedRefusedError(refusal)


def _email(local: str) -> str:
    return f"{local}@{mail_domain()}".lower()


def _random_password() -> str:
    """A fresh password for one seeded account. Returned to the caller,
    which hands it to the service; never printed, logged or stored."""
    return secrets.token_urlsafe(24)


def _text(value: Any, where: str) -> str:
    """The English text of a {"en": ..., "ru": ...} field.

    Raises:
        SeedRefusedError: not a dictionary, no "en", or an empty one.
    """
    if not isinstance(value, dict):
        raise SeedRefusedError(
            f"{where} must be a dictionary of languages, "
            f'{{"en": ..., "ru": ...}}; got {type(value).__name__}'
        )
    text = value.get("en")
    if not isinstance(text, str) or not text.strip():
        raise SeedRefusedError(f'{where} has no "en" text')
    return text


def _plain_name(value: Any, where: str) -> str:
    """The name of an installment plan: a string, or a {"en": ..., "ru": ...}
    text of which only the English is kept -- a plan has no translations
    column, and the cabinet names a plan by its months."""
    if isinstance(value, str):
        return value
    return _text(value, where)


def _optional_text(spec: dict[str, Any], field: str, where: str) -> str | None:
    if field not in spec or spec[field] is None:
        return None
    return _text(spec[field], f"{where}.{field}")


def _translations(
    spec: dict[str, Any], fields: tuple[str, ...], table: str, where: str
) -> dict[str, dict[str, str]]:
    """The non-English texts of `fields`, as the row's `translations` (H38).

    Raises:
        SeedRefusedError: a language key that is not a two-letter code, or
            a text normalize_translations refuses (not a string, too long).
    """
    raw: dict[str, dict[str, Any]] = {}
    for field in fields:
        value = spec.get(field)
        if value is None:
            continue
        _text(value, f"{where}.{field}")
        for language, text in value.items():
            if language == BASE_LANGUAGE:
                continue
            if not is_language_code(language):
                raise SeedRefusedError(
                    f"{where}.{field}: language {language!r} is not a "
                    f"two-letter lowercase code"
                )
            raw.setdefault(language, {})[field] = text
    try:
        return normalize_translations(table, raw)
    except ValueError as exc:
        raise SeedRefusedError(f"{where}: {exc}") from exc


def _project_file(company_key: str, relative: Any, where: str) -> Path:
    """The file a project entry names, inside the project's folder.

    Raises:
        SeedRefusedError: not a string, outside the folder, or missing.
    """
    if not isinstance(relative, str) or not relative:
        raise SeedRefusedError(f"{where} must be a path inside the project folder")
    root = (PROJECTS_DIR / company_key).resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise SeedRefusedError(
            f"{where} = {relative!r} leaves the project folder {root}"
        )
    if not path.is_file():
        raise SeedRefusedError(f"{where}: no file at {path}")
    return path


def _check_picture(path: Path, max_bytes: int, where: str) -> None:
    """The checks the picture services make, made before any write."""
    try:
        validate_roadmap_cover_mime_by_filename(path.name)
    except BadRequestError as exc:
        raise SeedRefusedError(f"{where}: {exc.message}") from exc
    size = path.stat().st_size
    if size <= 0:
        raise SeedRefusedError(f"{where}: {path} is empty")
    if size > max_bytes:
        raise SeedRefusedError(
            f"{where}: {path} is {size} bytes, over the {max_bytes}-byte limit"
        )


# The project folders whose <lang>/ subfolders hold picture variants.
_VARIANT_FOLDERS = ("media", "roadmap")


def _picture_limits(spec: dict[str, Any]) -> dict[str, int]:
    """Every picture the profile names, as a path relative to the project
    folder, with the size limit its service applies."""
    root = (PROJECTS_DIR / spec["key"]).resolve()
    named: list[tuple[Any, int]] = [
        (spec.get(slot.value), company_media_max_bytes(slot))
        for slot in CompanyMediaSlot
    ]
    named += [(p.get("cover"), ROADMAP_COVER_MAX_BYTES) for p in spec.get("products", [])]
    named += [(i.get("cover"), ROADMAP_COVER_MAX_BYTES) for i in spec.get("roadmap", [])]
    limits: dict[str, int] = {}
    for relative, max_bytes in named:
        if not isinstance(relative, str) or not relative:
            continue
        common = (root / relative).resolve().relative_to(root).as_posix()
        limits[common] = min(max_bytes, limits.get(common, max_bytes))
    return limits


def _picture_variants(spec: dict[str, Any], where: str) -> dict[str, dict[str, Path]]:
    """The language variants in the project folder: picture -> {lang: file}.

    A variant of `media/logo.png` is `media/<lang>/logo.png`. The picture
    paths themselves are checked by _check_company before this runs.

    Raises:
        SeedRefusedError: `en/` (English is the common file), a subfolder
            that is not a two-letter code, anything in it that is not a
            file, or a file that is a variant of no picture the profile
            names.
    """
    root = (PROJECTS_DIR / spec["key"]).resolve()
    pictures = _picture_limits(spec)
    variants: dict[str, dict[str, Path]] = {}
    for folder in _VARIANT_FOLDERS:
        base = root / folder
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if not sub.is_dir():
                continue
            language = sub.name
            if language == BASE_LANGUAGE:
                raise SeedRefusedError(
                    f"{where}: {folder}/{language}/ -- English is the common "
                    f"file in {folder}/ itself, not a variant"
                )
            if not is_language_code(language):
                raise SeedRefusedError(
                    f"{where}: {folder}/{language}/ is not a two-letter "
                    f"lowercase language code"
                )
            for path in sorted(sub.iterdir()):
                common = f"{folder}/{path.name}"
                if not path.is_file():
                    raise SeedRefusedError(
                        f"{where}: {folder}/{language}/{path.name} is not a file"
                    )
                if common not in pictures:
                    raise SeedRefusedError(
                        f"{where}: {folder}/{language}/{path.name} would be a "
                        f"variant of {common}, which is no picture of this "
                        f"profile"
                    )
                variants.setdefault(common, {})[language] = path
    return variants


def _variants_of(spec: dict[str, Any], relative: str) -> dict[str, Path]:
    """The language variants of one picture the profile names."""
    root = (PROJECTS_DIR / spec["key"]).resolve()
    common = (root / relative).resolve().relative_to(root).as_posix()
    return _picture_variants(spec, spec["key"]).get(common, {})


def _local_of(spec: dict[str, Any]) -> str | None:
    """The local part of an account's address.

    A person is named by `email_local`. A project's package carries a full
    `email` instead: the local part of that is the account, and the domain
    is the box's, as for every other seeded address -- a package names who
    the project is, never where the box lives. (sync_project_package.py
    writes the profile's entry with `email_local` already.)
    """
    local = spec.get("email_local")
    if local is None and isinstance(spec.get("email"), str):
        local = spec["email"].split("@", 1)[0]
    return local if isinstance(local, str) and local else None


def _check_address(spec: dict[str, Any], where: str) -> str:
    """The seeded address of one account, as the services would validate it."""
    local = _local_of(spec)
    if local is None:
        raise SeedRefusedError(f"{where} has no `email_local` (or `email`)")
    try:
        return str(_EMAIL.validate_python(_email(local)))
    except ValueError as exc:
        raise SeedRefusedError(f"{where}.email_local {local!r}: {exc}") from exc


def _check_names(spec: dict[str, Any], where: str) -> None:
    """An account's first and last name, held to the rule every writer of
    profile names follows (users/schemas.py profile_name_problem)."""
    for key in PROFILE_NAME_KEYS:
        if key in spec:
            problem = profile_name_problem(key, spec[key])
            if problem is not None:
                raise SeedRefusedError(f"{where}.{key}: {problem}")


def _check_company(spec: dict[str, Any], where: str) -> None:
    key = spec.get("key")
    if not isinstance(key, str) or not key:
        raise SeedRefusedError(f"{where} has no `key`")
    email = _check_address(spec, where)
    _check_names(spec, where)
    name = _text(spec.get("name"), f"{where}.name")
    description = _optional_text(spec, "description", where)

    # The create body as the staff endpoint gets it (the password is a
    # stand-in: the real one is drawn at creation), then the service's own
    # distribution check, which the schema does not make.
    try:
        body = CreateCompanyRequest(
            email=email,
            password=_random_password(),
            name=name,
            description=description,
            translations=_translations(
                spec, ("name", "description"), "company_profiles", where
            ),
            price_per_unit_cents=spec.get("price_per_unit_cents"),
            distribution_config=spec.get("distribution_config"),
            total_supply=spec.get("total_supply"),
            shares_per_option=spec.get("shares_per_option", 1),
        )
    except ValueError as exc:
        raise SeedRefusedError(f"{where}: {exc}") from exc
    try:
        validate_distribution_config(body.distribution_config)
    except BadRequestError as exc:
        raise SeedRefusedError(f"{where}.distribution_config: {exc.message}") from exc

    # The pool: the schema's bounds, and create_pool's "at least one option".
    try:
        pool = CreatePoolRequest.model_validate(spec.get("pool"))
    except ValueError as exc:
        raise SeedRefusedError(f"{where}.pool: {exc}") from exc
    total_options = _compute_total_options(body.total_supply, pool.equity_percent)
    if total_options <= 0:
        raise SeedRefusedError(
            f"{where}.pool: equity_percent {pool.equity_percent} of "
            f"total_supply {body.total_supply} gives no options"
        )

    for slot in CompanyMediaSlot:
        if spec.get(slot.value) is not None:
            path = _project_file(key, spec[slot.value], f"{where}.{slot.value}")
            _check_picture(path, company_media_max_bytes(slot), f"{where}.{slot.value}")

    price = body.price_per_unit_cents
    for i, product in enumerate(spec.get("products", [])):
        pwhere = f"{where}.products[{i}]"
        # The create body as the staff endpoint gets it (company_id is a
        # stand-in), then create_product's "a package fits in the pool".
        try:
            product_body = CreateProductRequest(
                company_id=uuid4(),
                name=_text(product.get("name"), f"{pwhere}.name"),
                description=_optional_text(product, "description", pwhere),
                translations=_translations(
                    product, ("name", "description"), "products", pwhere
                ),
                package_size=product.get("package_size"),
                purchase_config=product.get("purchase_config"),
            )
        except ValueError as exc:
            raise SeedRefusedError(f"{pwhere}: {exc}") from exc
        if product_body.package_size > total_options:
            raise SeedRefusedError(
                f"{pwhere}.package_size {product_body.package_size} exceeds "
                f"the pool's {total_options} options"
            )
        if product.get("cover") is not None:
            path = _project_file(key, product["cover"], f"{pwhere}.cover")
            _check_picture(path, ROADMAP_COVER_MAX_BYTES, f"{pwhere}.cover")
        try:
            if product.get("purchase_config") is not None:
                validate_purchase_config(product["purchase_config"])
            for j, installment in enumerate(product.get("installments", [])):
                try:
                    plan = CreateInstallmentRequest.model_validate(
                        {
                            **installment,
                            "name": _plain_name(
                                installment.get("name"), f"{pwhere}.installments[{j}].name"
                            ),
                        }
                    )
                except ValueError as exc:
                    raise SeedRefusedError(
                        f"{pwhere}.installments[{j}]: {exc}"
                    ) from exc
                try:
                    validate_plan_config(
                        plan.plan_config,
                        product_units=product_body.package_size,
                        price_per_unit_cents=price,
                    )
                except BadRequestError as exc:
                    raise SeedRefusedError(
                        f"{pwhere}.installments[{j}]: {exc.message}"
                    ) from exc
        except BadRequestError as exc:
            raise SeedRefusedError(f"{pwhere}: {exc.message}") from exc

    for i, attachment in enumerate(spec.get("attachments", [])):
        awhere = f"{where}.attachments[{i}]"
        path = _project_file(key, attachment.get("file"), f"{awhere}.file")
        try:
            validate_attachment_mime_by_filename(path.name)
        except BadRequestError as exc:
            raise SeedRefusedError(f"{awhere}: {exc.message}") from exc
        size = path.stat().st_size
        if size <= 0:
            raise SeedRefusedError(f"{awhere}: {path} is empty")
        if size > settings.storage_max_file_size_bytes:
            raise SeedRefusedError(
                f"{awhere}: {path} is {size} bytes, over the "
                f"{settings.storage_max_file_size_bytes}-byte attachment limit"
            )
        try:
            AttachmentInboxMetadata.model_validate(attachment.get("meta"))
        except ValueError as exc:
            raise SeedRefusedError(f"{awhere}.meta: {exc}") from exc

    seen_items: set[str] = set()
    seen_titles: set[str] = set()
    for i, item in enumerate(spec.get("roadmap", [])):
        rwhere = f"{where}.roadmap[{i}]"
        unknown = sorted(set(item) - _ROADMAP_KEYS)
        if unknown:
            raise SeedRefusedError(f"{rwhere} has unknown keys: {unknown}")
        item_key = item.get("key")
        if not isinstance(item_key, str) or not item_key:
            raise SeedRefusedError(f"{rwhere} has no `key`")
        if item_key in seen_items:
            raise SeedRefusedError(f"{rwhere}: key {item_key!r} is used twice")
        seen_items.add(item_key)
        title = _text(item.get("title"), f"{rwhere}.title")
        # The English title is how a second run finds the item again.
        if title in seen_titles:
            raise SeedRefusedError(f"{rwhere}: title {title!r} is used twice")
        seen_titles.add(title)
        _roadmap_request(item, rwhere)
        if item.get("cover") is not None:
            path = _project_file(key, item["cover"], f"{rwhere}.cover")
            _check_picture(path, ROADMAP_COVER_MAX_BYTES, f"{rwhere}.cover")

    # The language variants, after every picture they vary is checked.
    limits = _picture_limits(spec)
    for common, by_language in _picture_variants(spec, where).items():
        for language, path in by_language.items():
            _check_picture(path, limits[common], f"{where}: {common} ({language})")


def _roadmap_request(item: dict[str, Any], where: str) -> CreateRoadmapItemRequest:
    """The create body of one roadmap entry, as the staff endpoint gets it."""
    status = item.get("status")
    if status is not None and status not in {s.value for s in RoadmapItemStatus}:
        raise SeedRefusedError(f"{where}.status {status!r} is not a roadmap status")
    try:
        return CreateRoadmapItemRequest.model_validate(
            {
                "kind": item.get("kind", "milestone"),
                "title": _text(item.get("title"), f"{where}.title"),
                "description": _optional_text(item, "description", where),
                "translations": _translations(
                    item, ("title", "description"), "company_roadmap_items", where
                ),
                "target_date": item.get("target_date"),
                "valid_until": item.get("valid_until"),
                "status": status,
                "external_url": item.get("external_url"),
            }
        )
    except ValueError as exc:
        raise SeedRefusedError(f"{where}: {exc}") from exc


def _check_portfolio(
    profile: dict[str, Any], portfolio: dict[str, Any], where: str
) -> None:
    """One investor's starting picture, checked before any write.

    `deposit_cents` is a whole number >= 0. `purchases` is a list of
    {"company": key, "product": English name, "plan": instalment name
    (optional)} -- one purchase at once, or the first payment of a plan.
    `gifts` is a list of {"company", "product", "lots" (optional, the
    package by default)} -- parts the stand's admin grants from the
    project's reserve, which the investor then accepts. Every name must
    exist in the profile, and the deposit must pay for every purchase and
    first payment, so a refusal never comes half-way through the run.
    """
    deposit = portfolio.get("deposit_cents", 0)
    if not isinstance(deposit, int) or isinstance(deposit, bool) or deposit < 0:
        raise SeedRefusedError(f"{where}.deposit_cents must be a whole number >= 0")

    companies = {c.get("key"): c for c in profile.get("companies", [])}
    needed = 0
    kinds: set[tuple[Any, Any, bool]] = set()
    for field in ("purchases", "gifts"):
        items = portfolio.get(field, [])
        if not isinstance(items, list):
            raise SeedRefusedError(
                f"{where}.{field} must be a list of steps, not {items!r} "
                f"(a count of purchases is the old form)"
            )
        for k, item in enumerate(items):
            iwhere = f"{where}.{field}[{k}]"
            if not isinstance(item, dict):
                raise SeedRefusedError(f"{iwhere} must be an object")
            company = companies.get(item.get("company"))
            if company is None:
                raise SeedRefusedError(
                    f"{iwhere}.company {item.get('company')!r} names no project "
                    f"in `companies`"
                )
            products = {
                _text(p.get("name"), f"{iwhere}.product"): p
                for p in company.get("products", [])
            }
            product = products.get(item.get("product"))
            if product is None:
                raise SeedRefusedError(
                    f"{iwhere}.product {item.get('product')!r} names no product "
                    f"of project {item.get('company')!r}"
                )
            if field == "gifts":
                lots = item.get("lots", product["package_size"])
                if not isinstance(lots, int) or isinstance(lots, bool) or lots <= 0:
                    raise SeedRefusedError(f"{iwhere}.lots must be a whole number > 0")
                continue
            plan = item.get("plan")
            kinds.add((item.get("company"), item.get("product"), plan is None))
            if (item.get("company"), item.get("product"), plan is not None) in kinds:
                raise SeedRefusedError(
                    f"{iwhere}: a product bought at once and on a plan by one investor"
                )
            if plan is None:
                needed += product["package_size"] * company["price_per_unit_cents"]
                continue
            plans = {
                _plain_name(i.get("name"), f"{iwhere}.plan"): i
                for i in product.get("installments", [])
            }
            if plan not in plans:
                raise SeedRefusedError(
                    f"{iwhere}.plan {plan!r} names no instalment of that product"
                )
            needed += plans[plan]["plan_config"]["tranches"][0]["amount_cents"]
    if needed > deposit:
        raise SeedRefusedError(
            f"{where}: the deposit of {deposit} cents does not cover the "
            f"{needed} cents its purchases and first payments cost"
        )


def validate_profile(profile: dict[str, Any]) -> None:
    """Every refusal a profile can earn, before the first write.

    Retired keys, the shape of `companies`, the English texts, the
    project files (present, inside their folder, of a type and size the
    services accept), the metadata and roadmap bodies against their
    schemas, purchase and plan configs against their validators, and the
    mail domain. What is left for the run to refuse is what only the
    database knows (a user at a seeded address who is not ours, a second
    roadmap item with the same title made by hand).

    Raises:
        SeedRefusedError: naming the field or the path.
    """
    for retired, reason in _RETIRED_KEYS.items():
        if retired in profile:
            raise SeedRefusedError(
                f"Profile key {retired!r} is retired: {reason}."
            )

    # The domain first: every address below is built on it.
    mail_domain()
    for section in ("staff", "agents", "investors"):
        for i, spec in enumerate(profile.get(section, [])):
            _check_address(spec, f"{section}[{i}]")
            _check_names(spec, f"{section}[{i}]")

    # An investor's agent and portfolio: a wrong agent key used to surface
    # as a KeyError half-way through the run, after the agents were made.
    agent_keys = {spec.get("key") for spec in profile.get("agents", [])}
    for i, spec in enumerate(profile.get("investors", [])):
        referrer = spec.get("referred_by_agent")
        if referrer is not None and referrer not in agent_keys:
            raise SeedRefusedError(
                f"investors[{i}].referred_by_agent {referrer!r} names no agent "
                f"in `agents`"
            )
        _check_portfolio(profile, spec.get("portfolio") or {}, f"investors[{i}].portfolio")

    companies = profile.get("companies", [])
    if not isinstance(companies, list):
        raise SeedRefusedError("`companies` must be a list of projects")
    keys: set[str] = set()
    for i, spec in enumerate(companies):
        _check_company(spec, f"companies[{i}]")
        if spec["key"] in keys:
            raise SeedRefusedError(f"companies[{i}]: key {spec['key']!r} is used twice")
        keys.add(spec["key"])


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


async def assert_no_live_staff(
    session: AsyncSession,
    marker: str,
    *,
    allow_live_staff: bool,
    admin: User | None = None,
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
    if admin is not None:
        # The admin the run acts as is declared by the seed itself
        # (ensure_staff), so it cannot be taken off the queue by it.
        stmt = stmt.where(User.id != admin.id)
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
        "This profile declares staff, and this stand has active staff "
        "profiles that this seed did not create (for example "
        + ", ".join(str(i) for i in foreign[:3])
        + "). The admin the run acts as is not counted: the seed declares "
        "it itself with the first operator it makes. Declaring seeded "
        "operators for the support section would stop every operator that "
        "is NOT declared from serving that section, and whether the other "
        "live ones are declared is a fact that lives in comms, not here, so "
        "it cannot be checked. Nothing has been written. Either re-run with "
        "--allow-live-staff if you know those people are declared (or "
        "that this stand is yours to change), or drop `staff` from the "
        "profile."
    )


async def require_admin(session: AsyncSession) -> User:
    """The active admin a seed run acts as, or a refusal (H37).

    The seed does not make an admin any more. Called before anything is
    written -- before the reset too -- so a refused run changes nothing.

    Raises:
        SeedRefusedError: no active admin on this stand.
    """
    admin = await find_any_admin(session)
    if admin is None:
        raise SeedRefusedError(
            "This stand has no active admin, and the seed needs one to act "
            "as (staff, companies, pools and products are created by an "
            "admin). The seed does not make one. Register on the site, "
            "confirm the address, then run: aivis bootstrap-admin <email>. "
            "Nothing has been written."
        )
    info(f"Acting as the admin: {admin.id}")
    return admin


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

    Signing is what moves ROLE_SELECTED to ONBOARDING_COMPLETE for roles
    that have required documents; roles with none are already there via
    the cascade inside select_role. Documents the user has signed already are
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

    if user.kyc_status != KYCStatus.APPROVED:
        await decide_by_user(
            user_id=user.id,
            new_status=KYCStatus.APPROVED,
            reason="Seeded fixture user -- approved by the seed script.",
            actor_id=None,
            session=session,
        )
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
    email = _email(_local_of(spec) or "")

    existing = await find_user_by_email(session, email)
    if existing is not None:
        if existing.seeded_profile != marker:
            raise SeedRefusedError(
                f"{email} already exists and was not created by profile "
                f"{marker!r} (marker: {existing.seeded_profile!r}). The "
                f"seed does not take over rows it did not make. Pick "
                f"another email_local in the profile, or clear that "
                f"user by hand."
            )
        # Idempotent path: finish any step a previous run left undone.
        return await walk_onboarding(
            session, existing, role=role, marker=marker
        )

    # A random password per account, handed straight to the service and
    # kept nowhere (see the header). An existing account above keeps its own.
    user = await register_email(
        email,
        _random_password(),
        session,
        referral_code=referral_code,
    )
    # NO THROWAWAY BackgroundTasks ANY MORE, AND NO MAIL EITHER. This
    # used to pass a BackgroundTasks() nobody would ever run -- FastAPI
    # runs background tasks after a response, and a seed has no response
    # -- so the scheduled verification e-mail died with the object.
    # register_email now emits a comms notification_request into the
    # outbox instead, inside this session. On a box with no comms
    # address the emitter is gated off and writes nothing at all; on a
    # linked box the seeded users WILL be sent their verification
    # code, which is what a seeded user asking for one should get.

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
    # THE ADMIN IS DECLARED WITH THE FIRST OPERATOR THE SEED MAKES. A support
    # section with no declared member is served by every operator; the moment
    # one is declared, only the declared serve. The admin was declared when
    # it was promoted -- if comms was configured then, which this run cannot
    # read -- and if it was not, declaring test01 alone would take the admin
    # off the queue. Declaring it again is a no-op where it is already a
    # member (comms answers by outcome) and the one thing that keeps "every
    # worker on support or admin takes the card himself" true where it was
    # not. Written only when this run makes the operator, so a re-run adds
    # no second row; reset un-declares the seeded operators only.
    await emit_support_membership(session, user_id=admin.id)
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
    email = _email(_local_of(spec) or "")

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
            password=_random_password(),
            name=_text(spec["name"], "name"),
            description=_optional_text(spec, "description", "company"),
            translations=_translations(
                spec, ("name", "description"), "company_profiles", "company"
            ),
            price_per_unit_cents=spec["price_per_unit_cents"],
            distribution_config=spec["distribution_config"],
            total_supply=spec["total_supply"],
            shares_per_option=spec.get("shares_per_option", 1),
        ),
        admin,
        session,
    )

    # create_company writes status=HIDDEN, and a hidden company is not
    # on the storefront and cannot be bought from. The storefront needs it
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
    """Create the company's single active pool, or return it.

    get_active_pool_or_none, not get_active_pool: the latter RAISES when
    there is no pool, so this check used to stop every first seed of a
    company here (H37 found it; nothing had run this path before).
    """
    existing = await get_active_pool_or_none(company.id, session)
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
    company_spec: dict[str, Any],
    spec: dict[str, Any],
    admin: User,
    stats: dict[str, int] | None = None,
) -> Product:
    """Create one product with its installments and cover, or finish it.

    Found again by its English name inside the company. Installments are
    found by name among the undeleted ones; the cover is uploaded only
    while the product has none (H37), each language variant of it only
    while that language has none (H38, counted in
    stats["picture_variants"]).
    """
    name = _text(spec["name"], "product.name")
    stmt = select(Product).where(
        Product.company_id == company.id,
        Product.name == name,
    )
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        product = await create_product(
            company.id,
            name,
            spec["package_size"],
            admin,
            session,
            description=_optional_text(spec, "description", "product"),
            purchase_config=spec.get("purchase_config"),
            translations=_translations(
                spec, ("name", "description"), "products", "product"
            ),
        )

    for installment in spec.get("installments", []):
        plan_name = _plain_name(installment["name"], "installment.name")
        exists_stmt = select(ProductInstallment.id).where(
            ProductInstallment.product_id == product.id,
            ProductInstallment.name == plan_name,
            ProductInstallment.is_deleted.is_(False),
        )
        if (await session.execute(exists_stmt)).first() is None:
            await create_installment(
                product.id,
                plan_name,
                installment["plan_config"],
                admin,
                session,
            )

    if spec.get("cover") is not None:
        path = _project_file(company_spec["key"], spec["cover"], "product.cover")
        files: list[tuple[str | None, Path]] = [(None, path)]
        files += sorted(_variants_of(company_spec, spec["cover"]).items())
        for language, file in files:
            if stored_key(product, "cover_storage_key", "cover", language):
                continue
            content_type, ext = validate_roadmap_cover_mime_by_filename(file.name)
            data = file.read_bytes()
            await set_product_cover(
                session,
                company.id,
                product.id,
                admin,
                file_data=io.BytesIO(data),
                file_size_bytes=len(data),
                content_type=content_type,
                file_extension=ext,
                language=language,
            )
            if language is not None and stats is not None:
                stats["picture_variants"] += 1

    # Same reason as the company: create_product writes HIDDEN, and
    # execute_purchase refuses anything that is not ACTIVE.
    if product.status == ProductStatus.ACTIVE:
        return product
    return await update_product_status(
        product.id, ProductStatus.ACTIVE, admin, session
    )


# ---------------------------------------------------------------------------
# Project files: pictures, attachments, roadmap (H37 P-130)
# ---------------------------------------------------------------------------


async def ensure_company_media(
    session: AsyncSession,
    company: CompanyProfile,
    spec: dict[str, Any],
    admin: User,
    stats: dict[str, int] | None = None,
) -> int:
    """Upload the logo, dark logo and cover the profile names, each only
    while its slot is empty, then their language variants, each only
    while that language's variant is empty (H38). Returns how many common
    pictures were uploaded; the variants go to stats["picture_variants"]."""
    uploaded = 0
    for slot in CompanyMediaSlot:
        relative = spec.get(slot.value)
        if relative is None:
            continue
        path = _project_file(spec["key"], relative, slot.value)
        files: list[tuple[str | None, Path]] = [(None, path)]
        files += sorted(_variants_of(spec, relative).items())
        for language, file in files:
            if stored_key(company, COMPANY_MEDIA_COLUMN[slot], slot.value, language):
                continue
            content_type, ext = validate_roadmap_cover_mime_by_filename(file.name)
            data = file.read_bytes()
            await set_company_media(
                session,
                company.id,
                admin,
                slot=slot,
                file_data=io.BytesIO(data),
                file_size_bytes=len(data),
                content_type=content_type,
                file_extension=ext,
                language=language,
            )
            if language is None:
                uploaded += 1
            elif stats is not None:
                stats["picture_variants"] += 1
    return uploaded


async def ensure_attachments(
    session: AsyncSession,
    company: CompanyProfile,
    spec: dict[str, Any],
    admin: User,
) -> int:
    """Create the attachments the profile names that are not there yet.

    "There" is the key reconcile_attachments.py matches on: the same
    company, category, title and language among the undeleted rows.
    Returns how many were created.
    """
    created = 0
    for attachment in spec.get("attachments", []):
        meta = AttachmentInboxMetadata.model_validate(attachment["meta"])
        exists_stmt = select(CompanyAttachment.id).where(
            CompanyAttachment.company_id == company.id,
            CompanyAttachment.category == meta.category,
            CompanyAttachment.title == meta.title,
            CompanyAttachment.language == meta.language,
            CompanyAttachment.is_deleted.is_(False),
        )
        if (await session.execute(exists_stmt)).first() is not None:
            continue
        path = _project_file(spec["key"], attachment["file"], "attachment.file")
        data = path.read_bytes()
        await create_attachment(
            session,
            company.id,
            admin,
            file_data=data,
            file_size_bytes=len(data),
            original_filename=path.name,
            content_type=validate_attachment_mime_by_filename(path.name),
            metadata=meta,
        )
        created += 1
    return created


async def ensure_roadmap(
    session: AsyncSession,
    company: CompanyProfile,
    spec: dict[str, Any],
    admin: User,
    stats: dict[str, int] | None = None,
) -> int:
    """Create the roadmap items the profile names, then their covers (and
    the covers' language variants, H38, in stats["picture_variants"]).

    An item is found again by its English title among the company's
    undeleted items -- the roadmap has no column for the profile's key.
    Two undeleted items with that title (one made by hand) are refused
    rather than guessed between. A cover is uploaded only while the item
    has none. Returns how many items were created.
    """
    created = 0
    for item in spec.get("roadmap", []):
        body = _roadmap_request(item, f"roadmap[{item['key']}]")
        found_stmt = select(CompanyRoadmapItem).where(
            CompanyRoadmapItem.company_id == company.id,
            CompanyRoadmapItem.title == body.title,
            CompanyRoadmapItem.is_deleted.is_(False),
        )
        found = list((await session.execute(found_stmt)).scalars())
        if len(found) > 1:
            raise SeedRefusedError(
                f"Project {spec['key']!r} has {len(found)} roadmap items titled "
                f"{body.title!r}; the seed finds an item by its title and "
                f"will not pick one. Remove the extra item by hand."
            )
        if found:
            roadmap_item = found[0]
        else:
            roadmap_item = await create_roadmap_item(
                company.id,
                body.title,
                admin,
                session,
                kind=body.kind.value,
                description=body.description,
                target_date=body.target_date,
                valid_until=body.valid_until,
                status=body.status,
                external_url=body.external_url,
                translations=body.translations,
            )
            created += 1

        if item.get("cover") is None:
            continue
        path = _project_file(spec["key"], item["cover"], "roadmap.cover")
        files: list[tuple[str | None, Path]] = [(None, path)]
        files += sorted(_variants_of(spec, item["cover"]).items())
        for language, file in files:
            if stored_key(roadmap_item, "cover_storage_key", "cover", language):
                continue
            content_type, ext = validate_roadmap_cover_mime_by_filename(file.name)
            data = file.read_bytes()
            await set_roadmap_cover(
                session,
                company.id,
                roadmap_item.id,
                admin,
                file_data=io.BytesIO(data),
                file_size_bytes=len(data),
                content_type=content_type,
                file_extension=ext,
                language=language,
            )
            if language is not None and stats is not None:
                stats["picture_variants"] += 1
    return created


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


async def _find_product(
    session: AsyncSession, profile: dict[str, Any], company_key: str, name: str
) -> Product:
    """A product of a profile's project, found by the project's key and the
    product's English name -- the same keys the run made it under."""
    spec = next(c for c in profile["companies"] if c["key"] == company_key)
    owner = await find_user_by_email(session, _email(_local_of(spec) or ""))
    if owner is None:
        raise SeedRefusedError(f"Project {company_key!r} has no owner account")
    company = (
        await session.execute(
            select(CompanyProfile).where(CompanyProfile.user_id == owner.id)
        )
    ).scalar_one_or_none()
    product = None
    if company is not None:
        product = (
            await session.execute(
                select(Product).where(
                    Product.company_id == company.id, Product.name == name
                )
            )
        ).scalar_one_or_none()
    if product is None:
        raise SeedRefusedError(f"Project {company_key!r} has no product {name!r}")
    return product


async def ensure_portfolio(
    session: AsyncSession,
    user: User,
    spec: dict[str, Any],
    profile: dict[str, Any],
    admin: User,
) -> dict[str, int]:
    """One investor's starting picture: money, then the steps of the spec.

    Every step goes through the application's own path and is found again
    on its own natural key, so a second run changes nothing:

      - deposit_cents: by balance floor, as before;
      - gifts: the admin grants (gift_service.grant_gift, from the
        project's reserve, no money) and the investor accepts
        (accept_gift) -- the one gift this product has; a gift left
        pending by a run that died is accepted by the next;
      - purchases: a sale (execute_purchase) found by (investor, product,
        legal basis sale), or, with a `plan`, an instalment plan
        (create_plan) found by (investor, product, plan template); the
        first payment is taken inline and the rest is the scheduler's.

    A profile's purchases never mix one product at once and on a plan for
    the same investor: the tranche payments are sale rows of that product.
    """
    stats = {"deposited_cents": 0, "purchases": 0, "instalments": 0, "gifts": 0}

    target = int(spec.get("deposit_cents", 0))
    if target > 0:
        # The deposit is idempotent on THIS seed's own rows, not on the
        # balance: a purchase or a tranche is a negative CONFIRMED row, so a
        # balance floor would hand the money out again on every run.
        seeded = (
            await session.execute(
                select(func.coalesce(func.sum(ActiveLedger.amount_cents), 0)).where(
                    ActiveLedger.user_id == user.id,
                    ActiveLedger.reason == "deposit:seed",
                    ActiveLedger.status != LedgerStatus.REVERSED,
                )
            )
        ).scalar_one()
        if seeded < target:
            await record_active_ledger(
                session,
                user_id=user.id,
                amount_cents=target - seeded,
                status=LedgerStatus.CONFIRMED,
                reason="deposit:seed",
            )
            stats["deposited_cents"] = target - seeded

    for item in spec.get("gifts", []):
        product = await _find_product(session, profile, item["company"], item["product"])
        gift = (
            await session.execute(
                select(Purchase).where(
                    Purchase.investor_id == user.id,
                    Purchase.product_id == product.id,
                    Purchase.legal_basis == PurchaseLegalBasis.GIFT,
                    Purchase.source_purchase_id.is_(None),
                )
            )
        ).scalars().first()
        if gift is None:
            gift = await grant_gift(
                staff=admin,
                user_id=user.id,
                product_id=product.id,
                units=item.get("lots", product.package_size),
                session=session,
            )
            stats["gifts"] += 1
        if gift.status == PurchaseStatus.PENDING_ACCEPTANCE:
            await accept_gift(gift.id, user, session)

    for item in spec.get("purchases", []):
        product = await _find_product(session, profile, item["company"], item["product"])
        plan_name = item.get("plan")
        if plan_name is None:
            made = (
                await session.execute(
                    select(Purchase.id).where(
                        Purchase.investor_id == user.id,
                        Purchase.product_id == product.id,
                        Purchase.legal_basis == PurchaseLegalBasis.SALE,
                        Purchase.source_purchase_id.is_(None),
                    )
                )
            ).first()
            if made is None:
                await execute_purchase(product.id, user, session)
                stats["purchases"] += 1
            continue
        template = (
            await session.execute(
                select(ProductInstallment).where(
                    ProductInstallment.product_id == product.id,
                    ProductInstallment.name == plan_name,
                    ProductInstallment.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if template is None:
            raise SeedRefusedError(
                f"Product {product.name!r} has no instalment {plan_name!r}"
            )
        made = (
            await session.execute(
                select(InstallmentPlan.id).where(
                    InstallmentPlan.investor_id == user.id,
                    InstallmentPlan.product_installment_id == template.id,
                )
            )
        ).first()
        if made is None:
            await create_plan(product.id, template.id, user, session)
            stats["instalments"] += 1

    return stats


async def ensure_portfolio_count(
    session: AsyncSession,
    user: User,
    spec: dict[str, Any],
    products: list[Product],
) -> dict[str, int]:
    """Give one LIVE investor money and a few purchases (`aivis seed-portfolio`).

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
        "instalment_plans": 0,
        "attachments": 0,
        "roadmap_items": 0,
        "templates": 0,
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

    # -- 3a. Instalment plans: their tranches point at purchases (RESTRICT),
    # so tranches and plans go before the purchases. --
    plan_ids = list(
        (
            await session.execute(
                select(InstallmentPlan.id).where(
                    InstallmentPlan.investor_id.in_(user_ids)
                )
            )
        ).scalars()
    )
    if plan_ids:
        await session.execute(
            delete(InstallmentTranche).where(InstallmentTranche.plan_id.in_(plan_ids))
        )
        await session.execute(
            delete(InstallmentPlan).where(InstallmentPlan.id.in_(plan_ids))
        )
        counts["instalment_plans"] = len(plan_ids)

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

    # The project's own rows (H37): attachments, roadmap items and
    # document templates are RESTRICT on the company. Their storage
    # objects are NOT touched here -- purge_seeded_objects deletes them
    # after the commit, so a reset that rolls back keeps both.
    if company_ids:
        for model, name in (
            (CompanyAttachment, "attachments"),
            (CompanyRoadmapItem, "roadmap_items"),
            (CompanyDocumentTemplate, "templates"),
        ):
            result = await session.execute(
                delete(model).where(model.company_id.in_(company_ids))
            )
            counts[name] = result.rowcount or 0

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


async def seeded_company_ids(session: AsyncSession, marker: str) -> list[UUID]:
    """The companies whose owner carries this marker -- the ones --reset
    deletes, read before it does so their objects can be found after."""
    stmt = (
        select(CompanyProfile.id)
        .join(User, User.id == CompanyProfile.user_id)
        .where(User.seeded_profile == marker)
    )
    return list((await session.execute(stmt)).scalars())


async def purge_seeded_objects(company_ids: list[UUID]) -> dict[str, int]:
    """Delete every storage object under companies/<id>/ of these companies.

    Called AFTER the reset's rows are committed (H37): an object deleted
    before the commit would be gone while its row survived a rollback.
    Everything a project has in the storage lives under that one prefix
    (pictures, product covers, roadmap covers, attachments, templates).
    A failure to list or delete is a warning, not a refusal -- the rows
    are already gone, and a leftover object is an orphan, not a lie.
    """
    stats = {"objects": 0, "failed": 0}
    for company_id in company_ids:
        prefix = f"companies/{company_id}/"
        try:
            keys = await list_objects(prefix)
        except StorageError as exc:
            warn(f"could not list {prefix}: {exc}")
            stats["failed"] += 1
            continue
        for key in keys:
            try:
                await delete_object(key)
                stats["objects"] += 1
            except StorageError as exc:
                warn(f"could not delete {key}: {exc}")
                stats["failed"] += 1
    return stats


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def seed_profile(
    session: AsyncSession,
    profile: dict[str, Any],
    *,
    admin: User | None = None,
) -> dict[str, int]:
    """Walk the profile top to bottom and report what was made.

    validate_profile() runs first, so everything a profile can be refused
    for is refused before the first write. `admin` is the actor; when not
    given, the stand's active admin is looked up and its absence refused.
    """
    validate_profile(profile)
    if admin is None:
        admin = await require_admin(session)

    marker = profile["marker"]
    stats = {
        "staff": 0,
        "companies": 0,
        "products": 0,
        "pictures": 0,
        "picture_variants": 0,
        "attachments": 0,
        "roadmap_items": 0,
        "agents": 0,
        "investors": 0,
        "purchases": 0,
        "instalments": 0,
        "gifts": 0,
    }

    for spec in profile.get("staff", []):
        await ensure_staff(session, profile, spec, admin)
        stats["staff"] += 1
    info(f"staff: {stats['staff']}")

    # KNOWN CEILING -- objects of a project whose seed run fails after its
    # uploads began.
    #   1. Mechanics: the whole run is one transaction, but a storage upload
    #      is not part of it. If the run fails after set_company_media /
    #      set_product_cover / create_attachment / set_roadmap_cover wrote
    #      objects, the rows roll back and the objects stay under
    #      companies/<the rolled-back id>/. The next run creates the company
    #      with a new id, so --reset never finds that prefix.
    #   2. Status: acknowledged by design.
    #   3. Task: P-80, "orphan files in the storage" (technical debt).
    #   4. Trigger: the first seed run that fails after its uploads began
    #      (an [ERROR] line or a traceback in the seed's output after
    #      set_company_media / create_attachment had run), or P-80 leaving
    #      the debt list.
    #   5. Fix: the P-80 sweeper -- reconcile companies/* in the storage
    #      against company_profiles and delete the prefixes with no row.
    #   6. Rejected: a commit per project. It keeps the projects already
    #      finished, and leaves the failing one's objects orphaned exactly
    #      the same way.
    #   Every refusal a profile can earn happens in validate_profile(),
    #   before any upload, so only a storage or database failure mid-run
    #   reaches this.
    products: list[Product] = []
    for company_spec in profile.get("companies", []):
        company = await ensure_company(session, profile, company_spec, admin)
        await ensure_pool(session, company, company_spec["pool"], admin)
        for product_spec in company_spec.get("products", []):
            products.append(
                await ensure_product(
                    session,
                    company,
                    company_spec,
                    product_spec,
                    admin,
                    stats=stats,
                )
            )
        await session.refresh(company)
        stats["pictures"] += await ensure_company_media(
            session, company, company_spec, admin, stats=stats
        )
        stats["attachments"] += await ensure_attachments(
            session, company, company_spec, admin
        )
        stats["roadmap_items"] += await ensure_roadmap(
            session, company, company_spec, admin, stats=stats
        )
        stats["companies"] += 1
        info(f"project {company_spec['key']}: {company.name}")
    stats["products"] = len(products)
    info(
        f"projects: {stats['companies']}, products: {stats['products']}, "
        f"pictures: {stats['pictures']}, "
        f"picture variants: {stats['picture_variants']}, "
        f"attachments: {stats['attachments']}, "
        f"roadmap items: {stats['roadmap_items']} (new this run)"
    )

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
                session, investor, portfolio, profile, admin
            )
            stats["purchases"] += result["purchases"]
            stats["instalments"] += result["instalments"]
            stats["gifts"] += result["gifts"]

    info(
        f"investors: {stats['investors']}, purchases: {stats['purchases']}, "
        f"instalments: {stats['instalments']}, gifts: {stats['gifts']}"
    )
    logger.info("seed_profile_applied", marker=marker, **stats)
    return stats


async def _run_profile(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    marker = profile["marker"]

    factory = get_session_factory()
    async with factory() as session:
        try:
            # Everything that can refuse, before anything is written --
            # the reset included. --reset-only needs neither a valid
            # profile body nor an actor: it deletes by marker alone.
            admin: User | None = None
            if not args.reset_only:
                validate_profile(profile)
                admin = await require_admin(session)
                if profile.get("staff"):
                    await assert_no_live_staff(
                        session,
                        marker,
                        allow_live_staff=args.allow_live_staff,
                        admin=admin,
                    )

            if args.dry_run:
                info(f"profile {args.profile!r}: {profile.get('description')}")
                if not args.reset_only:
                    info(f"marker: {marker}, domain: {mail_domain()}")
                    info(
                        "would seed: "
                        f"{len(profile.get('staff', []))} staff, "
                        f"{len(profile.get('companies', []))} project(s), "
                        f"{len(profile.get('agents', []))} agent(s), "
                        f"{len(profile.get('investors', []))} investor(s)"
                    )
                if args.reset:
                    info("would reset first")
                return 0

            if args.reset:
                company_ids = await seeded_company_ids(session, marker)
                counts = await reset_seed_data(session, marker)
                await session.commit()
                ok(f"reset: {counts}")
                # After the commit: see purge_seeded_objects.
                ok(f"storage: {await purge_seeded_objects(company_ids)}")

            if args.reset_only:
                return 0

            stats = await seed_profile(session, profile, admin=admin)
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

            stats = await ensure_portfolio_count(
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
