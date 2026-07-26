# =============================================================================
# AIVIS.ONE Backend -- Installment Scheduler (Sprint 6.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Calculate due dates for installment tranches using the february rule.
#
# FEBRUARY RULE (from AIVIS-Installment.md v1.1):
#   When start_date.day exceeds the last day of the target month, clamp
#   to the last day of that month. This ensures predictable dates for
#   the investor.
#
#   Examples:
#     start=Dec 31, offset=1 -> Jan 31
#     start=Dec 31, offset=2 -> Feb 28 (or 29 in leap year)
#     start=Dec 31, offset=3 -> Mar 31
#     start=Dec 31, offset=4 -> Apr 30
#     start=Jan 28, offset=1 -> Feb 28
#     start=Jan 28, offset=2 -> Mar 28
#
# USAGE:
#   from app.modules.installments.scheduler import calculate_due_date
#   due = calculate_due_date(date(2026, 12, 31), month_offset=2)
#   # -> date(2027, 2, 28)
# =============================================================================

import calendar
from datetime import date


def calculate_due_date(start_date: date, month_offset: int) -> date:
    """Calculate tranche due date with february rule (last-day-of-month clamping).

    Args:
        start_date: Date the installment plan was created.
        month_offset: Number of months from start (1..N).
            0 is not valid here -- tranche 0 uses start_date directly.

    Returns:
        Target date, clamped to last day of month if needed.

    Raises:
        ValueError: If month_offset < 1.
    """
    if month_offset < 1:
        raise ValueError(f"month_offset must be >= 1, got {month_offset}")

    # Calculate target year/month.
    total_months = start_date.month + month_offset
    target_year = start_date.year + (total_months - 1) // 12
    target_month = ((total_months - 1) % 12) + 1

    # Clamp day to last day of target month.
    last_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(start_date.day, last_day)

    return date(target_year, target_month, target_day)
