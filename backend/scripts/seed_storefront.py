#!/usr/bin/env python3
# =============================================================================
# AIVIS.ONE Backend -- Seed Storefront (Phase F4.1 -- dev only)
# =============================================================================
#
# COMPANIES / PRODUCTS / INSTALLMENTS are intentionally EMPTY (owner
# 2026-07-25: every demo tenant was fictional test fixture data and has
# been removed; the owner supplies a real company set as a separate,
# later task). An empty storefront is the expected result of running
# this script until then -- not a bug. The orchestration below and the
# _svg_logo / _bonus / _tranches helpers are unchanged and data-driven,
# so re-populating the three collections is enough to seed real data
# again; nothing else in this file needs to change.
#
# LOGOS:
#   Inline SVG data-URIs with the company's initials on a coloured
#   background. No network dependency, zero repo bytes beyond this
#   file, compatible with the frontend CSP (`img-src 'self' data:`).
#
# COVERS:
#   All cover_url = None -- the UI falls back to the logo, then to
#   the Building icon. Cover photos need a CSP change and real
#   assets, out of scope for dev seeds.
#
# SOLD_UNITS:
#   Every seeded product ships fully available -- no Purchase rows
#   injected. The backend currently conflates `Product.units` with
#   both "package size" and "available inventory", and `sold_units`
#   is COUNT(Purchase), not SUM. Until TD-F05 fixes the share-pool
#   model properly (introducing Company.total_shares_issued +
#   Product.package_size + computed available_packages), any fake
#   sold-out data here would only misrepresent a broken model.
#   Treat this script as decorative: it fills empty screens with
#   realistic names / prices / installments. Purchase-flow and
#   availability logic are validated elsewhere.
#
# IDEMPOTENCY:
#   Re-running the script without --reset is a no-op for anything
#   that already exists. Existence is checked by name (companies,
#   products, installments) or by email (users). --reset removes
#   everything the script seeded (by exact name / email match) and
#   starts clean.
#
# USAGE:
#   docker compose exec app python -m scripts.seed_storefront
#   docker compose exec app python -m scripts.seed_storefront --reset
# =============================================================================

from __future__ import annotations

import argparse
import base64
import asyncio
import sys
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
from app.modules.auth.service import get_platform_user_id, hash_password
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from app.modules.pools.models import OptionPool
from app.modules.products.constants import ProductStatus
from app.modules.products.models import Product, ProductInstallment
from app.modules.purchases.models import Purchase
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole
# Register referral_links in Base.metadata so User.referred_by_link_id's FK
# resolves when a User is flushed on a fresh DB. Import-only.
from app.modules.referrals.models import ReferralLink  # noqa: F401

logger = structlog.get_logger()

# Terminal colours matched to seed_admin.py style.
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
# Helpers
# ---------------------------------------------------------------------------


SEED_PASSWORD = "seedpass123"  # noqa: S105 -- dev-only fixture password


def _svg_logo(initials: str, bg: str) -> str:
    """Inline SVG data-URI. Square 200x200, initials on a coloured
    background. Viewable inline anywhere, no external fetch.

    base64 rather than utf8 -- avoids the pitfalls of escaping
    spaces / quotes / < > inside a CSS url() token across browsers.
    """
    # Keep initials to three chars max so they fit the viewBox.
    label = initials[:3].upper()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        f'<rect width="200" height="200" rx="24" fill="{bg}"/>'
        f'<text x="100" y="100" font-family="Arial, sans-serif" '
        f'font-size="72" font-weight="700" fill="#ffffff" '
        f'text-anchor="middle" dominant-baseline="central">'
        f"{label}</text></svg>"
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

# Company name -> seed data. Prices in cents.
# The slug is used for the owner user's email; must be unique per company.
COMPANIES: list[dict] = []  # type: ignore[type-arg]


def _bonus(pct: float, funded_by: str = "company") -> dict:  # type: ignore[type-arg]
    """Shortcut for an `always`-triggered bonus entry."""
    return {
        "condition": "always",
        "bonus_units_percent": pct,
        "funded_by": funded_by,
    }


# Product seeds. Each references a company by slug.
# purchase_config.bonuses encode the volume incentive -- bigger packs
# get a higher `always` bonus_units_percent. Legally the share price
# stays flat; buyers are rewarded with free (gift) units for buying
# in larger volumes.
PRODUCTS: list[dict] = []  # type: ignore[type-arg]


