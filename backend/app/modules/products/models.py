# =============================================================================
# CBSHOME Backend -- Product Models (Sprint 4.2)
# =============================================================================
#
# Product:
#   Investment package belonging to a Company. Contains units (package
#   size, immutable), gift_units (bonus on instant purchase), and
#   price_per_unit_cents (denormalized from Company, cascaded on price
#   change).
#
# ProductInstallment:
#   Installment plan template for a Product. Contains plan_config JSONB
#   with tranches, bonus_units, and agent_bonus_units. Soft-deleted on
#   company price cascade (new templates must be created for new price).
#   When an investor starts an installment, plan_config is snapshot-copied
#   into InstallmentPlan (Sprint 6.2) -- changes to the template do not
#   affect active plans.
#
# PRICE CASCADE (from companies/service.py):
#   When Company price changes:
#   1. Product.price_per_unit_cents updated for active/hidden products
#   2. All ProductInstallment for those products soft-deleted
#   3. Staff creates new installment templates for new price
# =============================================================================

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, TimestampMixin, UUIDMixin


class ProductStatus(enum.StrEnum):
    """Product lifecycle status."""

    ACTIVE = "active"
    HIDDEN = "hidden"
    ARCHIVED = "archived"


class Product(UUIDMixin, TimestampMixin, Base):
    """Investment package belonging to a Company."""

    __tablename__ = "products"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
    )

    # -- Package size (immutable after creation) --
    units: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # -- Bonus units on instant purchase (0 = no bonus) --
    gift_units: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    # -- Denormalized from Company, cascaded on price change --
    price_per_unit_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # -- Status --
    status: Mapped[str] = mapped_column(
        String(20),
        default=ProductStatus.HIDDEN,
        server_default=ProductStatus.HIDDEN.value,
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Product id={self.id} name={self.name!r} "
            f"units={self.units} status={self.status}>"
        )


class ProductInstallment(JSONBMixin, UUIDMixin, Base):
    """Installment plan template for a Product.

    Soft-deleted on company price cascade. No updated_at per ТЗ.
    plan_config is snapshot-copied into InstallmentPlan on activation.
    """

    __tablename__ = "product_installments"

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # -- Plan configuration (JSONB) --
    # {
    #   "tranches": [{"amount_cents": int, "units_percent": int}, ...],
    #   "bonus_units": int,
    #   "agent_bonus_units": int
    # }
    # Use set_jsonb("plan_config", value) for mutations.
    plan_config: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=False,
    )

    # -- Soft-delete --
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    # -- Immutable timestamp (no updated_at per ТЗ) --
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ProductInstallment id={self.id} product={self.product_id} "
            f"name={self.name!r}>"
        )
