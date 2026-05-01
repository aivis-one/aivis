#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed Test Accounts (Sprint 4.3 -- dev only)
# =============================================================================
#
# Creates four ready-to-login accounts for manual frontend / E2E testing:
#
#   investor@test.cbshome.dev   -- KYC approved, $5 000 balance
#   company@test.cbshome.dev    -- owns "Test Company [Auto]" + active pool
#                                  + 2 products + 1 installment template
#   agent@test.cbshome.dev      -- approved AgentApplication, has a
#                                  referral link with fixed code TEST_AGENT_LINK
#   staff@test.cbshome.dev      -- StaffProfile with all permissions True
#
# All four use the same password as the rest of the dev seeds:
#   seedpass123
#
# Why a separate script (vs extending seed_storefront.py):
#   These accounts persist across reseeds of the storefront and serve a
#   different purpose -- testing flows by logging in as each role rather
#   than populating browseable catalogue data. The "Test Company [Auto]"
#   they own is intentionally separate from the storefront companies
#   (IPI AG, etc.) so a wipe of one does not affect the other.
#
# IDEMPOTENCY:
#   Existence checks by email (users), by name (company/products/
#   installments), by code (referral link), by company_id (pool).
#   Re-running without --reset is a no-op for anything already present.
#
# USAGE:
#   docker compose exec app python -m scripts.seed_test_accounts
#   docker compose exec app python -m scripts.seed_test_accounts --reset
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path

# Ensure app package is importable when running as standalone script.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import dispose_engine, get_session_factory
from app.core.logging import setup_logging
from app.modules.agent_applications.constants import AgentApplicationStatus
from app.modules.agent_applications.models import AgentApplication
from app.modules.auth.service import get_platform_user_id, hash_password
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.pools.models import OptionPool
from app.modules.products.constants import ProductStatus
from app.modules.products.models import Product, ProductInstallment
from app.modules.purchases.models import Purchase
from app.modules.referrals.models import ReferralAttribution, ReferralLink
from app.modules.staff.constants import VALID_PERMISSION_KEYS
from app.modules.staff.models import StaffProfile
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole

logger = structlog.get_logger()

# Terminal colours -- match seed_storefront / seed_admin.
G = "\033[0;32m"
Y = "\033[1;33m"
R = "\033[0;31m"
N = "\033[0m"


def log(msg: str) -> None:
    print(f"{G}[SEED-TEST]{N} {msg}")


def warn(msg: str) -> None:
    print(f"{Y}[WARN]{N} {msg}")


def err(msg: str) -> None:
    print(f"{R}[ERROR]{N} {msg}")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Password shared with seed_storefront.py for consistency in dev fixtures.
TEST_PASSWORD = "seedpass123"  # noqa: S105 -- dev-only

INVESTOR_EMAIL = "investor@test.cbshome.dev"
COMPANY_OWNER_EMAIL = "company@test.cbshome.dev"
AGENT_EMAIL = "agent@test.cbshome.dev"
STAFF_EMAIL = "staff@test.cbshome.dev"

ALL_TEST_EMAILS = (
    INVESTOR_EMAIL,
    COMPANY_OWNER_EMAIL,
    AGENT_EMAIL,
    STAFF_EMAIL,
)

# Investor starting balance -- enough to exercise both packs of the test
# company and an installment plan without running out.
INVESTOR_BALANCE_CENTS = 5_000_00  # $5 000

# Company owned by company@test.cbshome.dev. Name is intentionally distinct
# from any storefront company so wipes don't collide.
TEST_COMPANY_NAME = "Test Company [Auto]"
TEST_COMPANY_PRICE_CENTS = 100  # $1.00 per option
TEST_COMPANY_TOTAL_SUPPLY = 1_000_000
TEST_COMPANY_SHARES_PER_OPTION = 1

TEST_PRODUCT_STARTER_NAME = "Test Starter Pack"
TEST_PRODUCT_STARTER_PACKAGE_SIZE = 100

