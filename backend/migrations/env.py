# =============================================================================
# CBSHOME Backend -- Alembic Environment Configuration
# =============================================================================
#
# KEY POINTS:
#   1. Async migrations: asyncpg requires an async engine. We bridge to
#      Alembic's sync runner via connection.run_sync().
#   2. Database URL: from app.core.config (reads .env) -- single source.
#   3. target_metadata: Base.metadata -- Alembic compares against actual DB.
#
# IMPORTANT: Every new models.py must be imported here so Alembic can
#   see the tables via Base.metadata. Add imports as modules are created.
# =============================================================================

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.database import Base

# ---------------------------------------------------------------------------
# Model imports -- required for Alembic autogenerate.
# Add new model imports here as sprints are completed.
# ---------------------------------------------------------------------------

# Sprint 0.3: Core models
from app.modules.users.models import User  # noqa: F401
from app.modules.ledgers.models import ActiveLedger, PassiveLedger  # noqa: F401
from app.modules.staff.models import StaffProfile, AvatarSession  # noqa: F401
from app.core.audit import AuditLog  # noqa: F401

# Sprint 2.1: KYC
# from app.modules.kyc.models import KYCApplication  # noqa: F401

# Sprint 2.2: Documents
# from app.modules.documents.models import Document, DocumentSigning  # noqa: F401

# Sprint 4.1: Companies
# from app.modules.companies.models import CompanyProfile, CompanyPriceHistory, CompanyRoadmapItem  # noqa: F401

# Sprint 4.2: Products
# from app.modules.products.models import Product, ProductInstallment  # noqa: F401

# Sprint 5.2: Payments
# from app.modules.payments.models import Payment, CryptoAddress  # noqa: F401

# Sprint 6.1: Purchases
# from app.modules.purchases.models import Purchase  # noqa: F401

# Sprint 6.2: Installments
# from app.modules.installments.models import InstallmentPlan, InstallmentTranche  # noqa: F401

# Sprint 6.3: Withdrawals
# from app.modules.withdrawals.models import Withdrawal  # noqa: F401

# Sprint 7.1: Agent Applications
# from app.modules.agent_applications.models import AgentApplication  # noqa: F401

# Sprint 7.2: Referrals
# from app.modules.referrals.models import ReferralLink, ReferralAttribution  # noqa: F401

# Sprint 7.3: Commissions
# from app.modules.commissions.models import LeaderboardSnapshot, VolumePayout  # noqa: F401

# Sprint 8.1: Notifications
# from app.modules.notifications.models import Notification, NotificationDelivery  # noqa: F401

# Sprint 9.1: Posts
# from app.modules.posts.models import Post, PostDismiss, Event  # noqa: F401

# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting to DB (--sql mode)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    """Execute migrations with the provided sync connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with async engine.

    asyncpg is async-only. We create an async engine, then bridge to
    Alembic's sync runner via run_sync(). Engine is always disposed in
    finally -- even if connect() raises (e.g. DB unreachable).
    """
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode -- bridges async to sync."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
