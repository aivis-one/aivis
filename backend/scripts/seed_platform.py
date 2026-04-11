#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed Platform System User
# =============================================================================
#
# Creates the Platform system user (role=platform) if it does not exist.
# This user is the double-entry anchor for all incoming investor payments.
#
# RULES:
#   - Created once at first deploy, never recreated or deleted
#   - Identified by role=platform (no is_system field)
#   - Never logs in (blocked in get_current_user() dependency)
#   - Never appears in user lists (filtered by role=platform)
#   - referred_by = self (Platform is its own referrer)
#
# USAGE:
#   python scripts/seed_platform.py          -- idempotent, safe to re-run
#
# Called automatically by install_cbshome.sh after migrations.
# =============================================================================

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Ensure app package is importable when running as standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import select

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.users.models import User, UserRole, OnboardingStep, KYCStatus

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


async def seed_platform() -> None:
    """Create Platform user if not already present."""
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            # Check if platform user already exists.
            result = await session.execute(
                select(User).where(User.role == UserRole.PLATFORM)
            )
            existing = result.scalar_one_or_none()

            if existing is not None:
                warn(f"Platform user already exists: {existing.id}")
                return

            # Pre-generate UUID so referred_by can reference self.
            platform_id = uuid4()

            # Create Platform user.
            platform = User(
                id=platform_id,
                role=UserRole.PLATFORM,
                is_active=True,
                onboarding_step=OnboardingStep.ROLE_SELECTED,
                kyc_status=KYCStatus.APPROVED,
                referred_by=platform_id,
                credentials={},
                profile={"first_name": "Platform", "last_name": "System"},
                language="en",
            )
            session.add(platform)
            await session.commit()

            log(f"Platform user created: {platform.id}")
            logger.info("platform_user_created", user_id=str(platform.id))

        except Exception as exc:
            await session.rollback()
            err(f"Failed to create Platform user: {exc}")
            raise
        finally:
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed_platform())
