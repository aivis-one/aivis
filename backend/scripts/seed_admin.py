#!/usr/bin/env python3
# =============================================================================
# AIVIS.ONE Backend -- Seed Admin User
# =============================================================================
#
# Creates the first admin staff user if none exists.
# Admin = staff with ALL permissions True.
#
# USAGE:
#   ADMIN_PASSWORD=secret python scripts/seed_admin.py --email admin@aivis.one
#   python scripts/seed_admin.py --email admin@aivis.one  (prompts twice)
#   python scripts/seed_admin.py --email admin@aivis.one --reset-password
#
# SECURITY:
#   Password read from ADMIN_PASSWORD env var (preferred for automation)
#   or interactive getpass prompt. Never passed as CLI argument to avoid
#   exposure in ps aux, shell history, and docker logs.
#
# WHY THE PROMPT ASKS TWICE (2026-08-18).
#   It asked ONCE, blind, with no confirmation, and the very first human
#   ever to run this script mistyped it. The hash was written silently and
#   there was no way back: the create path refuses when an admin already
#   exists, the flag set was --email ONLY, and email carries a UNIQUE
#   index -- so re-running, and running with another address, both failed.
#   A tool that can mint a credential and cannot reset it is not
#   idempotent, it is ONE-WAY. Hence --reset-password.
#
# RULES:
#   - Idempotent: skips if any admin (all-True permissions) exists
#   - --reset-password: sets a new hash on the EXISTING admin at --email
#   - Creates User (role=staff) + StaffProfile (all permissions True)
#   - NOT called by install_aivis.sh or the aivis CLI -- nothing runs this
#     file, which is why two bugs lived in it until it was first executed
# =============================================================================

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

# Ensure app package is importable when running as standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import select

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.auth.service import get_platform_user_id, hash_password
from app.modules.staff.constants import VALID_PERMISSION_KEYS, is_admin
from app.modules.staff.models import StaffProfile
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole
# Register referral_links in Base.metadata so User.referred_by_link_id's FK
# resolves when a User is flushed on a fresh DB. Import-only.
from app.modules.referrals.models import ReferralLink  # noqa: F401

logger = structlog.get_logger()

# Terminal colors.
G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[SEED]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


def _get_password(confirm_label: str = "Admin password") -> str:
    """Read the password from ADMIN_PASSWORD, else prompt twice and compare.

    The env var path is unconfirmed on purpose: it is the automation route,
    the value is already fixed by the caller, and there is nothing to typo
    interactively. The INTERACTIVE path is the one that locked an owner out.
    """
    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if password:
        return password

    for _ in range(3):
        first = getpass.getpass(f"{confirm_label}: ")
        if not first:
            err("Password is required")
            continue
        second = getpass.getpass(f"{confirm_label} (again): ")
        if first == second:
            return first
        err("Passwords do not match -- try again.")
    err("Too many mismatched attempts.")
    sys.exit(1)