def _tranches(n: int, amount_cents: int) -> list[dict]:  # type: ignore[type-arg]
    """Build `n` tranches summing to amount_cents with percent distribution
    summing to 100 and decomposing evenly over product units.

    The last tranche absorbs the rounding remainder in both amount_cents
    (so `sum == amount_cents`) and units_percent (so `sum == 100`).
    """
    per_amount = amount_cents // n
    per_pct = 100 // n
    tranches: list[dict] = []  # type: ignore[type-arg]
    for i in range(n):
        is_last = i == n - 1
        tranches.append(
            {
                "amount_cents": (
                    amount_cents - per_amount * (n - 1)
                    if is_last
                    else per_amount
                ),
                "units_percent": (
                    100 - per_pct * (n - 1) if is_last else per_pct
                ),
            }
        )
    return tranches


# Product name -> list of installment specs.
# Each spec: (plan name, number of tranches, bonus_units, agent_bonus_units)
INSTALLMENTS: dict[str, list[tuple[str, int, int, int]]] = {}


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


async def _reset(session: AsyncSession) -> None:
    """Remove everything this script ever seeded, in FK-safe order."""
    log("Reset: removing previously-seeded rows")

    product_names = [p["name"] for p in PRODUCTS]
    company_names = [c["name"] for c in COMPANIES]
    owner_emails = [f"seed-{c['slug']}@cbshome.dev" for c in COMPANIES]

    # Resolve product IDs first -- we need them to clean installments
    # and seeded Purchase rows (sold-out marker).
    prod_ids_stmt = select(Product.id).where(Product.name.in_(product_names))
    product_ids = [
        row[0]
        for row in (await session.execute(prod_ids_stmt)).all()
    ]

    # 1. Purchases referencing seeded products.
    if product_ids:
        await session.execute(
            delete(Purchase).where(Purchase.product_id.in_(product_ids))
        )

    # 2. Installment templates under seeded products.
    if product_ids:
        await session.execute(
            delete(ProductInstallment).where(
                ProductInstallment.product_id.in_(product_ids)
            )
        )

    # 3. Products themselves.
    await session.execute(
        delete(Product).where(Product.name.in_(product_names))
    )

    # 3b. OptionPools (Sprint 4.3) for the seeded companies.
    # Done after Products because Product.pool_id has FK ondelete=RESTRICT.
    company_ids_stmt = select(CompanyProfile.id).where(
        CompanyProfile.name.in_(company_names)
    )
    seeded_company_ids = [
        row[0] for row in (await session.execute(company_ids_stmt)).all()
    ]
    if seeded_company_ids:
        await session.execute(
            delete(OptionPool).where(
                OptionPool.company_id.in_(seeded_company_ids)
            )
        )

    # 4. Company profiles.
    await session.execute(
        delete(CompanyProfile).where(
            CompanyProfile.name.in_(company_names)
        )
    )

    # 5. Users we created (company owners only).
    for email in owner_emails:
        await session.execute(
            delete(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )

    await session.commit()
    log("Reset: done")


# ---------------------------------------------------------------------------
# Ensure helpers (idempotent)
# ---------------------------------------------------------------------------


async def _ensure_company_owner(
    session: AsyncSession,
    *,
    slug: str,
    platform_user_id,  # UUID, re-used as referred_by
) -> User:
    """Return the company-owner User, creating it if missing."""
    email = f"seed-{slug}@cbshome.dev"
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        role=UserRole.COMPANY,
        is_active=True,
        onboarding_step=OnboardingStep.ROLE_SELECTED,
        kyc_status=KYCStatus.NOT_STARTED,
        referred_by=platform_user_id,
        credentials={
            "email": {
                "email": email,
                "password_hash": await hash_password(SEED_PASSWORD),
            },
        },
        profile={},
        language="en",
    )
    session.add(user)
    await session.flush()
    return user


async def _ensure_company(
    session: AsyncSession,
    *,
    spec: dict,  # type: ignore[type-arg]
    owner: User,
) -> CompanyProfile:
    """Return the CompanyProfile, creating it if missing."""
    stmt = select(CompanyProfile).where(CompanyProfile.name == spec["name"])
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    logo_url = (
        _svg_logo(spec["logo_initials"], spec["logo_bg"])
        if spec["has_logo"]
        else None
    )

    # Minimal valid distribution_config: company keeps everything
    # (company_pct=1.0, no agent levels). Adjust per company later
    # if the seed should simulate agent distribution.
    profile = CompanyProfile(
        user_id=owner.id,
        name=spec["name"],
        description=spec["description"],
        logo_url=logo_url,
        cover_url=None,  # fallback chain tested via logo / icon
        promo_video_url=None,
        presentation_url=None,
        price_per_unit_cents=spec["price_per_unit_cents"],
        # Sprint 4.3: tokenization parameters.
        total_supply=spec["total_supply"],
        shares_per_option=spec["shares_per_option"],
        distribution_config={"company_pct": 1.0, "agent_levels": []},
        status=spec["status"],
    )
    session.add(profile)
    await session.flush()
    return profile


