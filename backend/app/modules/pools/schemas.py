# =============================================================================
# CBSHOME Backend -- Pool Schemas (Sprint 4.3)
# =============================================================================
#
# REQUEST SCHEMAS:
#   CreatePoolRequest -- POST   /staff/companies/{id}/pool
#                        Caller specifies equity_percent (the share of
#                        company total_supply allocated for sale).
#                        total_options is derived: company.total_supply
#                        * equity_percent / 100.
#   UpdatePoolRequest -- PATCH  /staff/companies/{id}/pool
#                        Caller specifies total_options directly
#                        (допэмиссия). equity_percent is recomputed:
#                        new_total_options / company.total_supply * 100.
#                        See spec §5.1 for rationale.
#
# RESPONSE SCHEMAS:
#   PoolResponse -- pool fields plus computed derivations:
#                     consumed (SUM of active Purchase.units),
#                     remaining (total_options - consumed; can be
#                     negative when gifts have overflowed into owner
#                     supply).
#
# DECIMAL:
#   equity_percent uses Decimal in the response (matches the column
#   type Numeric(7, 4)) so floats don't round at the API boundary.
#   Pydantic serializes Decimal as a JSON string by default, which
#   is what we want -- the frontend should parse it back as a
#   number explicitly. Service layer accepts Decimal-or-int from
#   Pydantic and stores Decimal.
# =============================================================================

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreatePoolRequest(BaseModel):
    """Create a new active pool for a company.

    equity_percent: percentage of company.total_supply to allocate for
    sale. Must be > 0 and <= 100. The actual total_options is computed
    server-side as floor(company.total_supply * equity_percent / 100).
    """

    model_config = ConfigDict(extra="forbid")

    equity_percent: Decimal = Field(
        gt=Decimal("0"),
        le=Decimal("100"),
        max_digits=7,
        decimal_places=4,
    )


class UpdatePoolRequest(BaseModel):
    """Update an existing active pool's total_options (допэмиссия).

    total_options: new absolute number of options in the pool.
    Must be > 0 and <= company.total_supply (validated in service).
    The service rejects values below already-consumed options.

    equity_percent is recomputed by the service based on the new
    total_options. Callers do not pass it.
    """

    model_config = ConfigDict(extra="forbid")

    total_options: int = Field(gt=0)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class PoolResponse(BaseModel):
    """Pool info with computed consumption and remaining options.

    consumed and remaining are NOT columns on OptionPool -- they are
    aggregated at request time from active Purchase rows of the same
    company. Service layer fills them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    equity_percent: Decimal
    total_options: int
    status: str
    created_at: datetime
    updated_at: datetime | None

    # Computed (not on the model):
    # SUM(Purchase.units) for active purchases of this company.
    consumed: int = 0
    # total_options - consumed. Can be negative when gifts have
    # overflowed into owner supply (see spec §3.7). The router
    # renders both numbers as-is; clients decide how to display
    # the overflow case.
    remaining: int = 0