TEST_PRODUCT_INVESTOR_NAME = "Test Investor Pack"
TEST_PRODUCT_INVESTOR_PACKAGE_SIZE = 1000

TEST_INSTALLMENT_NAME = "3 months -- test plan"

# Fixed referral code for predictable links in test URLs.
AGENT_REFERRAL_CODE = "TEST_AGENT_LINK"


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


async def _reset(session: AsyncSession) -> None:
    """Remove everything this script creates, in FK-safe order."""
    log("Reset: removing previously-seeded test accounts")

    # Resolve user IDs by email so we can clean their dependents first.
    user_ids: list = []
    for email in ALL_TEST_EMAILS:
        stmt = select(User.id).where(
            User.credentials["email"]["email"].as_string() == email
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            user_ids.append(row)

    # Resolve test company id -- needed for pool/products/purchases cascade.
    company_stmt = select(CompanyProfile.id).where(
        CompanyProfile.name == TEST_COMPANY_NAME
    )
    test_company_id = (
        await session.execute(company_stmt)
    ).scalar_one_or_none()

    # Resolve test product ids.
    test_product_ids: list = []
    if test_company_id is not None:
        prod_stmt = select(Product.id).where(
            Product.company_id == test_company_id
        )
        test_product_ids = [
            row[0]
            for row in (await session.execute(prod_stmt)).all()
        ]

    # 1. Purchases against test products (defensive -- tests may have left some).
    if test_product_ids:
        await session.execute(
            delete(Purchase).where(Purchase.product_id.in_(test_product_ids))
        )

    # 2. Installment templates of test products.
    if test_product_ids:
        await session.execute(
            delete(ProductInstallment).where(
                ProductInstallment.product_id.in_(test_product_ids)
            )
        )

    # 3. Test products.
    if test_product_ids:
        await session.execute(
            delete(Product).where(Product.id.in_(test_product_ids))
        )

    # 4. OptionPool of the test company.
    if test_company_id is not None:
        await session.execute(
            delete(OptionPool).where(OptionPool.company_id == test_company_id)
        )

    # 5. Test company profile.
    if test_company_id is not None:
        await session.execute(
            delete(CompanyProfile).where(CompanyProfile.id == test_company_id)
        )

    # 6. Referral attributions and links owned by the test agent.
    if user_ids:
        # Agent links -> attributions FK references them; clean attributions
        # that point to those links first.
        link_ids_stmt = select(ReferralLink.id).where(
            ReferralLink.agent_id.in_(user_ids)
        )
        link_ids = [
            row[0]
            for row in (await session.execute(link_ids_stmt)).all()
        ]
        if link_ids:
            await session.execute(
                delete(ReferralAttribution).where(
                    ReferralAttribution.referral_link_id.in_(link_ids)
                )
            )
            await session.execute(
                delete(ReferralLink).where(ReferralLink.id.in_(link_ids))
            )

    # 7. Agent applications submitted by the test agent.
    if user_ids:
        await session.execute(
            delete(AgentApplication).where(
                AgentApplication.user_id.in_(user_ids)
            )
        )

    # 8. StaffProfile for the test staff user.
    if user_ids:
        await session.execute(
            delete(StaffProfile).where(StaffProfile.user_id.in_(user_ids))
        )

    # 9. The four test users themselves.
    for email in ALL_TEST_EMAILS:
        await session.execute(
            delete(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )

    await session.commit()
    log("Reset: done")


# ---------------------------------------------------------------------------
# User creation primitives
# ---------------------------------------------------------------------------


async def _get_user_by_email(
    session: AsyncSession, email: str
) -> User | None:
    """Return the User with this credentials.email or None."""
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _make_user(
    *,
    email: str,
    role: UserRole,
    referred_by,  # UUID
    onboarding_step: OnboardingStep,
    kyc_status: KYCStatus,
    first_name: str,
    last_name: str,
) -> User:
    """Construct a User row with the given role / onboarding shape."""
    return User(
        role=role,
        is_active=True,
        onboarding_step=onboarding_step,
        kyc_status=kyc_status,
        referred_by=referred_by,
        credentials={
            "email": {
                "email": email,
                "password_hash": hash_password(TEST_PASSWORD),
                "verified": True,
            },
        },
        profile={
            "first_name": first_name,
            "last_name": last_name,
            "country": "DE",
        },
        language="en",
    )


# ---------------------------------------------------------------------------
# 1. Investor
# ---------------------------------------------------------------------------


async def _ensure_investor(
    session: AsyncSession,
    *,
    platform_user_id,  # UUID
) -> User:
    """Return the test investor, creating it (with balance + KYC) if missing."""
    existing = await _get_user_by_email(session, INVESTOR_EMAIL)
    if existing is not None:
        return existing

    investor = _make_user(
        email=INVESTOR_EMAIL,
        role=UserRole.INVESTOR,
        referred_by=platform_user_id,
        onboarding_step=OnboardingStep.ONBOARDING_COMPLETE,
        kyc_status=KYCStatus.APPROVED,
        first_name="Test",
        last_name="Investor",
    )
    session.add(investor)
    await session.flush()

    # Fund the investor's active balance so they can purchase products
    # immediately on first login.
    await record_active_ledger(
        session,
        user_id=investor.id,
        amount_cents=INVESTOR_BALANCE_CENTS,
        status=LedgerStatus.CONFIRMED,
        reason="test:investor_seed_balance",
    )

    log(f"  Investor created: {INVESTOR_EMAIL} (+${INVESTOR_BALANCE_CENTS // 100} balance)")
    return investor


# ---------------------------------------------------------------------------
# 2. Company owner + company + pool + products + installment
# ---------------------------------------------------------------------------


async def _ensure_company_owner(
    session: AsyncSession,
    *,
    platform_user_id,  # UUID
) -> User:
    """Return the company owner User, creating it if missing."""
    existing = await _get_user_by_email(session, COMPANY_OWNER_EMAIL)
    if existing is not None:
        return existing

    owner = _make_user(
        email=COMPANY_OWNER_EMAIL,
        role=UserRole.COMPANY,
        referred_by=platform_user_id,
        onboarding_step=OnboardingStep.ROLE_SELECTED,
        kyc_status=KYCStatus.NOT_STARTED,
        first_name="Test",
        last_name="Company",
    )
    session.add(owner)
    await session.flush()
    log(f"  Company owner created: {COMPANY_OWNER_EMAIL}")
    return owner


async def _ensure_company(
    session: AsyncSession,
    *,
    owner: User,
) -> CompanyProfile:
    """Return the test CompanyProfile, creating it if missing."""
    stmt = select(CompanyProfile).where(
        CompanyProfile.name == TEST_COMPANY_NAME
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    profile = CompanyProfile(
        user_id=owner.id,
        name=TEST_COMPANY_NAME,
        description=(
            "Auto-generated company used by manual frontend testing. "
            "Owned by company@test.cbshome.dev."
        ),
        logo_url=None,
        cover_url=None,
        promo_video_url=None,
        presentation_url=None,
        price_per_unit_cents=TEST_COMPANY_PRICE_CENTS,
        # Sprint 4.3: tokenization parameters.
        total_supply=TEST_COMPANY_TOTAL_SUPPLY,
        shares_per_option=TEST_COMPANY_SHARES_PER_OPTION,
        # Distribution: 80% company / 10% L1 / 5% L2 / 5% L3 -- exercises
        # the agent payout chain when the test agent's referral link is used.
        distribution_config={
            "company_pct": 0.80,
            "agent_levels": [0.10, 0.05, 0.05],
        },
        status=CompanyStatus.ACTIVE,
    )
    session.add(profile)
    await session.flush()
    log(f"  Company created: {TEST_COMPANY_NAME}")
    return profile


async def _ensure_pool(
    session: AsyncSession,
    *,
    company: CompanyProfile,
) -> OptionPool:
    """Return the active OptionPool for the test company, creating it if missing."""
    stmt = select(OptionPool).where(
        OptionPool.company_id == company.id,
        OptionPool.status == "active",
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    pool = OptionPool(
        company_id=company.id,
        equity_percent=Decimal("100.0000"),
        total_options=company.total_supply,
        status="active",
    )
    session.add(pool)
    await session.flush()
    log(f"  Pool created: 100% / {company.total_supply:,} options")
    return pool


async def _ensure_products(
    session: AsyncSession,
    *,
    company: CompanyProfile,
    pool: OptionPool,
) -> tuple[Product, Product]:
    """Return (starter_product, investor_product), creating missing ones."""
    products: dict[str, Product] = {}
    specs = (
        (TEST_PRODUCT_STARTER_NAME, TEST_PRODUCT_STARTER_PACKAGE_SIZE, None),
        (
            TEST_PRODUCT_INVESTOR_NAME,
            TEST_PRODUCT_INVESTOR_PACKAGE_SIZE,
            # Volume bonus on the bigger pack so the investor view has
            # something to render in the bonus column.
            {"bonuses": [{
                "condition": "always",
                "bonus_units_percent": 5,
                "funded_by": "company",
            }]},
        ),
    )

    for name, package_size, purchase_config in specs:
        stmt = select(Product).where(Product.name == name)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            products[name] = existing
            continue

        product = Product(
            company_id=company.id,
            pool_id=pool.id,
            name=name,
            description=f"Auto-generated test product ({package_size} options/pack).",
            package_size=package_size,
            price_per_unit_cents=company.price_per_unit_cents,
            purchase_config=purchase_config,
            status=ProductStatus.ACTIVE,
        )
        session.add(product)
        await session.flush()
        products[name] = product
        log(f"  Product created: {name} ({package_size} opts)")

    return (
        products[TEST_PRODUCT_STARTER_NAME],
        products[TEST_PRODUCT_INVESTOR_NAME],
    )


async def _ensure_installment(
    session: AsyncSession,
    *,
    product: Product,
) -> ProductInstallment:
    """Return one installment template for the given product, creating it if missing.

    Plan: 3 equal tranches over 33% / 33% / 34% of options. Total amount
    matches the product's full price.
    """
    stmt = select(ProductInstallment).where(
        ProductInstallment.product_id == product.id,
        ProductInstallment.name == TEST_INSTALLMENT_NAME,
        ProductInstallment.is_deleted.is_(False),
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    total = product.package_size * product.price_per_unit_cents
    per_amount = total // 3
    plan = ProductInstallment(
        product_id=product.id,
        name=TEST_INSTALLMENT_NAME,
        plan_config={
            "tranches": [
                {"amount_cents": per_amount, "units_percent": 33},
                {"amount_cents": per_amount, "units_percent": 33},
                # Last tranche absorbs rounding remainder (matches
                # seed_storefront _tranches() semantics).
                {
                    "amount_cents": total - per_amount * 2,
                    "units_percent": 34,
                },
            ],
            "bonus_units": 0,
            "agent_bonus_units": 0,
        },
        is_deleted=False,
    )
    session.add(plan)
    await session.flush()
    log(f"  Installment template created: {TEST_INSTALLMENT_NAME}")
    return plan


# ---------------------------------------------------------------------------
# 3. Agent
# ---------------------------------------------------------------------------


async def _ensure_agent(
    session: AsyncSession,
    *,
    platform_user_id,  # UUID
    staff_reviewer_id,  # UUID -- used as reviewed_by on the approved application
) -> User:
    """Return the test agent (registered + approved + linked), creating it if missing."""
    existing = await _get_user_by_email(session, AGENT_EMAIL)
    if existing is not None:
        return existing

    agent = _make_user(
        email=AGENT_EMAIL,
        role=UserRole.AGENT,
        referred_by=platform_user_id,
        onboarding_step=OnboardingStep.ONBOARDING_COMPLETE,
        kyc_status=KYCStatus.APPROVED,
        first_name="Test",
        last_name="Agent",
    )
    session.add(agent)
    await session.flush()

    # Approved AgentApplication for compliance history. status_changed via
    # staff workflow normally goes through staff_service; here we set the
    # terminal state directly (dev fixture, no audit trail required).
    application = AgentApplication(
        user_id=agent.id,
        status=AgentApplicationStatus.APPROVED,
        reviewed_at=datetime.now(UTC),
        reviewed_by=staff_reviewer_id,
    )
    session.add(application)

    # Referral link with a fixed code so test URLs stay predictable.
    link = ReferralLink(agent_id=agent.id, code=AGENT_REFERRAL_CODE)
    session.add(link)
    await session.flush()

    log(f"  Agent created: {AGENT_EMAIL} (link code: {AGENT_REFERRAL_CODE})")
    return agent


# ---------------------------------------------------------------------------
# 4. Staff
# ---------------------------------------------------------------------------


async def _ensure_staff(
    session: AsyncSession,
    *,
    platform_user_id,  # UUID
) -> User:
    """Return the test staff user with all permissions, creating it if missing."""
    existing = await _get_user_by_email(session, STAFF_EMAIL)
    if existing is not None:
        return existing

    staff = _make_user(
        email=STAFF_EMAIL,
        role=UserRole.STAFF,
        referred_by=platform_user_id,
        onboarding_step=OnboardingStep.ROLE_SELECTED,
        kyc_status=KYCStatus.APPROVED,
        first_name="Test",
        last_name="Staff",
    )
    session.add(staff)
    await session.flush()

    # All permissions True -- this account doubles as a stand-in admin
    # for the dashboard / management screens.
    profile = StaffProfile(
        user_id=staff.id,
        permissions={key: True for key in VALID_PERMISSION_KEYS},
        is_active=True,
    )
    session.add(profile)
    await session.flush()

    log(f"  Staff created: {STAFF_EMAIL} (all permissions)")
    return staff


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def seed_test_accounts(reset: bool) -> None:
    """Main entry point -- create the four test accounts."""
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            if reset:
                await _reset(session)

            platform_user_id = await get_platform_user_id(session)

            # Order matters: staff is created first so the agent
            # application can list staff as the reviewer. (Investor and
            # company owner have no inter-dependencies -- they could
            # come in any order.)
            log("Ensuring staff account")
            staff = await _ensure_staff(
                session, platform_user_id=platform_user_id
            )

            log("Ensuring investor account")
            await _ensure_investor(
                session, platform_user_id=platform_user_id
            )

            log("Ensuring company owner + company + pool + products + installment")
            owner = await _ensure_company_owner(
                session, platform_user_id=platform_user_id
            )
            company = await _ensure_company(session, owner=owner)
            pool = await _ensure_pool(session, company=company)
            starter, investor_pack = await _ensure_products(
                session, company=company, pool=pool
            )
            await _ensure_installment(session, product=investor_pack)

            log("Ensuring agent account")
            await _ensure_agent(
                session,
                platform_user_id=platform_user_id,
                staff_reviewer_id=staff.id,
            )

            await session.commit()
            log("Test accounts seed complete")
            log("")
            log("Login credentials (password: seedpass123):")
            log(f"  investor: {INVESTOR_EMAIL}")
            log(f"  company:  {COMPANY_OWNER_EMAIL}")
            log(f"  agent:    {AGENT_EMAIL}  (link: {AGENT_REFERRAL_CODE})")
            log(f"  staff:    {STAFF_EMAIL}")

        except Exception as exc:
            await session.rollback()
            err(f"Seed failed: {exc}")
            raise
        finally:
            await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed dev test accounts (investor / company / agent / staff)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove previously-seeded test accounts before seeding",
    )
    args = parser.parse_args()

    asyncio.run(seed_test_accounts(reset=args.reset))


if __name__ == "__main__":
    main()
