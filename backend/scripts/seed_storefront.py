#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- Seed Storefront (Phase F4.1 -- dev only)
# =============================================================================
#
# Populates the database with 6 companies, 21 products and 19 installment
# plans so the investor storefront (F4.1) renders real data in dev /
# staging environments. Covers:
#   - image fallback chain (cover_url / logo_url / Building icon)
#   - purchase_config.bonuses with `always` and `platform`-funded variants
#   - hidden company + hidden product (negative visibility tests)
#   - LIKE-escape test (company name contains "%" -- "Tesla 50%")
#   - sold-out product (one Purchase row injected)
#   - long names / empty descriptions / rich descriptions
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
#   Computed by the storefront router from Purchase rows. The one
#   sold-out product is seeded with a single Purchase by a
#   dedicated seed-investor so `sold_units` reaches `units`.
#   All other products stay at sold_units=0. This is a cosmetic
#   injection -- no ledger entries, no balances.
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
import asyncio
import sys
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
from app.modules.products.constants import ProductStatus
from app.modules.products.models import Product, ProductInstallment
from app.modules.purchases.constants import (
    PurchaseLegalBasis,
    PurchaseStatus,
)
from app.modules.purchases.models import Purchase
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole

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
SEED_INVESTOR_EMAIL = "seed-investor@cbshome.dev"


