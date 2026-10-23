"""Decide whether this workflow run should build.

Three editions a day, at 01:13, 11:43 and 17:43 Europe/Zurich. GitHub cron is
UTC-only, so each edition has two crons (one for CEST, one for CET) and this
guard lets through only the one whose *scheduled* time falls in a target hour.
Off-peak minutes (:13, :43) because GitHub delays top-of-the-hour jobs most.
01:13 rather than 02:xx because 02:xx is skipped or doubled on DST-switch nights.

The scheduled time is taken from the cron expression that triggered the run
(github.event.schedule), not from the wall clock, so a run that GitHub starts
late (delays of 10-60 min are common) is still judged by its intended slot and
can neither be skipped nor doubled. Manual runs (workflow_dispatch) always build.

Writes `run=true|false` to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Zurich")
TARGET_HOURS = (1, 11, 17)


def scheduled_utc(now_utc: datetime, cron: str) -> datetime:
    """Most recent UTC datetime <= now matching a daily 'M H * * *' cron."""
    minute, hour = (int(x) for x in cron.split()[:2])
    t = now_utc.astimezone(timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t > now_utc:
        t -= timedelta(days=1)
    return t


def should_run(event: str, now_utc: datetime, cron: str | None = None, tz: ZoneInfo = TZ,
               hours: tuple[int, ...] = TARGET_HOURS) -> bool:
    if event in ("workflow_dispatch", "push"):
        return True
    t = scheduled_utc(now_utc, cron) if cron else now_utc
    return t.astimezone(tz).hour in hours


def main() -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
    cron = None
    path = os.environ.get("GITHUB_EVENT_PATH")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            cron = (json.load(fh) or {}).get("schedule")
    now = datetime.now(timezone.utc)
    run = should_run(event, now, cron)
    print(f"event={event} cron={cron!r} now={now:%Y-%m-%d %H:%M}Z "
          f"zurich={now.astimezone(TZ):%H:%M %Z} -> run={str(run).lower()}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"run={str(run).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
