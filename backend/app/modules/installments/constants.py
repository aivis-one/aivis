# =============================================================================
# AIVIS.ONE Backend -- Installment Constants (Sprint 6.2, tranche-unwind R51+)
# =============================================================================
#
# INSTALLMENT PLAN STATUS:
#   active    -- plan is in progress, tranches being paid
#   completed -- all tranches paid, bonuses awarded
#   defaulted -- overdue tranche exceeded INSTALLMENT_DEFAULT_DAYS
#   cancelled -- plan cancelled (admin action, future sprint)
#
# INSTALLMENT TRANCHE STATUS:
#   scheduled -- awaiting due_date
#   paid      -- paid, purchase_id NOT NULL
#   overdue   -- due_date passed, insufficient funds
#   defaulted -- overdue exceeded INSTALLMENT_DEFAULT_DAYS
#   cancelled -- cancelled due to plan default/cancellation
#   reversed  -- the payment that funded this PAID tranche was
#                charged back (tranche-unwind); terminal
#
# STATE MACHINES (from AIVIS-State-Machines.md v1.4 + tranche-unwind):
#
#   InstallmentPlan:
#     active    -> completed  (all tranches paid)
#     active    -> defaulted  (tranche overdue > limit, OR funding of a
#                              paid tranche reversed -- boss-locked
#                              tranche-unwind semantics)
#     active    -> cancelled  (admin cancellation)
#
#   InstallmentTranche:
#     scheduled -> paid       (daemon: due_date <= today AND funds sufficient)
#     scheduled -> overdue    (daemon: due_date <= today AND funds insufficient)
#     scheduled -> cancelled  (plan -> cancelled or defaulted)
#     overdue   -> paid       (daemon: funds appeared within grace period)
#     overdue   -> defaulted  (daemon: overdue > INSTALLMENT_DEFAULT_DAYS)
#     overdue   -> cancelled  (plan -> cancelled)
#     paid      -> reversed   (funding payment charged back; the ONLY
#                              transition out of paid, executed solely
#                              by the payment-reversal unwind)
#
# TERMINAL STATUSES:
#   Plan:    completed, defaulted, cancelled
#   Tranche: paid (except -> reversed), defaulted, cancelled, reversed
#
# RULE: All columns use String (not SAEnum) to avoid PostgreSQL type
# conflicts in migrations. The DB CHECK ck_installment_tranches_status
# mirrors the tranche enum -- migration 0038 added 'reversed'.
# =============================================================================

import enum

from app.core.exceptions import BadRequestError


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InstallmentPlanStatus(enum.StrEnum):
    """Installment plan lifecycle status."""

    ACTIVE = "active"
    COMPLETED = "completed"
    DEFAULTED = "defaulted"
    CANCELLED = "cancelled"


class InstallmentTrancheStatus(enum.StrEnum):
    """Installment tranche lifecycle status."""

    SCHEDULED = "scheduled"
    PAID = "paid"
    OVERDUE = "overdue"
    DEFAULTED = "defaulted"
    CANCELLED = "cancelled"
    REVERSED = "reversed"


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------

VALID_PLAN_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    InstallmentPlanStatus.ACTIVE: frozenset({
        InstallmentPlanStatus.COMPLETED,
        InstallmentPlanStatus.DEFAULTED,
        InstallmentPlanStatus.CANCELLED,
    }),
    # Terminal statuses -- no transitions out.
    InstallmentPlanStatus.COMPLETED: frozenset(),
    InstallmentPlanStatus.DEFAULTED: frozenset(),
    InstallmentPlanStatus.CANCELLED: frozenset(),
}

VALID_TRANCHE_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    InstallmentTrancheStatus.SCHEDULED: frozenset({
        InstallmentTrancheStatus.PAID,
        InstallmentTrancheStatus.OVERDUE,
        InstallmentTrancheStatus.CANCELLED,
    }),
    InstallmentTrancheStatus.OVERDUE: frozenset({
        InstallmentTrancheStatus.PAID,
        InstallmentTrancheStatus.DEFAULTED,
        InstallmentTrancheStatus.CANCELLED,
    }),
    # Tranche-unwind (boss-locked): the funding payment of a PAID
    # tranche was charged back. Executed only by the payment-reversal
    # unwind path -- pay_tranche and the daemons never set it.
    InstallmentTrancheStatus.PAID: frozenset({
        InstallmentTrancheStatus.REVERSED,
    }),
    # Terminal statuses -- no transitions out.
    InstallmentTrancheStatus.DEFAULTED: frozenset(),
    InstallmentTrancheStatus.CANCELLED: frozenset(),
    InstallmentTrancheStatus.REVERSED: frozenset(),
}


# ---------------------------------------------------------------------------
# Status transition validators
# ---------------------------------------------------------------------------


def validate_plan_status_transition(
    current: str,
    new: str,
) -> None:
    """Validate that an installment plan status transition is allowed.

    Raises:
        BadRequestError: If transition is not in the state machine.
    """
    allowed = VALID_PLAN_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise BadRequestError(
            f"Cannot transition installment plan from '{current}' to '{new}'"
        )


def validate_tranche_status_transition(
    current: str,
    new: str,
) -> None:
    """Validate that an installment tranche status transition is allowed.

    Raises:
        BadRequestError: If transition is not in the state machine.
    """
    allowed = VALID_TRANCHE_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise BadRequestError(
            f"Cannot transition installment tranche from '{current}' to '{new}'"
        )
