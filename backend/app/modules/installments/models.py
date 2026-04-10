# =============================================================================
# CBSHOME Backend -- Installment Models (Sprint 6.2)
# =============================================================================
#
# InstallmentPlan:
#   Active installment plan for an investor. Created when investor
#   chooses a ProductInstallment template. plan_config_snapshot freezes
#   the template at creation time -- subsequent template changes do not
#   affect active plans.
#
# InstallmentTranche:
#   Individual payment within a plan. Each tranche becomes a Purchase
#   record when paid (purchase_id NOT NULL after payment).
#
# SNAPSHOT STRATEGY:
#   plan_config_snapshot: full copy of ProductInstallment.plan_config.
#   total_price_cents, total_units: denormalized for fast queries.
#   price_per_unit_cents: snapshot from Product at plan creation time.
#
# AGENT FIELDS (Sprint 7.x stub):
#   referral_link_id: nullable, filled when purchase is via referral link.
#   agent_id: nullable, L1 agent for bonus units at plan completion.
#   Both are nullable now, populated when referral system is implemented.
#
# RULE: All columns use String (not SAEnum) to avoid PostgreSQL type
# conflicts in migrations.
# =============================================================================

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, UUIDMixin
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)


class InstallmentPlan(JSONBMixin, UUIDMixin, Base):
    """Active installment plan for an investor."""

    __tablename__ = "installment_plans"

    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    product_installment_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_installments.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # -- Denormalized company_id for fast queries --
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Snapshot of plan_config at creation time --
    # Full copy of ProductInstallment.plan_config.
    # Use set_jsonb("plan_config_snapshot", value) for mutations (should not happen).
    plan_config_snapshot: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=False,
    )

    # -- Denormalized fields from snapshot for fast queries --
    total_price_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    total_units: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Price per unit snapshot at plan creation time.
    price_per_unit_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # -- Agent fields (Sprint 7.x stubs) --
    referral_link_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        # FK to referral_links.id added in Sprint 7.2 migration.
    )

    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # -- Lifecycle --
    status: Mapped[str] = mapped_column(
        String(20),
        default=InstallmentPlanStatus.ACTIVE,
        server_default=InstallmentPlanStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )

    # Immutable creation timestamp.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Set when plan transitions to completed.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Set when plan transitions to defaulted.
    defaulted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<InstallmentPlan id={self.id} investor={self.investor_id} "
            f"product={self.product_id} status={self.status}>"
        )


class InstallmentTranche(UUIDMixin, Base):
    """Individual tranche payment within an installment plan."""

    __tablename__ = "installment_tranches"

    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("installment_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Tranche sequence number (1-based).
    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Payment due date (calculated via february rule).
    due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Amount to pay in cents (from plan_config_snapshot.tranches[N].amount_cents).
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Units unlocked upon payment (pre-computed at plan creation).
    # = tranches[N].units_percent * total_units // 100
    units_unlocked: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # -- Lifecycle --
    status: Mapped[str] = mapped_column(
        String(20),
        default=InstallmentTrancheStatus.SCHEDULED,
        server_default=InstallmentTrancheStatus.SCHEDULED.value,
        nullable=False,
        index=True,
    )

    # Set when tranche is paid.
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # FK to Purchase record created upon payment.
    purchase_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("purchases.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Immutable creation timestamp.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<InstallmentTranche id={self.id} plan={self.plan_id} "
            f"number={self.number} due={self.due_date} "
            f"amount={self.amount_cents} status={self.status}>"
        )
