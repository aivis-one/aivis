# =============================================================================
# AIVIS.ONE Backend -- Commission Constants (Sprint 7.3)
# =============================================================================
#
# Period types for leaderboard snapshots and volume payouts.
# Date helpers shared by worker.py and service.py.
# =============================================================================

from datetime import date, datetime, UTC


class PeriodType:
    """Period type constants for leaderboard and volume bonuses."""

    MONTHLY: str = "monthly"
    QUARTERLY: str = "quarterly"


ALL_PERIOD_TYPES: frozenset[str] = frozenset({
    PeriodType.MONTHLY,
    PeriodType.QUARTERLY,
})


def current_month_start() -> date:
    """First day of current month."""
    now = datetime.now(UTC)
    return date(now.year, now.month, 1)
