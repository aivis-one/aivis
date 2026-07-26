# =============================================================================
# AIVIS.ONE Backend -- Withdrawal Constants (Sprint 6.3)
# =============================================================================
#
# ENUMS:
#   WithdrawalStatus -- pending | confirmed | processing | completed |
#                       rejected | failed
#
# STATE MACHINE (from AIVIS-State-Machines.md section 4, extended):
#   pending    -> confirmed   (Staff: approved)
#   pending    -> rejected    (Staff: declined with reason)
#   confirmed  -> processing  (system: pushed to payment provider)
#   processing -> completed   (system/webhook: provider confirmed payout)
#   processing -> failed      (system/webhook: provider rejected payout)
#
# Terminal statuses: completed, rejected, failed.
#
# RULE: All columns use String (not SAEnum) to avoid PostgreSQL type
# conflicts in migrations.
# =============================================================================

import enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WithdrawalStatus(enum.StrEnum):
    """Withdrawal lifecycle status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Non-terminal statuses (used by partial unique index)
# ---------------------------------------------------------------------------

ACTIVE_WITHDRAWAL_STATUSES: frozenset[str] = frozenset({
    WithdrawalStatus.PENDING,
    WithdrawalStatus.CONFIRMED,
    WithdrawalStatus.PROCESSING,
})


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------

VALID_WITHDRAWAL_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    WithdrawalStatus.PENDING: frozenset({
        WithdrawalStatus.CONFIRMED,
        WithdrawalStatus.REJECTED,
    }),
    WithdrawalStatus.CONFIRMED: frozenset({
        WithdrawalStatus.PROCESSING,
    }),
    WithdrawalStatus.PROCESSING: frozenset({
        WithdrawalStatus.COMPLETED,
        WithdrawalStatus.FAILED,
    }),
    # Terminal statuses -- no transitions out.
    WithdrawalStatus.COMPLETED: frozenset(),
    WithdrawalStatus.REJECTED: frozenset(),
    WithdrawalStatus.FAILED: frozenset(),
}


# ---------------------------------------------------------------------------
# Status transition validator
# ---------------------------------------------------------------------------


def validate_withdrawal_status_transition(
    current: str,
    new: str,
) -> None:
    """Validate that a withdrawal status transition is allowed.

    Raises:
        BadRequestError: If transition is not in the state machine.
    """
    from app.core.exceptions import BadRequestError

    allowed = VALID_WITHDRAWAL_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise BadRequestError(
            f"Cannot transition withdrawal from '{current}' to '{new}'"
        )
