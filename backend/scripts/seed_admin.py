#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed Admin User
# =============================================================================
#
# Creates the first admin staff user if none exists.
# Admin = staff with ALL permissions True.
#
# USAGE:
#   python scripts/seed_admin.py --email admin@cbshome.org --password <pw>
#
# RULES:
#   - Idempotent: skips if any admin (all-True permissions) exists
#   - Creates User (role=staff) + StaffProfile (all permissions True)
#   - Called by install_cbshome.sh after seed_platform.py
# =============================================================================

import argparse
import asyncio
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
from app.modules.auth.service import hash_password
from app.modules.staff.constants import VALID_PERMISSION_KEYS, is_admin
from app.modules.staff.models import StaffProfile
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole

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


async def seed_admin(email: str, password: str) -> None:
    """Create admin user if no admin exists yet."""
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            # Check if any admin already exists.
            stmt = select(StaffProfile)
            result = await session.execute(stmt)
            profiles = result.scalars().all()

            for profile in profiles:
                if is_admin(profile.permissions):
                    warn(f"Admin already exists: user_id={profile.user_id}")
                    return

            # Create admin user.
            password_hash = hash_password(password)
            admin = User(
                role=UserRole.STAFF,
                is_active=True,
                onboarding_step=OnboardingStep.ROLE_SELECTED,
                kyc_status=KYCStatus.APPROVED,
                credentials={
                    "email": {
                        "email": email,
                        "password_hash": password_hash,
                    },
                },
                profile={"first_name": "Admin", "last_name": "CBSHOME"},
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

        except Exception as exc:
            await session.rollback()
            err(f"Failed to create admin user: {exc}")
            raise
        finally:
            await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed admin user")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()

    asyncio.run(seed_admin(args.email, args.password))


if __name__ == "__main__":
    main()
