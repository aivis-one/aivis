# =============================================================================
# CBSHOME Backend -- Company Models (Sprint 4.1, fix Phase 4, Sprint 4.3,
#                                     Refactor 2 iter 2.2)
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
# CompanyAttachment (Refactor 2 iter 2.2):
#   Arbitrary binary files attached to a company (business licenses,
#   incorporation certificates, presentations, patents, etc.) stored in
#   MinIO under `companies/<company_id>/attachments/<attachment_id>/...`
#   (R2 §2.2). Metadata only in Postgres -- the actual bytes are streamed
#   through presigned URLs from the storage layer (app/core/storage.py).
#   Soft-deleted via is_deleted; hard-delete is a separate admin-only path
#   that also removes the MinIO object.
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
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - Added total_supply (BigInteger NOT NULL): total number of options
#     that cover 100% of company shares. When tokenised this is the full
#     mint of the contract. Owners hold (total_supply - sum(active_pools))
#     outside the platform.
#   - Added shares_per_option (Integer NOT NULL): denomination ratio.
#     total_supply = total_shares / shares_per_option. Changes only on a
#     split (future scope -- new Pool, migration purchases, see
#     CBSHOME-Share-Pool-Refactor.md section 4).
#   - Price still lives here (NOT on OptionPool): price changes more often
#     than the pool is restructured, and a re-valuation should not require
#     a new pool.
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

    # -- Supply (Sprint 4.3) --
    # Total number of options covering 100% of company shares.
    # total_supply = total_shares / shares_per_option.
    # When tokenised, this is the full mint of the contract.
    total_supply: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Denomination ratio: how many real shares one option represents.
    # Default in seeds is 1 (one option = one share). Changes only on a
    # split (new pool, future scope).
    shares_per_option: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
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
            f"supply={self.total_supply} status={self.status}>"
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


class CompanyAttachment(UUIDMixin, TimestampMixin, Base):
    """Binary file attached to a company.

    Refactor 2 iter 2.2 (R2 §3.2). Metadata only -- bytes live in MinIO
    under storage_key. Soft-deleted via is_deleted; hard-delete is admin-only
    and removes the MinIO object as well (handled in the service layer).

    `category` is a path-tree string with `/` as level separator (max 5
    levels, lowercase, regex enforced via Pydantic at the API edge -- see
    ATTACHMENT_CATEGORY_REGEX in constants.py). Slashes are NOT directory
    separators in MinIO -- the storage key uses UUID-based paths instead
    (companies/<company_id>/attachments/<attachment_id>/<filename>).

    `language` is ISO 639-1 (en/ru/de/ar) or NULL for language-agnostic
    documents (R2 §3.6). Multilingual docs are stored as separate rows
    sharing (category, title) -- the backend exposes a flat list and the
    UI groups client-side.

    `order` controls display sequence inside a (company_id, category)
    scope (Q-ATT-4). The service layer shifts existing rows to make room
    when an explicit order is requested.

    `is_published` controls visibility for the auth-flow investor view;
    `is_public` AND `is_published` together enable the public-flow
    download endpoint without authentication (R2 §3.4).

    NOTE: `order` is a Postgres reserved word; SQLAlchemy + the DB driver
    quote it correctly without an explicit `mapped_column("order", ...)`,
    matching the existing CompanyRoadmapItem.order convention.
    """

    __tablename__ = "company_attachments"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Categorisation --
    category: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )
    language: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    # -- Display --
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
    )

    # -- Storage pointer --
    storage_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # -- Ordering inside (company_id, category) --
    order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    # -- Visibility flags (safety-first defaults: invisible) --
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    # -- Audit --
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # -- Soft-delete --
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CompanyAttachment id={self.id} company={self.company_id} "
            f"category={self.category!r} title={self.title!r}>"
        )
