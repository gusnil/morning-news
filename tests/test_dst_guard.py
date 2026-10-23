from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from dst_guard import TZ, should_run

WF = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/build.yml").read_text())
CRONS = [c["cron"] for c in WF[True]["schedule"]]   # yaml reads the "on:" key as True


def firings(day: str, delay_min: int = 0):
    """Local (date, hour) of every build the guard lets through, for crons firing around `day`."""
    d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) - timedelta(days=1)
    out = []
    for k in range(3):
        for cron in CRONS:
            m, h = (int(x) for x in cron.split()[:2])
            sched = (d0 + timedelta(days=k)).replace(hour=h, minute=m)
            now = sched + timedelta(minutes=delay_min)
            if should_run("schedule", now, cron):
                loc = sched.astimezone(TZ)
                out.append((loc.date().isoformat(), loc.hour))
    return out


@pytest.mark.parametrize("day", ["2027-01-15", "2026-07-15", "2027-03-28", "2026-10-25", "2026-10-26", "2026-10-23"])
@pytest.mark.parametrize("delay", [0, 7, 59, 75, 270])
def test_exactly_three_editions_per_local_day(day, delay):
    # includes DST-switch days and a 4.5 h GitHub start delay (observed 23.10.2026)
    got = [h for d, h in firings(day, delay) if d == day]
    assert sorted(got) == [1, 11, 17]


def test_manual_and_push_always_build():
    assert should_run("workflow_dispatch", datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc))
    assert should_run("push", datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc))


def test_wall_clock_fallback_without_cron():
    assert should_run("schedule", datetime(2026, 7, 15, 9, 50, tzinfo=timezone.utc))      # 11:50 CEST
    assert not should_run("schedule", datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc))  # 14:05 CEST


def test_edition_names():
    from render import edition
    assert [edition(h) for h in (1, 5, 11, 15, 17, 22)] == ["Morning", "Morning", "Midday", "Midday", "Evening", "Evening"]
