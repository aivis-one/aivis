# =============================================================================
# AIVIS.ONE Backend -- Token Interface (Sprint 10.1)
# =============================================================================
#
# Stub protocol for future Solana tokenization (Q3 2027).
#
# TokenServiceProtocol:
#   Defines how external modules will interact with token issuance
#   and holdings queries. Not implemented in MVP.
#
# Stub types:
#   TokenIssuance -- result of issuing tokens to an investor.
#   TokenHolding  -- single holding record for portfolio display.
# =============================================================================

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TokenIssuance:
    """Result of a token issuance operation (stub)."""

    issuance_id: UUID
    investor_id: UUID
    product_id: UUID
    amount: int


@dataclass(frozen=True)
class TokenHolding:
    """Single token holding record for an investor (stub)."""

    holding_id: UUID
    investor_id: UUID
    product_id: UUID
    amount: int


class TokenServiceProtocol(Protocol):
    """Public interface for the tokens module.

    Solana utility tokens -- conversion to security tokens.
    Implementation deferred to Phase 2 (Q3 2027).
    """

    async def issue_tokens(
        self, investor_id: UUID, amount: int, product_id: UUID
    ) -> TokenIssuance: ...

    async def get_holdings(
        self, investor_id: UUID
    ) -> list[TokenHolding]: ...
