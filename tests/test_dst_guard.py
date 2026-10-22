from datetime import datetime, timezone

import pytest

from dst_guard import should_run

CRONS = ["0 1 * * *", "0 2 * * *"]


def runs_on(day: str, delay_min: int = 0):
    """Which of the two daily crons would build on `day` (UTC date), given a start delay."""
    out = []
    for cron in CRONS:
        hour = int(cron.split()[1])
        now = datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")
        now = now.replace(minute=delay_min) if delay_min < 60 else now.replace(hour=hour + 1, minute=delay_min - 60)
        if should_run("schedule", now, cron):
            out.append(cron)
    return out


@pytest.mark.parametrize("day,expected", [
    ("2027-01-15", "0 2 * * *"),   # mid-January, CET (UTC+1): 02:00 UTC = 03:00
    ("2026-07-15", "0 1 * * *"),   # mid-July, CEST (UTC+2): 01:00 UTC = 03:00
    ("2027-03-28", "0 1 * * *"),   # last Sunday of March: clocks jump at 01:00 UTC, 01:00 UTC = 03:00 CEST
    ("2026-10-25", "0 2 * * *"),   # last Sunday of October: back to CET at 01:00 UTC, 02:00 UTC = 03:00 CET
    ("2026-10-22", "0 1 * * *"),   # today (CEST)
    ("2026-10-26", "0 2 * * *"),   # first day after the switch (CET)
])
def test_exactly_one_run_per_night(day, expected):
    assert runs_on(day) == [expected]


@pytest.mark.parametrize("day", ["2027-01-15", "2026-07-15", "2027-03-28", "2026-10-25"])
@pytest.mark.parametrize("delay", [7, 35, 59, 75])
def test_late_start_still_exactly_one_run(day, delay):
    # GitHub often starts scheduled jobs late; the guard judges the scheduled slot, not the wall clock.
    assert len(runs_on(day, delay)) == 1


def test_manual_run_always_builds():
    assert should_run("workflow_dispatch", datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc))


def test_wall_clock_fallback_without_cron():
    assert should_run("schedule", datetime(2026, 7, 15, 1, 5, tzinfo=timezone.utc))
    assert not should_run("schedule", datetime(2026, 7, 15, 2, 5, tzinfo=timezone.utc))
