# =============================================================================
# CBSHOME Backend -- Installment Constants (Sprint 6.2)
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
#
# STATE MACHINES (from CBSHOME-State-Machines.md v1.4):
#
#   InstallmentPlan:
#     active    -> completed  (all tranches paid)
#     active    -> defaulted  (tranche overdue > limit)
#     active    -> cancelled  (admin cancellation)
#
#   InstallmentTranche:
#     scheduled -> paid       (daemon: due_date <= today AND funds sufficient)
#     scheduled -> overdue    (daemon: due_date <= today AND funds insufficient)
#     scheduled -> cancelled  (plan -> cancelled or defaulted)
#     overdue   -> paid       (daemon: funds appeared within grace period)
#     overdue   -> defaulted  (daemon: overdue > INSTALLMENT_DEFAULT_DAYS)
#     overdue   -> cancelled  (plan -> cancelled)
#
# TERMINAL STATUSES:
#   Plan:    completed, defaulted, cancelled
#   Tranche: paid, defaulted, cancelled
#
# RULE: All columns use String (not SAEnum) to avoid PostgreSQL type
# conflicts in migrations.
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
    # Terminal statuses -- no transitions out.
    InstallmentTrancheStatus.PAID: frozenset(),
    InstallmentTrancheStatus.DEFAULTED: frozenset(),
    InstallmentTrancheStatus.CANCELLED: frozenset(),
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
