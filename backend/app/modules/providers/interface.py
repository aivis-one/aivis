# =============================================================================
# AIVIS.ONE Backend -- Payment Provider Interface (Sprint 10.1)
# =============================================================================
#
# Stub protocol for future fiat payment providers (Moonpay/Transak).
#
# PaymentProviderProtocol:
#   Abstraction over payment providers. MVP implements CryptoProvider
#   in payments/service.py. Fiat (MoonpayProvider) -- Phase 2.
#
# NOTE: ProviderPaymentStatus is intentionally NOT named PaymentStatus
#   to avoid collision with payments/constants.py:PaymentStatus which
#   tracks internal payment lifecycle (created/frozen/confirmed/etc.).
#
# Stub types:
#   PaymentIntent         -- provider's response to a payment creation.
#   ProviderPaymentStatus -- provider's response to a payment verification.
# =============================================================================

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class PaymentIntent:
    """Provider's response when creating a new payment (stub)."""

    provider_payment_id: str
    redirect_url: str
    amount_usd: Decimal
    investor_id: UUID


@dataclass(frozen=True)
class ProviderPaymentStatus:
    """Provider's response when verifying a payment (stub).

    Not to be confused with payments.constants.PaymentStatus
    which tracks internal payment lifecycle states.
    """

    provider_payment_id: str
    is_completed: bool
    amount_usd: Decimal


class PaymentProviderProtocol(Protocol):
    """Public interface for external payment providers.

    MVP uses CryptoProvider (inline in payments/service.py).
    Fiat providers (Moonpay, Transak) -- Phase 2.
    """

    async def create_payment(
        self, amount_usd: Decimal, investor_id: UUID
    ) -> PaymentIntent: ...

    async def verify_payment(
        self, payment_id: str
    ) -> ProviderPaymentStatus: ...