def _svg_logo(initials: str, bg: str) -> str:
    """Inline SVG data-URI. Square 200x200, initials on a coloured
    background. Viewable inline anywhere, no external fetch.
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
    # data:image/svg+xml;utf8,<svg...> -- only a handful of chars need
    # escaping for a URL-safe inline reference.
    url_safe = (
        svg.replace("\n", "")
        .replace("#", "%23")
        .replace('"', "'")
    )
    return f"data:image/svg+xml;utf8,{url_safe}"


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

# Company name -> seed data. Prices in cents.
# The slug is used for the owner user's email; must be unique per company.
COMPANIES: list[dict] = [  # type: ignore[type-arg]
    {
        "slug": "ipi-ag",
        "name": "IPI AG",
        "description": (
            "Investments in IPI AG construction projects. "
            "Returns through unit value growth."
        ),
        "logo_bg": "#1A6B6A",
        "logo_initials": "IPI",
        "has_logo": True,
        "price_per_unit_cents": 100,
        "status": CompanyStatus.ACTIVE,
    },
    {
        "slug": "immo-pro-invest",
        "name": "Immo-Pro-Invest GmbH",
        "description": (
            "Real estate investments via Immo-Pro-Invest GmbH. "
            "Stable portfolio growth."
        ),
        "logo_bg": "#C26A2B",
        "logo_initials": "IPG",
        "has_logo": True,
        "price_per_unit_cents": 95,
        "status": CompanyStatus.ACTIVE,
    },
    {
        "slug": "cbs-home",
        "name": "CBS Home Franchise",
        "description": (
            "CBS Home franchise -- innovative construction technology. "
            "Patented system."
        ),
        "logo_bg": "#3E6D9C",
        "logo_initials": "CBS",
        "has_logo": True,
        "price_per_unit_cents": 500,
        "status": CompanyStatus.ACTIVE,
    },
    {
        "slug": "nordic-construction",
        "name": "Nordic Construction Holdings International",
        "description": (
            "Large-scale industrial construction projects across the "
            "Nordic region."
        ),
        "logo_bg": "#4A4A4A",
        "logo_initials": "NCH",
        "has_logo": False,  # test Building-icon fallback
        "price_per_unit_cents": 1000,
        "status": CompanyStatus.ACTIVE,
    },
    {
        "slug": "tesla-50pct",
        "name": "Tesla 50% Infrastructure",
        "description": (
            "Infrastructure co-investment programme. Unit price covers "
            "50% of the project cost."
        ),
        "logo_bg": "#B02E2E",
        "logo_initials": "T50",
        "has_logo": True,
        "price_per_unit_cents": 250,
        "status": CompanyStatus.ACTIVE,
    },
    {
        "slug": "stealth-fund",
        "name": "Stealth Fund",
        "description": "Private placements. Not publicly visible.",
        "logo_bg": "#2A2A2A",
        "logo_initials": "STF",
        "has_logo": True,
        "price_per_unit_cents": 10000,
        "status": CompanyStatus.HIDDEN,  # negative visibility test
    },
]


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
PRODUCTS: list[dict] = [  # type: ignore[type-arg]
    # -- IPI AG packs (ladder: 100 / 1000 / 10000 / 100000 units) --
    {
        "company_slug": "ipi-ag",
        "name": "IPI AG Starter -- 100 Shares",
        "description": (
            "Entry-level pack for first-time investors. Build a small "
            "position and test the waters."
        ),
        "units": 100,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "ipi-ag",
        "name": "IPI AG Investor -- 1 000 Shares",
        "description": (
            "Mid-tier pack for committed investors. +5% bonus shares on "
            "every purchase, funded by the company."
        ),
        "units": 1000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(5)]},
    },
    {
        "company_slug": "ipi-ag",
        "name": "IPI AG Whale -- 10 000 Shares",
        "description": (
            "High-volume pack. +10% bonus shares, multiple installment "
            "plans available."
        ),
        "units": 10000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(10)]},
    },
    {
        "company_slug": "ipi-ag",
        "name": "IPI AG Institutional -- 100 000 Shares",
        "description": (
            "Institutional-grade pack. Maximum bonus (+15%), long-term "
            "installment plans up to 24 months."
        ),
        "units": 100000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(15)]},
    },
    {
        "company_slug": "ipi-ag",
        "name": "IPI AG Sold Tranche",
        "description": "Completed pack -- closed to new buyers.",
        "units": 500,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
        # Marker for sold-out injection below.
        "_force_sold_out": True,
    },
    {
        "company_slug": "ipi-ag",
        "name": (
            "IPI AG Series C Long Title -- Real Estate Construction "
            "Holdings Tranche"
        ),
        "description": (
            "Wraps across two lines on narrow screens. Used to verify "
            "card ellipsis and header truncation."
        ),
        "units": 1000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "ipi-ag",
        "name": "IPI AG Dev Tranche",
        "description": "Internal tranche, not public.",
        "units": 100,
        "status": ProductStatus.HIDDEN,  # negative visibility test
        "purchase_config": None,
    },
    # -- Immo-Pro-Invest packs --
    {
        "company_slug": "immo-pro-invest",
        "name": "Real Estate Starter Pack",
        "description": (
            "Entry-level real estate exposure. 500 units, no volume "
            "bonus at this tier."
        ),
        "units": 500,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "immo-pro-invest",
        "name": "Real Estate Investor Pack",
        "description": (
            "Mid-tier real estate pack with +7% volume bonus and three "
            "installment options."
        ),
        "units": 5000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(7)]},
    },
    {
        "company_slug": "immo-pro-invest",
        "name": "Real Estate Whale Pack",
        "description": (
            "Large real estate allocation. +12% volume bonus, long "
            "installment plans."
        ),
        "units": 50000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(12)]},
    },
    {
        "company_slug": "immo-pro-invest",
        "name": "Real Estate Platform Bonus Pack",
        "description": (
            "Special programme -- bonus shares are funded by the "
            "platform rather than the company."
        ),
        "units": 10000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(5, funded_by="platform")]},
    },
    # -- CBS Home packs --
    {
        "company_slug": "cbs-home",
        "name": "CBS Home Basic License",
        "description": (
            "Entry license for small operators. 100 units at $5 each."
        ),
        "units": 100,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "cbs-home",
        "name": "CBS Home Full License",
        "description": (
            "Full licensing rights. Includes technology transfer, "
            "training materials, and support contracts. +10% bonus "
            "shares on purchase. Installment options available for "
            "operators who prefer to pay over time rather than upfront "
            "-- longer plans come with their own additional bonus on "
            "top of the volume bonus applied at checkout. Review both "
            "layers before committing."
        ),
        "units": 500,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(10)]},
    },
    {
        "company_slug": "cbs-home",
        "name": "CBS Home Starter Kit",
        "description": None,  # empty-description test
        "units": 50,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "cbs-home",
        "name": "CBS Home Enterprise",
        "description": (
            "Enterprise-grade license with +20% volume bonus, the "
            "highest tier available."
        ),
        "units": 2000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(20)]},
    },
    # -- Nordic Construction packs (no company logo -> Building icon) --
    {
        "company_slug": "nordic-construction",
        "name": "Nordic Starter",
        "description": "Entry pack for Nordic infrastructure projects.",
        "units": 50,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "nordic-construction",
        "name": "Nordic Mega Project",
        "description": (
            "Mid-tier pack with +8% volume bonus for serious backers."
        ),
        "units": 500,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(8)]},
    },
    {
        "company_slug": "nordic-construction",
        "name": "Nordic Flagship",
        "description": "Top-tier Nordic pack with +15% volume bonus.",
        "units": 2000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(15)]},
    },
    # -- Tesla 50% packs (LIKE-escape test on company name) --
    {
        "company_slug": "tesla-50pct",
        "name": "Tesla Solar Farm Starter",
        "description": "Small solar allocation.",
        "units": 100,
        "status": ProductStatus.ACTIVE,
        "purchase_config": None,
    },
    {
        "company_slug": "tesla-50pct",
        "name": "Tesla Solar Farm Pro",
        "description": "Pro-tier solar allocation with +6% volume bonus.",
        "units": 1000,
        "status": ProductStatus.ACTIVE,
        "purchase_config": {"bonuses": [_bonus(6)]},
    },
    # -- Stealth Fund (parent company is hidden) --
    {
        "company_slug": "stealth-fund",
        "name": "Stealth Product",
        "description": None,
        "units": 10,
        "status": ProductStatus.ACTIVE,  # active, but company is hidden
        "purchase_config": None,
    },
]


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
INSTALLMENTS: dict[str, list[tuple[str, int, int, int]]] = {
    "IPI AG Investor -- 1 000 Shares": [
        ("3 months, no bonus", 3, 0, 0),
        ("6 months with bonus", 6, 50, 5),
    ],
    "IPI AG Whale -- 10 000 Shares": [
        ("6 months", 6, 200, 20),
        ("12 months", 12, 500, 50),
    ],
    "IPI AG Institutional -- 100 000 Shares": [
        ("6 months", 6, 2000, 200),
        ("12 months", 12, 5000, 500),
        ("24 months", 24, 10000, 1000),
    ],
    "Real Estate Investor Pack": [
        ("Quarterly", 4, 0, 0),
        ("Monthly 6 months", 6, 100, 10),
        ("Annual", 12, 300, 30),
    ],
    "Real Estate Whale Pack": [
        ("6 months", 6, 1000, 100),
        ("12 months", 12, 3000, 300),
        ("24 months", 24, 8000, 800),
    ],
    "CBS Home Full License": [
        ("12 months", 12, 30, 3),
        ("24 months", 24, 60, 6),
    ],
    "CBS Home Enterprise": [
        ("12 months", 12, 200, 20),
        ("24 months", 24, 500, 50),
    ],
    "Nordic Flagship": [
        ("12 months", 12, 300, 30),
    ],
    "Tesla Solar Farm Pro": [
        ("3 months", 3, 0, 0),
    ],
}


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

    # 4. Company profiles.
    await session.execute(
        delete(CompanyProfile).where(
            CompanyProfile.name.in_(company_names)
        )
    )

    # 5. Users we created (company owners + seed investor).
    all_emails = owner_emails + [SEED_INVESTOR_EMAIL]
    for email in all_emails:
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
                "password_hash": hash_password(SEED_PASSWORD),
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
        distribution_config={"company_pct": 1.0, "agent_levels": []},
        status=spec["status"],
    )
    session.add(profile)
    await session.flush()
    return profile


async def _ensure_product(
    session: AsyncSession,
    *,
    spec: dict,  # type: ignore[type-arg]
    company: CompanyProfile,
) -> Product:
    """Return the Product, creating it if missing."""
    stmt = select(Product).where(Product.name == spec["name"])
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    product = Product(
        company_id=company.id,
        name=spec["name"],
        description=spec["description"],
        units=spec["units"],
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

    total_amount = product.units * product.price_per_unit_cents

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


async def _ensure_seed_investor(session: AsyncSession) -> User:
    """Return the dedicated seed investor used for sold-out injection."""
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string()
        == SEED_INVESTOR_EMAIL
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        role=UserRole.INVESTOR,
        is_active=True,
        onboarding_step=OnboardingStep.ROLE_SELECTED,
        kyc_status=KYCStatus.APPROVED,
        credentials={
            "email": {
                "email": SEED_INVESTOR_EMAIL,
                "password_hash": hash_password(SEED_PASSWORD),
            },
        },
        profile={"first_name": "Seed", "last_name": "Investor"},
        language="en",
    )
    session.add(user)
    await session.flush()
    return user


async def _ensure_sold_out(
    session: AsyncSession,
    *,
    product: Product,
    investor: User,
) -> None:
    """Inject a single Purchase row so sold_units == units.

    Cosmetic only -- no ledger entries, no balances. See module
    docstring for the trade-off.
    """
    stmt = select(Purchase.id).where(Purchase.product_id == product.id)
    if (await session.execute(stmt)).first() is not None:
        return

    purchase = Purchase(
        investor_id=investor.id,
        product_id=product.id,
        company_id=product.company_id,
        legal_basis=PurchaseLegalBasis.SALE,
        units=product.units,
        paid_cents=product.units * product.price_per_unit_cents,
        price_per_unit_cents=product.price_per_unit_cents,
        status=PurchaseStatus.ACTIVE,
    )
    session.add(purchase)
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

            # 2. Products.
            log("Ensuring products")
            products_by_name: dict[str, Product] = {}
            sold_out_product: Product | None = None
            for spec in PRODUCTS:
                company = companies_by_slug[spec["company_slug"]]
                product = await _ensure_product(
                    session, spec=spec, company=company
                )
                products_by_name[spec["name"]] = product
                if spec.get("_force_sold_out"):
                    sold_out_product = product
            log(f"  {len(products_by_name)} products ready")

            # 3. Installments.
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

            # 4. Sold-out injection (single Purchase on one product).
            if sold_out_product is not None:
                investor = await _ensure_seed_investor(session)
                await _ensure_sold_out(
                    session,
                    product=sold_out_product,
                    investor=investor,
                )
                log(
                    f"  Sold-out marker on '{sold_out_product.name}' "
                    f"(+1 Purchase row)"
                )

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
