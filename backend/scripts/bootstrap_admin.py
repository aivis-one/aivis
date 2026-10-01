#!/usr/bin/env python3
# =============================================================================
# AIVIS.ONE Backend -- `aivis bootstrap-admin <email>` (H30 P-118)
# =============================================================================
#
# Makes the already registered, verified user with this address the first
# admin of the box. Runs on APP_ENV=production -- it is the production
# path to the first admin; `aivis seed` is the test stands' one and
# refuses production.
#
# This file only reads the argument, runs the transaction and reports. The
# decisions and the writes live in app/modules/staff/bootstrap.py, where
# the suite tests them.
#
# Exit codes: 0 -- promoted; 1 -- refused, nothing written; 2 -- usage.
# =============================================================================

import asyncio
import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Every model registered before the first query: the promotion writes the
# audit log and the support outbox, whose mappers reference models this
# script never names. Importing the application registers all of them.
import app.main  # noqa: E402, F401
from app.core.database import dispose_engine, get_session_factory  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.modules.staff.bootstrap import (  # noqa: E402
    BootstrapRefusedError,
    bootstrap_first_admin,
)

USAGE = "Usage: aivis bootstrap-admin <email of a registered, verified user>"


async def run(email: str) -> int:
    setup_logging()
    factory = get_session_factory()
    try:
        async with factory() as session:
            try:
                user = await bootstrap_first_admin(session, email)
                await session.commit()
            except BootstrapRefusedError as exc:
                await session.rollback()
                print(f"Refused: {exc}", file=sys.stderr)
                return 1
            print(f"Made admin: {user.email} ({user.id})")
            return 0
    finally:
        await dispose_engine()


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].strip():
        print(USAGE, file=sys.stderr)
        return 2
    return asyncio.run(run(argv[0]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
