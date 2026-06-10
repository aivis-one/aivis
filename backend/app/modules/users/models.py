# =============================================================================
# CBSHOME Backend -- User Model
# =============================================================================
#
# Central user entity. Every person and system actor is a single User row.
# Role determines permissions -- no separate tables per role.
#
# ROLES:
#   investor  -- default role, can browse and purchase products
#   agent     -- can create referral links, earn commissions
#   company   -- has CompanyProfile, lists products
#   staff     -- platform operator (admin/support), has StaffProfile
#   platform  -- system user (is_system equivalent), never logs in,
#               receives all incoming payments, distributes via saga
#
# PLATFORM USER:
#   Identified by role=platform. No is_system field needed -- role is
#   the single source of truth. Created once by seed_platform.py.
#   Blocked from login in get_current_user() dependency.
#
# REFERRED_BY (Sprint 7.2):
#   Every user has a referrer. Default = Platform user (self-referencing
#   for Platform itself). Set once at registration, immutable after.
#   Agent chain for commission calculation walks up this field.
#
# REFERRED_BY_LINK_ID (Task 1, migration 0035):
#   Which specific referral link brought the user in. Set at
#   registration alongside referred_by when a valid link code resolves;
#   NULL for organic / platform-fallback registrations and for every
#   user registered before migration 0035 (historically only the agent
#   is known, not the link). Used for per-link registration counts.
#   Does NOT participate in commission logic -- that stays on
#   referred_by.
#
# JSONB COLUMNS:
#   credentials    -- auth data: {email: {...}, telegram: {...}, onboarding: {...}}
#   profile        -- personal data: {first_name, last_name, country, phone, ...}
#   payout_details -- withdrawal payment methods: free-form JSONB (Sprint 6.3)
#   All JSONB columns use JSONBMixin.set_jsonb() for safe mutation.
#
# KYC STATUS:
#   kyc_status is a denormalized cache of KYCApplication.status.
#   Kept in sync by kyc/service.py on every status change.
#   Used by get_current_user() for fast purchase eligibility checks
#   without a JOIN on kyc_applications.
# =============================================================================

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, TimestampMixin, UUIDMixin


class UserRole(enum.StrEnum):
    """User roles in the platform."""

    INVESTOR = "investor"
    AGENT = "agent"
    COMPANY = "company"
    STAFF = "staff"
    PLATFORM = "platform"


class OnboardingStep(enum.StrEnum):
    """Onboarding funnel position. Moves forward only."""

    REGISTERED = "registered"
    EMAIL_VERIFIED = "email_verified"
    PROFILE_COMPLETE = "profile_complete"
    KYC_DONE = "kyc_done"
    ROLE_SELECTED = "role_selected"
    ONBOARDING_COMPLETE = "onboarding_complete"


class KYCStatus(enum.StrEnum):
    """KYC verification status. Denormalized cache from KYCApplication."""

    NOT_STARTED = "not_started"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    """Platform user -- investor, agent, company, staff, or platform system."""

    __tablename__ = "users"

    # -- Role --
    # Stored as String to match migration (CHECK constraint enforces valid values).
    # Python-side validation uses UserRole enum.
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # -- Status --
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # -- Onboarding --
    onboarding_step: Mapped[str] = mapped_column(
        String(30),
        default=OnboardingStep.REGISTERED,
        server_default=OnboardingStep.REGISTERED.value,
        nullable=False,
    )

    # -- KYC (denormalized cache of KYCApplication.status) --
    kyc_status: Mapped[str] = mapped_column(
        String(20),
        default=KYCStatus.NOT_STARTED,
        server_default=KYCStatus.NOT_STARTED.value,
        nullable=False,
    )

    # -- Referrer (Sprint 7.2) --
    # Every user has a referrer. Platform user references itself.
    # Investors/agents set at registration, immutable after.
    # Commission chain walks up this field (max depth = len(agent_levels)).
    referred_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Referring link (Task 1, migration 0035) --
    # The specific referral link the user registered through. Set
    # alongside referred_by when a valid link code resolves at
    # registration; NULL otherwise (organic, platform fallback, or
    # pre-0035 users). ON DELETE SET NULL: removing a link never
    # blocks or cascades onto users. Indexed for per-link
    # registration aggregates (Block D).
    referred_by_link_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("referral_links.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # -- Auth credentials (JSONB sandbox) --
    # Schema: {
    #   "email": {"email": str, "password_hash": str, "verified": bool, "verified_at": str|null},
    #   "telegram": {"id": int, "username": str|null, "photo_url": str|null, "language_code": str|null},
    #   "onboarding": {"email_token": str|null, "email_token_expires_at": str|null, "email_verification_attempts": int}
    # }
    # Use set_jsonb("credentials", value) for mutations. Never assign directly.
    credentials: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    # -- Personal profile (JSONB sandbox) --
    # Schema: {first_name, last_name, country, phone, avatar_url, ...}
    # Use set_jsonb("profile", value) for mutations.
    profile: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    # -- Payout details (Sprint 6.3) --
    # Free-form JSONB with user's withdrawal payment methods.
    payout_details: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        default=None,
        nullable=True,
    )

    # -- Language --
    language: Mapped[str] = mapped_column(
        String(10),
        default="en",
        server_default="en",
        nullable=False,
    )

    # -- Timestamps (from TimestampMixin, but updated_at needs trigger) --
    # created_at: auto (TimestampMixin)
    # updated_at: nullable, set by DB trigger or application

    # -- Derived properties --

    @property
    def email(self) -> str | None:
        """Email extracted from credentials JSONB. None for Telegram-only users."""
        return (self.credentials or {}).get("email", {}).get("email")
