# =============================================================================
# CBSHOME Backend -- Referral Models (Sprint 7.2)
# =============================================================================
#
# ReferralLink:
#   Agent-owned referral link with unique code. Used to track which agent
#   brought an investor to the platform. Code is generated via
#   secrets.token_urlsafe(6) -> 8 alphanumeric chars.
#
# ReferralAttribution:
#   Immutable record linking a purchase to a referral link (or NULL for
#   organic purchases). Created for EVERY purchase regardless of source.
#   Used for stats/reporting, NOT for commission calculation (that uses
#   User.referred_by chain).
#
# RULES:
#   - ReferralLink.code is unique (partial retry on collision).
#   - ReferralAttribution is immutable (no updated_at).
#   - referral_link_id=NULL means organic purchase (no referral link used).
#   - Agent hierarchy lives in User.referred_by, not here.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import UUIDMixin


class ReferralLink(UUIDMixin, Base):
    """Agent-owned referral link with unique tracking code."""

    __tablename__ = "referral_links"

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ReferralLink id={self.id} agent={self.agent_id} "
            f"code={self.code}>"
        )


class ReferralAttribution(UUIDMixin, Base):
    """Immutable record linking a purchase to its referral source.

    Created for every purchase. referral_link_id=NULL for organic traffic.
    """

    __tablename__ = "referral_attributions"

    purchase_id: Mapped[UUID] = mapped_column(
        ForeignKey("purchases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    referral_link_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("referral_links.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ReferralAttribution id={self.id} purchase={self.purchase_id} "
            f"link={self.referral_link_id}>"
        )
