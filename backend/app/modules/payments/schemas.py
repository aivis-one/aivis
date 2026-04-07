# =============================================================================
# CBSHOME Backend -- Payment Schemas (Sprint 5.2)
# =============================================================================
#
# Request/response schemas for payment endpoints.
#
# SCHEMAS:
#   DepositAddressResponse -- GET /payments/crypto-address/{network}
#   PaymentResponse        -- individual payment in history
#   PaymentHistoryResponse -- GET /payments/history (paginated)
#   CryptoWebhookRequest   -- POST /payments/crypto/webhook
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    amount_usd_cents: int = Field(..., gt=0, description="Amount in USD cents")
    confirmed_block: int | None = Field(
        default=None, description="Block number where tx was confirmed"
    )
    exchange_rate: str = Field(
        default="1.00", description="Crypto to USD exchange rate"
    )
