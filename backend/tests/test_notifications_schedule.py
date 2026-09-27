# =============================================================================
# AIVIS.ONE Backend -- quiet hours <-> comms' allowed periods (H23 P-114)
# =============================================================================
#
# notifications/schedule.py is the only place the screen's quiet window and
# comms' allowed periods meet. The invariant guarded here: whatever window
# a person chooses, what is written to comms follows comms' rules, and
# reading it back returns exactly that window. A window it cannot read
# back is a defect of the conversion (the module header says why no one
# else writes these schedules), and it must fail loudly.
# =============================================================================

import itertools

import pytest
from pydantic import ValidationError

from app.modules.notifications.schedule import (
    ScheduleUnreadable,
    periods_to_quiet,
    quiet_to_periods,
)
from app.modules.notifications.schemas import DAY_CODES, ScheduleIn

_SHAPES = {
    "inside_the_day": ("09:00", "17:30"),
    "past_midnight": ("22:00", "07:00"),
}


def _window(from_: str, to: str, days: list[str]) -> ScheduleIn:
    return ScheduleIn(**{"from": from_, "to": to, "days": days})


def _check_comms_rules(periods: list[dict[str, str]]) -> None:
    """comms deploy/INTEGRATION.md section 6, as a checker."""
    assert periods, "comms refuses an empty list; clearing is null"
    by_day: dict[str, list[tuple[str, str]]] = {}
    for period in periods:
        assert set(period) == {"day", "from", "to"}
        assert period["day"] in DAY_CODES
        assert period["from"] < period["to"]
        assert period["from"] < "24:00" and period["to"] <= "24:00"
        by_day.setdefault(period["day"], []).append((period["from"], period["to"]))
    for spans in by_day.values():
        spans.sort()
        for (_, end), (start, _) in zip(spans, spans[1:]):
            assert end < start, "periods of one day neither overlap nor touch"


@pytest.mark.parametrize("day", DAY_CODES)
@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("width", ["one_day", "every_day"])
def test_a_window_round_trips_through_comms_form(
    day: str, shape: str, width: str
) -> None:
    """7 days x {inside the day, past midnight} x {1 day, 7 days}."""
    from_, to = _SHAPES[shape]
    days = [day] if width == "one_day" else list(DAY_CODES)

    periods = quiet_to_periods(_window(from_, to, days))

    _check_comms_rules(periods)
    back = periods_to_quiet(periods)
    assert back is not None
    assert (back.from_, back.to, back.days) == (from_, to, days)


def test_a_window_past_midnight_quiets_the_next_morning() -> None:
    """The window's meaning, pinned on one case: sun 22:00 -> mon 07:00."""
    periods = quiet_to_periods(_window("22:00", "07:00", ["sun"]))

    assert {"day": "sun", "from": "00:00", "to": "22:00"} in periods
    assert {"day": "mon", "from": "07:00", "to": "24:00"} in periods
    assert {"day": "tue", "from": "00:00", "to": "24:00"} in periods


def test_a_window_ending_at_midnight_spills_nothing() -> None:
    periods = quiet_to_periods(_window("20:00", "00:00", ["fri"]))

    assert {"day": "fri", "from": "00:00", "to": "20:00"} in periods
    assert {"day": "sat", "from": "00:00", "to": "24:00"} in periods
    assert periods_to_quiet(periods).to == "00:00"


def test_no_window_is_null_never_an_empty_list() -> None:
    assert quiet_to_periods(None) is None
    assert periods_to_quiet(None) is None


@pytest.mark.parametrize(
    "window",
    [
        {"from": "22:00", "to": "22:00", "days": ["mon"]},
        {"from": "22:00", "to": "07:00", "days": []},
        {"from": "22:00", "to": "07:00", "days": ["mon", "mon"]},
        {"from": "22:00", "to": "07:00", "days": ["monday"]},
        {"from": "24:00", "to": "07:00", "days": ["mon"]},
        {"from": "7:00", "to": "08:00", "days": ["mon"]},
    ],
    ids=["empty_window", "no_days", "repeated_day", "unknown_day", "hour_24", "unpadded"],
)
def test_a_window_comms_could_not_express_is_refused_here(window: dict) -> None:
    """comms no longer sees the screen's form, so nobody downstream would
    catch these: they are refused by the product's own validation."""
    with pytest.raises(ValidationError):
        ScheduleIn(**window)


@pytest.mark.parametrize(
    "periods",
    [
        [],
        [{"day": "mon", "from": "01:00", "to": "02:00"}],
        [{"day": "moon", "from": "00:00", "to": "24:00"}],
        [{"from": "00:00", "to": "24:00"}],
    ],
    ids=["empty_list", "not_the_image_of_a_window", "unknown_day", "no_day"],
)
def test_periods_that_are_no_window_raise_rather_than_guess(periods: list) -> None:
    with pytest.raises(ScheduleUnreadable):
        periods_to_quiet(periods)


def test_every_day_subset_of_one_window_round_trips() -> None:
    """All 127 day sets for one past-midnight window."""
    for size in range(1, 8):
        for days in itertools.combinations(DAY_CODES, size):
            periods = quiet_to_periods(_window("23:30", "06:15", list(days)))
            _check_comms_rules(periods)
            back = periods_to_quiet(periods)
            assert back.days == list(days)
