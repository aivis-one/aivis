# =============================================================================
# CBSHOME Backend -- Commission Constants (Sprint 7.3)
# =============================================================================
#
# Period types for leaderboard snapshots and volume payouts.
# =============================================================================


class PeriodType:
    """Period type constants for leaderboard and volume bonuses."""

    MONTHLY: str = "monthly"
    QUARTERLY: str = "quarterly"


ALL_PERIOD_TYPES: frozenset[str] = frozenset({
    PeriodType.MONTHLY,
    PeriodType.QUARTERLY,
})
