# =============================================================================
# CBSHOME Backend -- Alembic env.py
# =============================================================================
#
# Alembic migration environment. Imports all ORM models so that
# Base.metadata contains the full schema for autogenerate.
#
# RULE:
#   Add imports as modules are created.
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
from app.modules.kyc.models import KYCApplication  # noqa: F401

# Sprint 2.2: Documents
from app.modules.documents.models import Document, DocumentSigning  # noqa: F401

# Sprint 4.1: Companies
from app.modules.companies.models import CompanyProfile, CompanyPriceHistory, CompanyRoadmapItem  # noqa: F401

# Sprint 4.2: Products
from app.modules.products.models import Product, ProductInstallment  # noqa: F401

# Sprint 5.2: Payments
from app.modules.payments.models import Payment, CryptoAddress  # noqa: F401

# Sprint 6.1: Purchases
from app.modules.purchases.models import Purchase  # noqa: F401

# Sprint 6.2: Installments
from app.modules.installments.models import InstallmentPlan, InstallmentTranche  # noqa: F401

# Sprint 6.3: Withdrawals
from app.modules.withdrawals.models import Withdrawal  # noqa: F401

# Sprint 6.4: Transactions
from app.modules.transactions.models import Transaction  # noqa: F401

# Sprint 7.1: Agent Applications
from app.modules.agent_applications.models import AgentApplication  # noqa: F401

# Sprint 7.2: Referrals
from app.modules.referrals.models import ReferralLink, ReferralAttribution  # noqa: F401

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
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in an async context."""
    connectable = create_async_engine(settings.database_url)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations with a live connection."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
