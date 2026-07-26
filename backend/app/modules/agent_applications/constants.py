# =============================================================================
# AIVIS.ONE Backend -- Agent Application Constants (Sprint 7.1)
# =============================================================================
#
# STATUSES:
#   pending   -- submitted, awaiting Staff decision
#   approved  -- approved, user.role changed to agent (terminal)
#   rejected  -- rejected, cooldown applies before resubmission
#
# TRANSITIONS:
#   pending  -> approved  (Staff)
#   pending  -> rejected  (Staff)
#
# Note: rejected -> pending is modeled as a NEW AgentApplication row,
# not a status change on the old row. The old row stays rejected.
# =============================================================================

import enum

from app.core.exceptions import BadRequestError


class AgentApplicationStatus(enum.StrEnum):
    """Agent application lifecycle statuses."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# Valid transitions: {current_status: {allowed_next_statuses}}.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    AgentApplicationStatus.PENDING: frozenset({
        AgentApplicationStatus.APPROVED,
        AgentApplicationStatus.REJECTED,
    }),
    # approved and rejected are terminal (no outgoing transitions).
}


def validate_transition(current: str, target: str) -> None:
    """Validate a status transition.

    Raises:
        BadRequestError: If the transition is not allowed.
    """
    allowed = VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise BadRequestError(
            f"Invalid transition: {current} -> {target}. "
            f"Allowed from {current}: {sorted(allowed) if allowed else 'none (terminal)'}"
        )
