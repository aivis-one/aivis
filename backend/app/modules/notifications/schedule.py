# =============================================================================
# AIVIS.ONE Backend -- Notifications: quiet hours <-> comms' allowed periods
#                      (H23 P-114)
# =============================================================================
#
# The settings screen offers QUIET HOURS: one window, `from` -> `to`, on a
# set of days, during which the person does not want to be disturbed.
# comms stores the OPPOSITE: the periods in which it MAY deliver, one day
# per period, never crossing midnight (comms deploy/INTEGRATION.md,
# section 6). Sending the quiet window as-is would store the reverse of
# what the person chose -- which is exactly what the pre-H23 proxy would
# have done had comms accepted its shape; it never did, so no schedule was
# ever stored.
#
# This module is the ONLY place the two forms meet. Both directions are
# pure functions over minutes of the day, so they are tested as a pair:
# writing and reading back must return the window the person chose.
#
# THE WINDOW'S MEANING, which both directions share:
#   * `days` are the days the window STARTS on;
#   * from < to: the window lies inside its day;
#   * from > to: it runs past midnight -- [from, 24:00) on its day and
#     [00:00, to) on the next one, sun wrapping to mon; to == 00:00 means
#     it ends exactly at midnight and spills nothing;
#   * from == to is refused before it gets here (ScheduleIn).
# Every day's allowed periods are the complement of that day's quiet
# minutes. A window is shorter than a day, so no day is ever fully quiet
# and the list comms receives is never empty -- comms refuses an empty
# list (clearing is `null`, never []).
#
# READING BACK. comms' periods are written by this product's screen and
# by nothing else: the server starts on an empty comms database and no
# other writer touches these recipients. So every stored schedule is the
# image of some window, and periods_to_quiet recovers it. A schedule it
# cannot recover is a defect of this module, not a state of the product:
# it raises, the caller logs it as an error and answers 502. There is
# deliberately no "custom schedule" rendering -- it would describe a
# state that cannot happen.
# =============================================================================

from typing import Any

from app.modules.notifications.schemas import DAY_CODES, ScheduleIn, ScheduleOut

_DAY_MINUTES = 24 * 60


class ScheduleUnreadable(ValueError):
    """comms' periods are not the image of any quiet window."""


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _hhmm(minutes: int) -> str:
    # 1440 is written 24:00 -- comms' "end of the day", valid only as `to`.
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _quiet_by_day(
    start: int, end: int, days: list[str]
) -> dict[int, list[tuple[int, int]]]:
    """Quiet minute ranges per day index for one window."""
    quiet: dict[int, list[tuple[int, int]]] = {i: [] for i in range(7)}
    for day in days:
        index = DAY_CODES.index(day)
        if start < end:
            quiet[index].append((start, end))
        else:
            quiet[index].append((start, _DAY_MINUTES))
            if end > 0:
                quiet[(index + 1) % 7].append((0, end))
    return quiet


def _allowed(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The complement of one day's quiet ranges within [0, 1440]."""
    allowed: list[tuple[int, int]] = []
    cursor = 0
    for start, end in sorted(ranges):
        if start > cursor:
            allowed.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < _DAY_MINUTES:
        allowed.append((cursor, _DAY_MINUTES))
    return allowed


def _periods(start: int, end: int, days: list[str]) -> list[dict[str, str]]:
    quiet = _quiet_by_day(start, end, days)
    periods: list[dict[str, str]] = []
    for index, day in enumerate(DAY_CODES):
        for period_start, period_end in _allowed(quiet[index]):
            periods.append(
                {"day": day, "from": _hhmm(period_start), "to": _hhmm(period_end)}
            )
    return periods


def quiet_to_periods(window: ScheduleIn | None) -> list[dict[str, str]] | None:
    """The screen's quiet window as comms' allowed periods; None clears."""
    if window is None:
        return None
    days = [day for day in DAY_CODES if day in window.days]
    return _periods(_minutes(window.from_), _minutes(window.to), days)


def _normalised(periods: list[Any]) -> list[tuple[str, str, str]]:
    try:
        return sorted(
            (item["day"], item["from"], item["to"]) for item in periods
        )
    except (KeyError, TypeError) as exc:
        raise ScheduleUnreadable(f"a period is malformed: {exc}") from exc


def periods_to_quiet(periods: list[Any] | None) -> ScheduleOut | None:
    """comms' allowed periods back as the window that produced them.

    Candidates are taken from the quiet ranges the periods leave: a
    window starts where some quiet range starts and ends where some
    quiet range ends (24:00 read as a window ending at midnight). The
    first candidate whose forward image equals the stored periods is the
    answer. Raises ScheduleUnreadable when none does -- see the header.
    """
    if periods is None:
        return None
    if not isinstance(periods, list) or not periods:
        raise ScheduleUnreadable(
            f"expected a non-empty list or null, got {periods!r}"
        )

    target = _normalised(periods)

    allowed: dict[int, list[tuple[int, int]]] = {i: [] for i in range(7)}
    for day, start, end in target:
        if day not in DAY_CODES:
            raise ScheduleUnreadable(f"unknown day {day!r}")
        allowed[DAY_CODES.index(day)].append((_minutes(start), _minutes(end)))

    starts: set[int] = set()
    ends: set[int] = set()
    for index in range(7):
        for quiet_start, quiet_end in _allowed(allowed[index]):
            starts.add(quiet_start)
            ends.add(0 if quiet_end == _DAY_MINUTES else quiet_end)

    for start in sorted(starts):
        for end in sorted(ends):
            if start == end:
                continue
            days = [
                day
                for index, day in enumerate(DAY_CODES)
                if any(
                    quiet_start == start
                    for quiet_start, _ in _allowed(allowed[index])
                )
            ]
            if not days:
                continue
            if _normalised(_periods(start, end, days)) == target:
                return ScheduleOut(from_=_hhmm(start), to=_hhmm(end), days=days)

    raise ScheduleUnreadable(f"no quiet window produces {target!r}")
