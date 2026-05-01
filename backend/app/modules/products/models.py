# =============================================================================
# CBSHOME Backend -- Product Models (Sprint 4.2 + Sprint 6.1 + Sprint F4.1
#                                     + Sprint 4.3)
# =============================================================================
#
# Product:
#   Investment package belonging to a Company. The package_size
#   (renamed from `units` in Sprint 4.3) is the number of options sold in
#   one package. Price (price_per_unit_cents) is denormalized from the
#   Company and cascaded on price change.
#
# Sprint 6.1 CHANGES:
#   - Removed gift_units column (replaced by purchase_config.bonuses[])
#   - Added purchase_config JSONB column (nullable, fallback to Company)
#   - Added JSONBMixin for safe purchase_config mutation
#
# Sprint F4.1 CHANGES:
#   - Added cover_url (nullable String(2000)): storefront hero image.
#     When null, clients fall back to Company logo/cover.
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - Renamed `units` column to `package_size`. Semantics: number of options
#     in one package of this product. Immutable after creation. The previous
#     name conflated "package size" (its actual meaning) with "remaining
#     inventory" (which was not its meaning). Inventory is now derived from
#     OptionPool at runtime (see purchases/service.py
#     get_available_packages_map).
#   - Added pool_id FK -> option_pools.id (RESTRICT). Every product belongs
#     to exactly one pool. A product cannot exist without an active pool.
#   - company_id stays as a denormalised FK (it equals pool.company_id and
#     is set on creation). Keeping it avoids JOINing through option_pools
#     for fast queries (dashboard, portfolio, attribution).
#
# PURCHASE_CONFIG JSONB (nullable):
#   {
#     "distribution": {"company_pct": 0.65, "agent_levels": [0.10, 0.03]},
#     "bonuses": [{"condition": "always", "bonus_units_percent": 10, ...}]
#   }
#   If null -> fallback to Company.distribution_config + no bonuses.
#   If distribution is null within config -> fallback to Company.
#   Use set_jsonb("purchase_config", value) for mutations.
#
# ProductInstallment:
#   Installment plan template for a Product. Contains plan_config JSONB
#   with tranches, bonus_units, and agent_bonus_units. Soft-deleted on
#   company price cascade (new templates must be created for new price).
#   When an investor starts an installment, plan_config is snapshot-copied
#   into InstallmentPlan (Sprint 6.2) -- changes to the template do not
#   affect active plans. The snapshot already stores the absolute
#   total_units, so the column rename `units -> package_size` does not
#   break previously-created plans.
#
# ENUMS:
#   ProductStatus is canonical in constants.py.
#   Imported here for model defaults and type hints.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, TimestampMixin, UUIDMixin
from app.modules.products.constants import ProductStatus


class Product(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    """Investment package belonging to a Company."""

    __tablename__ = "products"

    # -- Pool (Sprint 4.3) --
    # Every product belongs to exactly one OptionPool. A product cannot
    # exist without a pool. RESTRICT on delete: pools are archived, not
    # dropped, so a product's pool stays around even after a future split.
    pool_id: Mapped[UUID] = mapped_column(
        ForeignKey("option_pools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Company (denormalised, Sprint 4.3) --
    # Equal to pool.company_id at creation and immutable. Kept on the row
    # so dashboard / portfolio / attribution queries do not have to JOIN
    # through option_pools. Migration 0027 backfills this column.
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

    # -- Package size (immutable after creation, Sprint 4.3 rename) --
    # Number of options in one package of this product. Renamed from
    # `units` in migration 0027.
    package_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # -- Denormalized from Company, cascaded on price change --
    price_per_unit_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # -- Storefront hero image (Sprint F4.1) --
    # Nullable: when unset, storefront falls back to CompanyProfile.logo_url
    # / cover_url, and finally to a placeholder icon on the client.
    cover_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    # -- Purchase configuration (Sprint 6.1) --
    # Nullable: if null, fallback to Company.distribution_config + no bonuses.
    # Use set_jsonb("purchase_config", value) for mutations.
    purchase_config: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=True,
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
            f"package_size={self.package_size} status={self.status}>"
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
