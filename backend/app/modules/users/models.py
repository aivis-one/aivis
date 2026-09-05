# =============================================================================
# AIVIS.ONE Backend -- User Model
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
    ROLE_SELECTED = "role_selected"
    ONBOARDING_COMPLETE = "onboarding_complete"


class KYCStatus(enum.StrEnum):
    """The KYC status vocabulary, for the application and its cache.

    ONE ENUM FOR BOTH COLUMNS (H12 P-46f). users.kyc_status is a
    denormalised cache of kyc_applications.status, and until this pass
    each had its own enum with identical members -- two declarations of
    one fact, plus two CHECK constraints that stayed level only because
    somebody remembered to edit both. kyc/models.py imports this one.
    tests/test_kyc.py reads both constraints out of pg_constraint and
    asserts each admits exactly these members, so a future widening
    that touches one column and not the other goes red the day it
    lands rather than the day a value is written.
    """

    NOT_STARTED = "not_started"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    # DISTINCT FROM REJECTED, AND THE DISTINCTION IS FOR THE READER OF
    # THE QUEUE. "rejected" says the person did not pass; "revoked" says
    # we took back a decision we had already made. Folding the second
    # into the first would make the audit trail claim the person failed
    # verification when what happened is that staff changed their mind.
    REVOKED = "revoked"


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

    # -- Seed marker (T-72, migration 0044) --
    # NULL for every person who arrived through the product. Set ONLY by
    # scripts/seed.py, to the name of the profile that created the row.
    #
    # WHY A COLUMN AND NOT A CONVENTION. `seed --reset` has to answer
    # "is this row mine" before it deletes anything, and every cheaper
    # answer is wrong here: uuid primary keys have no reserved range to
    # carve out (the reference implementation's trick), and an e-mail
    # domain is not a border -- nothing stops a real person registering
    # at the demo domain, and --reset would then delete them. The cost
    # is honest and was accepted deliberately: a product column that
    # exists for a development tool.
    #
    # The value is the PROFILE NAME, not a boolean, so two profiles on
    # one stand can be reset independently and so a row can say which
    # demo it belongs to.
    seeded_profile: Mapped[str | None] = mapped_column(
        String(64),
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

    @property
    def two_factor_enabled(self) -> bool:
        """Whether TOTP 2FA is active (TASK-38).

        Derived from credentials.totp.enabled -- see
        users/service.py's "Two-Factor Authentication (TOTP)" module
        note for the full storage shape. Surfaced on UserResponse
        (users/schemas.py) via Pydantic's from_attributes=True, the
        same mechanism that already exposes the `email` property above
        -- no separate status endpoint needed for
        components/shared/TwoFactorSection.vue to know which UI state
        (enable vs. disable) to render.
        """
        return bool(((self.credentials or {}).get("totp") or {}).get("enabled"))
