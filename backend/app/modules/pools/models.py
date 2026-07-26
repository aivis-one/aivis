# =============================================================================
# AIVIS.ONE Backend -- Option Pool Models (Sprint 4.3)
# =============================================================================
#
# OptionPool:
#   Pool of options a company has allocated for sale on the platform.
#   One active pool per company is enforced by a partial unique index:
#     CREATE UNIQUE INDEX uq_one_active_pool_per_company
#       ON option_pools (company_id) WHERE status = 'active';
#
#   total_supply (number of options covering 100% of company shares) lives
#   on CompanyProfile, NOT here. Pool only stores its share of that supply
#   plus the absolute count of options it offers. Price also lives on
#   CompanyProfile (a re-valuation does not need a new pool).
#
# LIFECYCLE:
#   active   -- pool currently sells through products
#   archived -- pool frozen (e.g. after a future split, see spec section 4)
#
# SOURCE OF TRUTH RULES:
#   Creation: staff sets equity_percent.
#             total_options = company.total_supply * equity_percent / 100
#   Edit:     staff sets total_options (допэмиссия).
#             equity_percent = total_options / company.total_supply * 100
#   Split:    new pool with new denomination, old pool -> archived.
#             Implementation deferred (future scope).
#
# NUMERIC PRECISION:
#   equity_percent stored as Numeric(7, 4). Range 0.0000 .. 999.9999.
#   Decimal is used in Python because float would round binary fractions
#   on a financial percentage. Standard for monetary / percentage fields
#   in this project (see ledgers, withdrawals BigInteger cents pattern).
# =============================================================================

from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin


class OptionPool(UUIDMixin, TimestampMixin, Base):
    """Pool of options allocated for sale on the platform.

    One active pool per company at any time. Enforced by a partial unique
    index `uq_one_active_pool_per_company` on `(company_id) WHERE status='active'`
    (created in migration 0027).
    """

    __tablename__ = "option_pools"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Share of company supply allocated for platform sale.
    # Example: Decimal("10.0000") = 10% of total_supply.
    equity_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )

    # Absolute number of options in this pool.
    # At creation: derived from total_supply * equity_percent / 100.
    # On edit (допэмиссия): staff sets this directly, equity_percent is recomputed.
    total_options: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Lifecycle. Allowed values: "active", "archived".
    # CHECK constraint enforced at DB level (migration 0027).
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<OptionPool id={self.id} company={self.company_id} "
            f"equity={self.equity_percent}% total={self.total_options} "
            f"status={self.status}>"
        )
