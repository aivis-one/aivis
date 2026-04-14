# =============================================================================
# CBSHOME Backend -- Payment Schemas (Sprint 5.2, updated Sprint 5.3 + 6.1, G2)
# =============================================================================
#
# Request/response schemas for payment endpoints.
#
# SCHEMAS:
#   CreateAddressRequest      -- POST /payments/crypto-address
#   DepositAddressResponse    -- POST /payments/crypto-address response
#   PaymentResponse           -- individual payment in history (investor)
#   PaymentHistoryResponse    -- GET /payments/history (paginated)
#   CryptoWebhookRequest      -- POST /payments/crypto/webhook
#
# Sprint 5.3:
#   ReversePaymentRequest     -- POST /staff/payments/{id}/reverse
#   ReversalResponse          -- reversal result summary
#
# Sprint 6.1 FIX:
#   CryptoWebhookRequest.amount_usd_cents -- added upper bound (MAX_DEPOSIT_CENTS)
#
# G2:
#   StaffPaymentResponse      -- payment with user_id (staff view)
#   StaffPaymentListResponse  -- GET /staff/payments (paginated)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Maximum single deposit: $10M (sanity guard against data errors).
# Adjustable in config if needed for larger deposits.
MAX_DEPOSIT_CENTS: int = 1_000_000_000


class CreateAddressRequest(BaseModel):
    """Request body for creating/getting a crypto deposit address."""

    network: str = Field(..., description="Crypto network: TRC20, ERC20, BEP20, PoS")


class DepositAddressResponse(BaseModel):
    """Response for crypto deposit address endpoint."""

    address: str
    network: str
    user_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PaymentResponse(BaseModel):
    """Individual payment in history listing."""

    id: UUID
    amount_cents: int
    currency: str
    payment_type: str
    provider: str
    status: str
    frozen_until: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PaymentHistoryResponse(BaseModel):
    """Paginated payment history response."""

    items: list[PaymentResponse]
    total: int
    page: int
    per_page: int


class CryptoWebhookRequest(BaseModel):
    """Incoming crypto webhook payload.

    Stub schema -- real provider will have different fields.
    This captures the minimum needed to create a Payment and
    record an active_ledger entry.
    """

    network: str = Field(..., description="Crypto network: TRC20, ERC20, etc.")
    to_address: str = Field(..., description="Our deposit address")
    from_address: str = Field(..., description="Sender wallet address")
    tx_hash: str = Field(..., description="Blockchain transaction hash")
    amount_crypto: str = Field(..., description="Amount in crypto units (string)")
    amount_usd_cents: int = Field(
        ...,
        gt=0,
        le=MAX_DEPOSIT_CENTS,
        description="Amount in USD cents (max $10M per deposit)",
    )
    confirmed_block: int | None = Field(
        default=None, description="Block number where tx was confirmed"
    )
    exchange_rate: str = Field(
        default="1.00", description="Crypto to USD exchange rate"
    )


# ---------------------------------------------------------------------------
# Reversal (Sprint 5.3)
# ---------------------------------------------------------------------------


class ReversePaymentRequest(BaseModel):
    """Request body for payment reversal (chargeback)."""

    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the reversal",
    )


class ReversalResponse(BaseModel):
    """Reversal result summary."""

    payment_id: UUID
    total_reversed_cents: int
    active_entries_reversed: int
    passive_entries_reversed: int
    affected_user_ids: list[UUID]


# ---------------------------------------------------------------------------
# Staff payment list (G2)
# ---------------------------------------------------------------------------


class StaffPaymentResponse(PaymentResponse):
    """Payment with user_id for staff views."""

    user_id: UUID


class StaffPaymentListResponse(BaseModel):
    """Paginated payment list for staff."""

    items: list[StaffPaymentResponse]
    total: int
    page: int
    per_page: int
