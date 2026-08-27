# =============================================================================
# AIVIS.ONE Backend -- Payment Schemas (Sprint 5.2, updated Sprint 5.3 + 6.1, G2)
# =============================================================================
#
# Request/response schemas for payment endpoints.
#
# SCHEMAS:
#   CreateInvoiceRequest      -- POST /payments/invoices
#   InvoiceResponse           -- invoice surface (create / read / current)
#   SubmitTxidRequest         -- POST /payments/invoices/{id}/txid
#   TxidResultResponse        -- TXID submission outcome
#   PaymentResponse           -- individual payment in history (investor)
#   PaymentHistoryResponse    -- GET /payments/history (paginated)
#
# Sprint 5.3:
#   ReversePaymentRequest     -- POST /staff/payments/{id}/reverse
#   ReversalResponse          -- reversal result summary
#
# G2:
#   StaffPaymentResponse      -- payment with user_id (staff view)
#   StaffPaymentListResponse  -- GET /staff/payments (paginated)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Maximum single deposit: $10M (sanity guard against data errors).
#
# KEPT, AND IT MOVED RATHER THAN SURVIVED. Its only user was the removed
# webhook's amount field. It now bounds the amount a user types into the
# deposit form, which is the same guard against a fat finger that it
# always was -- the removal of the webhook must not silently remove the
# ceiling on a deposit.
MAX_DEPOSIT_CENTS: int = 1_000_000_000


class CreateInvoiceRequest(BaseModel):
    """Request body for opening a deposit invoice.

    ``network`` is a plain string and is NOT checked against a local
    list. Which networks are served is the payments service's fact; it
    answers 400 network_not_supported with the offending value echoed
    back (TOR section 8), and a second list here would be a second
    source of truth that drifts silently (TOR section 11 p.12).

    ``amount_cents`` is floored at 1 because the service floors it at 1
    (``invoice_amount_cents: int = Field(ge=1)``). Validating it here as
    well is not duplication of the service's rule -- it is the
    difference between a user seeing "enter an amount" and a user seeing
    an opaque 422 relayed from a system they do not know exists.
    """

    network: str = Field(..., min_length=1, max_length=32)
    amount_cents: int = Field(..., ge=1, le=MAX_DEPOSIT_CENTS)


class SubmitTxidRequest(BaseModel):
    """Request body for handing one transaction hash to the service.

    No ``min_length``. An empty or malformed hash is not a schema
    error: the service answers 200 with result_code=invalid_format and
    spends no attempt, and turning that into a 422 here would move a
    documented outcome into a different status class and cost the user
    the explanation that comes with it.
    """

    txid: str


class InvoiceResponse(BaseModel):
    """One deposit invoice as the investor screen needs it.

    ``id`` IS THE PRODUCT'S ROW ID, NOT THE SERVICE'S. The service's id
    is never handed to a browser: the routes below take this one, look
    the row up scoped to the authenticated user, and use the service id
    internally. That is what makes an unowned id a 404 instead of a
    successful read of somebody else's invoice.

    The optional fields are optional for one reason each, not as a
    blanket "may be absent": creation does not yet know
    ``attempts_remaining`` (the service returns it on read and on
    submission), and ``credited_amount_cents`` / ``underpaid`` exist
    only once an invoice is confirmed.
    """

    id: UUID
    network: str
    address: str | None
    invoice_amount_cents: int
    status: str
    expires_at: datetime | None
    attempts_remaining: int | None = None
    active_txid: str | None = None
    credited_amount_cents: int | None = None
    underpaid: bool | None = None


class TxidResultResponse(BaseModel):
    """Outcome of one TXID submission.

    ``result_code`` is relayed verbatim from the service and is the only
    thing that says WHY: a submission can be rejected while the invoice
    stays ``created``, and the status alone cannot tell "not found on
    chain" from "wrong address" from "malformed hash".

    A caller must not derive the attempt counter from the result code.
    ``invalid_format`` and ``api_error`` reach an explorer never and
    therefore spend nothing, so ``attempts_remaining`` is reported by
    the service rather than computed here.
    """

    status: str
    result_code: str
    attempts_used: int
    attempts_remaining: int


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
    # R-2.2 Block A: frozen-funded purchases flipped to REVERSED as
    # part of this payment reversal (their debits inherited the
    # deposit's origin_payment_id and were captured by the unwind).
    purchases_reversed: int
    # Tranche-unwind: installment tranches whose funding this payment
    # provided. Each entry: {tranche_id, plan_id, plan_outcome
    # ("defaulted" | "completed_flagged" | terminal status),
    # cancelled_count}. Empty when no tranche debits were captured.
    tranches_unwound: list[dict] = []
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
