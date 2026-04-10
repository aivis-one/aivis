# =============================================================================
# CBSHOME Backend -- Company Models (Sprint 4.1, fix Phase 4)
# =============================================================================
#
# CompanyProfile:
#   One-to-one with User (role=company). Contains media URLs, pricing,
#   distribution config, and status. User is created alongside the profile
#   by staff admin (not promoted from existing user).
#
# CompanyPriceHistory:
#   Immutable record of price changes. No updated_at.
#   Tracks who changed the price (staff_id via changed_by).
#
# CompanyRoadmapItem:
#   Ordered list of roadmap milestones. Soft-delete only (status -> archived
#   pattern not applicable; items are hidden via is_deleted flag).
#   order column controls display sequence.
#
# DISTRIBUTION CONFIG (JSONB):
#   {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}
#   Validated by validate_distribution_config() in constants.py.
#   Use set_jsonb("distribution_config", value) for mutations.
#
# PRICE:
#   price_per_unit_cents uses BigInteger (64-bit) -- project standard
#   for all monetary values.
#
# ENUMS:
#   CompanyStatus and RoadmapItemStatus are canonical in constants.py.
#   Imported here for model defaults and type hints.
# =============================================================================

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, TimestampMixin, UUIDMixin
from app.modules.companies.constants import CompanyStatus, RoadmapItemStatus


class CompanyProfile(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    """Company profile -- one-to-one with User (role=company).

    Created by staff admin. Contains media, pricing, and distribution config.
    """

    __tablename__ = "company_profiles"

    # -- One-to-one with User --
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )

    # -- Identity --
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
    )

    # -- Media --
    logo_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )
    cover_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )
    promo_video_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )
    presentation_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    # -- Pricing --
    price_per_unit_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # -- Distribution --
    # {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}
    # Use set_jsonb("distribution_config", value) for mutations.
    distribution_config: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=False,
    )

    # -- Status --
    status: Mapped[str] = mapped_column(
        String(20),
        default=CompanyStatus.HIDDEN,
        server_default=CompanyStatus.HIDDEN.value,
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CompanyProfile id={self.id} name={self.name!r} "
            f"status={self.status}>"
        )


class CompanyPriceHistory(UUIDMixin, Base):
    """Immutable record of company price changes.

    No updated_at -- entries are never modified.
    """

    __tablename__ = "company_price_history"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    price_per_unit_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    changed_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CompanyPriceHistory company_id={self.company_id} "
            f"price={self.price_per_unit_cents}>"
        )


class CompanyRoadmapItem(UUIDMixin, TimestampMixin, Base):
    """Ordered roadmap milestone for a company.

    Soft-deleted via is_deleted flag. order controls display sequence.
    """

    __tablename__ = "company_roadmap_items"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
    )
    target_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=RoadmapItemStatus.PLANNED,
        server_default=RoadmapItemStatus.PLANNED.value,
        nullable=False,
    )
    order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CompanyRoadmapItem id={self.id} title={self.title!r} "
            f"order={self.order}>"
        )