async def _ensure_pool(
    session: AsyncSession,
    *,
    company: CompanyProfile,
) -> OptionPool:
    """Return the active OptionPool for the company, creating it if missing.

    Sprint 4.3: every Product needs a pool. The seed allocates 100% of
    company.total_supply to one active pool -- enough headroom that no
    product hits 'sold out' during dev/staging use, regardless of what
    the storefront sells.

    Idempotent: a pool with status='active' for this company is
    returned as-is (a partial unique index on the table guarantees at
    most one active pool per company).
    """
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
    return pool


async def _ensure_product(
    session: AsyncSession,
    *,
    spec: dict,  # type: ignore[type-arg]
    company: CompanyProfile,
    pool: OptionPool,
) -> Product:
    """Return the Product, creating it if missing.

    Sprint 4.3: products attach to the company's active OptionPool via
    pool_id. The denormalised company_id is still stored alongside for
    fast queries (dashboard, portfolio) without a join through pool.
    """
    stmt = select(Product).where(Product.name == spec["name"])
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    product = Product(
        company_id=company.id,
        pool_id=pool.id,
        name=spec["name"],
        description=spec["description"],
        package_size=spec["package_size"],  # Sprint 4.3: column renamed
        price_per_unit_cents=company.price_per_unit_cents,
        purchase_config=spec["purchase_config"],
        status=spec["status"],
    )
    session.add(product)
    await session.flush()
    return product


async def _ensure_installments(
    session: AsyncSession,
    *,
    product: Product,
    specs: list[tuple[str, int, int, int]],
) -> None:
    """Create missing installment plans for the product."""
    stmt = select(ProductInstallment.name).where(
        ProductInstallment.product_id == product.id,
        ProductInstallment.is_deleted.is_(False),
    )
    existing_names = {
        row[0] for row in (await session.execute(stmt)).all()
    }

    total_amount = product.package_size * product.price_per_unit_cents

    for name, n_tranches, bonus_units, agent_bonus_units in specs:
        if name in existing_names:
            continue
        plan = ProductInstallment(
            product_id=product.id,
            name=name,
            plan_config={
                "tranches": _tranches(n_tranches, total_amount),
                "bonus_units": bonus_units,
                "agent_bonus_units": agent_bonus_units,
            },
            is_deleted=False,
        )
        session.add(plan)
    await session.flush()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def seed_storefront(reset: bool) -> None:
    """Main entry point -- orchestrate the full seed."""
    setup_logging()
    factory = get_session_factory()

    async with factory() as session:
        try:
            if reset:
                await _reset(session)

            # Ensure we have the Platform user -- used as referrer
            # (Sprint 7.2 convention) for all company owners.
            platform_user_id = await get_platform_user_id(session)

            # 1. Companies (owners + profiles).
            log("Ensuring companies")
            companies_by_slug: dict[str, CompanyProfile] = {}
            for spec in COMPANIES:
                owner = await _ensure_company_owner(
                    session, slug=spec["slug"], platform_user_id=platform_user_id
                )
                profile = await _ensure_company(
                    session, spec=spec, owner=owner
                )
                companies_by_slug[spec["slug"]] = profile
            log(f"  {len(companies_by_slug)} companies ready")

            # 2. Option pools (Sprint 4.3).
            #    One active pool per company, equity_percent=100,
            #    total_options=company.total_supply. Products attach via pool_id.
            log("Ensuring option pools")
            pools_by_slug: dict[str, OptionPool] = {}
            for slug, profile in companies_by_slug.items():
                pool = await _ensure_pool(session, company=profile)
                pools_by_slug[slug] = pool
            log(f"  {len(pools_by_slug)} pools ready")

            # 3. Products.
            log("Ensuring products")
            products_by_name: dict[str, Product] = {}
            for spec in PRODUCTS:
                company = companies_by_slug[spec["company_slug"]]
                pool = pools_by_slug[spec["company_slug"]]
                product = await _ensure_product(
                    session, spec=spec, company=company, pool=pool
                )
                products_by_name[spec["name"]] = product
            log(f"  {len(products_by_name)} products ready")

            # 4. Installments.
            log("Ensuring installment plans")
            plan_count = 0
            for product_name, specs in INSTALLMENTS.items():
                product = products_by_name.get(product_name)
                if product is None:
                    warn(
                        f"  Skipping installments for missing product "
                        f"'{product_name}'"
                    )
                    continue
                await _ensure_installments(
                    session, product=product, specs=specs
                )
                plan_count += len(specs)
            log(f"  {plan_count} installment plans ensured")

            await session.commit()
            log("Storefront seed complete")

        except Exception as exc:
            await session.rollback()
            err(f"Seed failed: {exc}")
            raise
        finally:
            await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed storefront (dev only)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove previously-seeded rows before seeding",
    )
    args = parser.parse_args()

    asyncio.run(seed_storefront(reset=args.reset))


if __name__ == "__main__":
    main()
