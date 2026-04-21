#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed User Portfolio (dev only)
# =============================================================================
#
# Fills a specific user's dashboard with realistic activity:
#   1. Looks up the user by email (from User.credentials.email.email).
#   2. Force-sets kyc_status = approved (dev shortcut -- real users must
#      pass KYC through SumSub).
#   3. Credits active_ledger with a deposit (status=confirmed, reason=
#      "deposit:dev_seed") if the current confirmed balance is below
#      --deposit. Idempotent: a second run with the same --deposit will
#      not double-credit unless the balance has since been spent below
#      the threshold.
#   4. Picks --purchases random ACTIVE products from ACTIVE companies
#      and executes execute_purchase() for each one. Uses the real
#      engine so ledger entries, gifts, and commissions are all
#      written correctly (double-entry intact).
#
# IDEMPOTENCY:
#   Deposit is idempotent by balance floor.
#   Purchases are NOT idempotent -- each run adds N new purchases.
#   Re-running doubles the portfolio; pass --purchases 0 to skip.
#
# SAFETY:
#   This is a dev seed. It ignores the KYC guard in execute_purchase
#   by lifting kyc_status on the user directly. Do NOT run in prod.
#
# REFERRAL CHAIN:
#   The target user's referred_by is left untouched. If it points at
#   Platform (typical for a solo registration), no L1/L2/L3 commissions
#   are generated from these purchases -- that's expected. Agent
#   commissions require a referral tree seeded separately (not part of
#   this script).
#
# USAGE:
#   docker compose exec app python -m scripts.seed_user_portfolio \
#       --email foo@example.com
#
#   docker compose exec app python -m scripts.seed_user_portfolio \
#       --email foo@example.com --deposit 50000000 --purchases 10
#
#   # via management script:
#   cbshome seed-portfolio foo@example.com
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from uuid import UUID

# Ensure the app package is importable when running as a script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import (
    get_active_balance,
    record_active_ledger,
)
from app.modules.products.constants import ProductStatus
from app.modules.products.models import Product
from app.modules.purchases.service import execute_purchase
from app.modules.users.models import KYCStatus, User

logger = structlog.get_logger()

