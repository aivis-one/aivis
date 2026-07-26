# =============================================================================
# AIVIS.ONE Backend -- Payment Interface (Sprint 5.2)
# =============================================================================
#
# PUBLIC BOUNDARY of the payments/ module.
#
# PaymentServiceProtocol:
#   The only way external modules interact with payments.
#   Internal tables (crypto_addresses), provider logic, webhook parsing
#   are hidden behind this interface.
#
# DepositAddress:
#   Lightweight dataclass returned to callers. Does NOT expose
#   CryptoAddress model internals.
# =============================================================================

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.payments.models import Payment


@dataclass(frozen=True)
class DepositAddress:
    """Public representation of a crypto deposit address."""

    address: str
    network: str
    user_id: UUID


class PaymentServiceProtocol(Protocol):
    """Public interface for the payments module.

    External modules interact with payments ONLY through this protocol.
    """

    async def get_or_create_deposit_address(
        self, user_id: UUID, network: str
    ) -> DepositAddress: ...

    async def get_payment(
        self, payment_id: UUID
    ) -> Payment: ...