async def _reset_password(session, email: str, password: str) -> bool:
    """Set a new password hash on the existing admin at `email`.

    Scoped by email rather than "the first admin found" so the operation
    names its target. Returns False (and explains) when there is nothing
    to reset -- an unknown address, or an address that is not an admin.
    """
    email_lower = email.strip().lower()
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email_lower
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        err(f"No user with email {email_lower}")
        return False

    profile = (
        await session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if profile is None or not is_admin(profile.permissions):
        err(f"{email_lower} exists but is not an admin -- refusing to touch it")
        return False

    # credentials is a JSON column; mutating the dict in place does not mark
    # the attribute dirty, so rebuild and reassign it.
    creds = dict(user.credentials or {})
    email_creds = dict(creds.get("email", {}))
    email_creds["password_hash"] = await hash_password(password)
    email_creds["verified"] = True
    creds["email"] = email_creds
    user.credentials = creds

    # An admin minted by a seeder has no onboarding funnel to walk. Left at
    # ROLE_SELECTED the router guard bounces every sign-in to /onboarding/kyc
    # (guards.ts ONBOARDING_REDIRECTS has no role exemption), so the cabinet
    # is reachable only through the KYC + docs screens.
    user.onboarding_step = OnboardingStep.ONBOARDING_COMPLETE

    await session.commit()
    log(f"Password reset for admin {email_lower} (user_id={user.id})")
    logger.info("admin_password_reset", user_id=str(user.id), email=email_lower)
    return True


async def seed_admin(email: str, password: str, reset: bool = False) -> bool:
    """Create the admin user, or reset the existing one's password.

    Returns True on success. The exit code is applied by main() rather than
    here: raising SystemExit inside the try/finally would unwind through the
    session teardown for a case that is an ordinary refusal, not an error.
    """
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            if reset:
                return await _reset_password(session, email, password)

            # Check if any admin already exists.
            stmt = select(StaffProfile)
            result = await session.execute(stmt)
            profiles = result.scalars().all()

            for profile in profiles:
                if is_admin(profile.permissions):
                    warn(f"Admin already exists: user_id={profile.user_id}")
                    warn("To set a new password on it, re-run with --reset-password")
                    return True

            # Create admin user.
            #
            # referred_by is NOT NULL BY DESIGN -- "every user has a
            # referrer, the Platform user references itself" (migration
            # 0014, users/models.py). Omitting it raises
            # NotNullViolationError at flush, which is exactly what this
            # script did on every run until 2026-08-18. It was never
            # caught because nothing runs it: it is wired into neither
            # the `aivis` CLI nor the installer, so the only way to
            # execute it is by hand. seed_test_accounts.py has always
            # passed referred_by=platform_user_id; this now matches.
            platform_user_id = await get_platform_user_id(session)
            password_hash = await hash_password(password)
            admin = User(
                role=UserRole.STAFF,
                is_active=True,
                # ONBOARDING_COMPLETE, not ROLE_SELECTED: guards.ts redirects
                # any step present in ONBOARDING_REDIRECTS and exempts no
                # role, so ROLE_SELECTED sends every admin sign-in to
                # /onboarding/kyc. A seeded admin has no funnel to walk.
                # This is a DELIBERATE divergence from seed_test_accounts.py,
                # which sets ROLE_SELECTED for its staff account and reaches
                # the cabinet only via the idempotent /kyc/advance hotfix.
                onboarding_step=OnboardingStep.ONBOARDING_COMPLETE,
                kyc_status=KYCStatus.APPROVED,
                referred_by=platform_user_id,
                credentials={
                    "email": {
                        "email": email,
                        # Nothing on the LOGIN path reads `verified`
                        # (auth/service.py login_email checks existence,
                        # password, role != PLATFORM, is_active -- measured).
                        # It is set because the verify/resend endpoints raise
                        # "Email is already verified" off it, so an unset flag
                        # leaves a seeded admin able to be nagged to verify an
                        # address nobody will ever send mail to.
                        "verified": True,
                        "password_hash": password_hash,
                    },
                },
                profile={"first_name": "Admin", "last_name": "AIVIS.ONE"},
                language="en",
            )
            session.add(admin)
            await session.flush()

            # Create StaffProfile with full permissions.
            all_true = {key: True for key in VALID_PERMISSION_KEYS}
            profile = StaffProfile(
                user_id=admin.id,
                permissions=all_true,
                is_active=True,
            )
            session.add(profile)
            await session.commit()

            log(f"Admin user created: {admin.id} ({email})")
            logger.info(
                "admin_user_created",
                user_id=str(admin.id),
                email=email,
            )
            return True

        except Exception as exc:
            await session.rollback()
            err(f"Failed to create admin user: {exc}")
            raise
        finally:
            await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed admin user")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Set a new password on the EXISTING admin at --email",
    )
    args = parser.parse_args()

    label = "New admin password" if args.reset_password else "Admin password"
    password = _get_password(label)
    if not password:
        err("Password is required")
        sys.exit(1)

    if not asyncio.run(seed_admin(args.email, password, reset=args.reset_password)):
        sys.exit(1)


if __name__ == "__main__":
    main()
