# =============================================================================
# CBSHOME Backend -- Processor Base Types (Sprint 6.1, Sprint 4.3 comment,
#                                            Refactor 2 iter 2.4)
# =============================================================================
#
# Core data structures for the Distribution Engine.
#
# ARCHITECTURE:
#   processors/ is a standalone module. It receives PurchaseContext,
#   returns list[Transaction] with invariant SUM(entries) = 0.
#   It knows nothing about HTTP, routers, or sessions.
#   It never commits. Atomic write is the responsibility of
#   execute_purchase() in purchases/service.py.
#
# TYPES:
#   LedgerEntry      -- single ledger write instruction
#   Transaction      -- group of entries with SUM=0 invariant
#   PurchaseContext   -- all data needed to process a purchase
#   ProcessorProtocol -- interface for all processors
#
# FROZEN_UNTIL:
#   Computed by execute_purchase() from MAX(frozen_until) across
#   investor's active_ledger frozen entries. Processor translates
#   it onto all generated entries.
#
# ORIGIN_PAYMENT_ID:
#   Linked to the Payment with MAX frozen_until. Used for reversal
#   chain. May be None if all investor funds are confirmed.
#
# Sprint 4.3 NOTE:
#   PurchaseContext.units stays named `units` -- this is "options the
#   investor receives" (a Purchase-level value), not the immutable
#   package size on Product. The data source on Product is now
#   `package_size` (was `units`); see purchases/service.py where we
#   populate context.units = product.package_size.
#
# Refactor 2 iter 2.4 NOTE (R2 §5.1):
#   investor_language is the ISO 639-1 code used by the engine to
#   resolve the document template snapshot at Purchase creation time.
#   Defaults to "en" so existing tests / call sites that don't supply
#   a language fall back to the platform-default English template.
#   Real call sites populate it from `investor.user.language`.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class LedgerEntry:
    """Single ledger write instruction produced by a processor.

    Does not perform any DB operations. Pure data.
    """

    user_id: UUID
    ledger_type: str  # "active" | "passive"
    amount_cents: int
    reason: str
    origin_payment_id: UUID | None
    frozen_until: datetime | None


@dataclass(frozen=True)
class Transaction:
    """Group of ledger entries representing one logical operation.

    Invariant: sum(e.amount_cents for e in entries) == 0
    Each Transaction creates exactly one Purchase record.
    """

    reason: str  # from LedgerReason
    legal_basis: str  # "sale" | "gift" | "installment_tranche"
    entries: list[LedgerEntry]
    units: int  # share units (0 for non-unit operations)


@dataclass
class PurchaseContext:
    """All data needed by processors to generate transactions.

    Built by execute_purchase() in purchases/service.py.
    Processors read from this context, never mutate it.
    """

    investor_id: UUID
    product_id: UUID
    company_id: UUID
    company_user_id: UUID  # User.id for the company (for passive_ledger)
    platform_user_id: UUID  # Platform system user (double-entry anchor)
    amount_cents: int  # total purchase price (units * price_per_unit_cents)
    units: int  # product.package_size
    price_per_unit_cents: int  # snapshot at purchase time
    distribution_config: dict  # resolved: product override or company fallback
    purchase_config_bonuses: list[dict]  # bonuses from purchase_config or []
    origin_payment_id: UUID | None
    frozen_until: datetime | None
    agent_chain: list[UUID] = field(default_factory=list)  # stub in 6.1
    triggered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Sprint 6.2 (UX-01 / installments):
    # Defaults to "sale" so all existing instant-purchase call sites keep
    # working unchanged. installments/service.pay_tranche overrides both
    # fields so tranche payments are recorded as legal_basis=
    # "installment_tranche" with reason="installment:tranche:{tranche_id}"
    # instead of masquerading as a regular sale in ledger + Purchase rows.
    legal_basis: str = "sale"  # "sale" | "installment_tranche"
    # Ledger reason for the primary ledger entries emitted by
    # PurchaseProcessor. If None -> falls back to LedgerReason.PURCHASE
    # with the usual "{purchase_id}" placeholder (resolved by engine).
    # If provided, must be a fully-resolved string (no placeholders left).
    reason: str | None = None
    # Refactor 2 iter 2.4: ISO 639-1 language for the renderer's
    # 4-stage template fallback (R2 §5.1). Default "en" so older call
    # sites (and the bonus-only context built by complete_plan) keep
    # working through the platform-default English fallback.
    investor_language: str = "en"


class ProcessorProtocol(Protocol):
    """Interface for all processors in the Distribution Engine."""

    def process(self, context: PurchaseContext) -> list[Transaction]:
        """Generate transactions from purchase context.

        Returns list of Transaction, each with SUM(entries) = 0.
        Must be synchronous -- processors are pure logic, no I/O.
        """
        ...