# Terminal colours, same scheme as the other seed scripts.
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


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# $100,000 in cents. Generous on purpose -- the whole point is that a
# dev user should be able to buy multiple products without tripping
# balance checks or burning through the deposit in one go.
DEFAULT_DEPOSIT_CENTS = 10_000_000
DEFAULT_PURCHASES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _find_user_by_email(
    email: str, session: AsyncSession
) -> User | None:
    """Look up a user by credentials.email.email.

    User.email is a property that reads credentials -- we cannot filter
    on it directly. Using the JSONB operator matches what the backend
    does elsewhere (see users/router or tests/helpers).
    """
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _pick_random_products(
    session: AsyncSession, limit: int
) -> list[Product]:
    """Pick up to `limit` ACTIVE products whose company is ACTIVE."""
    stmt = (
        select(Product)
        .join(CompanyProfile, CompanyProfile.id == Product.company_id)
        .where(
            Product.status == ProductStatus.ACTIVE,
            CompanyProfile.status == CompanyStatus.ACTIVE,
        )
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    if not products:
        return []

    # Shuffle in-place and slice so caller can assume up to `limit`
    # distinct products. If fewer than `limit` ACTIVE products exist,
    # we just return all of them -- better than duplicating a single
    # product across the whole run.
    random.shuffle(products)
    return products[:limit]


async def _ensure_kyc_approved(user: User, session: AsyncSession) -> None:
    """Lift kyc_status to approved if it isn't already.

    execute_purchase() raises BadRequestError when kyc_status !=
    approved; dev seed skips SumSub entirely and flips the flag
    in place.
    """
    if user.kyc_status == KYCStatus.APPROVED:
        return
    warn(
        f"User {user.id} kyc_status={user.kyc_status!r} -- "
        f"force-setting to 'approved' for dev seed"
    )
    user.kyc_status = KYCStatus.APPROVED
    await session.flush()


async def _ensure_deposit(
    user: User,
    target_cents: int,
    session: AsyncSession,
) -> int:
    """Top up confirmed active balance to at least `target_cents`.

    Returns the amount actually credited (can be 0 if balance already
    satisfies target). Uses record_active_ledger with status=confirmed
    so the funds are immediately spendable -- no freeze window.

    This is NOT how real deposits work (they go frozen first, then
    confirmed after the chain confirmation window). Dev seed cuts
    that short on purpose.
    """
    balance = await get_active_balance(session, user.id)
    current_confirmed = balance["confirmed"]

    if current_confirmed >= target_cents:
        log(
            f"Balance already at {current_confirmed} cents "
            f"(target {target_cents}) -- skipping deposit"
        )
        return 0

    delta = target_cents - current_confirmed
    await record_active_ledger(
        session,
        user_id=user.id,
        amount_cents=delta,
        status=LedgerStatus.CONFIRMED,
        reason="deposit:dev_seed",
    )
    log(f"Credited {delta} cents (target {target_cents})")
    return delta


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------


async def seed_portfolio(
    email: str,
    deposit_cents: int,
    purchase_count: int,
) -> None:
    """Entry point invoked by main()."""
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            # -- 1. Resolve user --
            user = await _find_user_by_email(email, session)
            if user is None:
                err(f"User not found: {email}")
                sys.exit(1)
            log(f"Target user: {user.id} ({email}), role={user.role}")

            # -- 2. Force-approve KYC --
            await _ensure_kyc_approved(user, session)

            # -- 3. Ensure deposit --
            await _ensure_deposit(user, deposit_cents, session)

            # Commit deposit + KYC before purchases. Purchases need the
            # balance to be visible to the engine's advisory-lock check.
            await session.commit()

            # -- 4. Purchases --
            if purchase_count <= 0:
                log("--purchases 0 -- skipping purchase step")
                return

            products = await _pick_random_products(session, purchase_count)
            if not products:
                warn(
                    "No ACTIVE products found. Run seed_storefront "
                    "first so there is something to buy."
                )
                return

            log(
                f"Picked {len(products)} product(s) for purchase "
                f"(requested {purchase_count})"
            )

            # Re-load user in the same session so engine sees the
            # deposit we just committed on the write session.
            user = await _find_user_by_email(email, session)
            if user is None:
                err("User vanished mid-run")
                sys.exit(1)

            success = 0
            skipped: list[tuple[UUID, str]] = []
            for product in products:
                try:
                    purchases = await execute_purchase(
                        product.id, user, session
                    )
                    await session.commit()
                    log(
                        f"  + {product.name!r} -- "
                        f"{len(purchases)} purchase row(s)"
                    )
                    success += 1
                except Exception as exc:  # noqa: BLE001 -- dev tool
                    await session.rollback()
                    # Re-load user after rollback; engine advisory lock
                    # invalidates the bound instance.
                    user = await _find_user_by_email(email, session)
                    skipped.append((product.id, str(exc)))

            log(
                f"Done: {success} purchase(s) completed, "
                f"{len(skipped)} skipped"
            )
            for pid, reason in skipped:
                warn(f"  skipped {pid}: {reason}")

            logger.info(
                "user_portfolio_seeded",
                user_id=str(user.id) if user else None,
                email=email,
                deposit_cents=deposit_cents,
                purchases_requested=purchase_count,
                purchases_completed=success,
                purchases_skipped=len(skipped),
            )

        finally:
            await dispose_engine()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a specific user's dashboard with deposit + purchases (dev only).",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Target user email (must already exist in the users table).",
    )
    parser.add_argument(
        "--deposit",
        type=int,
        default=DEFAULT_DEPOSIT_CENTS,
        help=(
            "Target confirmed active balance in cents "
            f"(default {DEFAULT_DEPOSIT_CENTS})."
        ),
    )
    parser.add_argument(
        "--purchases",
        type=int,
        default=DEFAULT_PURCHASES,
        help=(
            "Number of random products to buy "
            f"(default {DEFAULT_PURCHASES}). Pass 0 to skip."
        ),
    )
    args = parser.parse_args()

    if args.deposit < 0:
        err("--deposit cannot be negative")
        sys.exit(1)
    if args.purchases < 0:
        err("--purchases cannot be negative")
        sys.exit(1)

    asyncio.run(
        seed_portfolio(
            email=args.email,
            deposit_cents=args.deposit,
            purchase_count=args.purchases,
        )
    )


if __name__ == "__main__":
    main()
