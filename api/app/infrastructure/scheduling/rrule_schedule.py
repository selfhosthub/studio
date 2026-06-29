# api/app/infrastructure/scheduling/rrule_schedule.py

"""Compute next-run times for schedule-trigger workflows from iCalendar RRULEs.

The schedule is stored as a DTSTART anchor + optional RRULE (RFC 5545) evaluated
in a named IANA timezone. Evaluating in the workflow's own timezone keeps DST
transitions correct; the returned next-run is always normalized to UTC for storage
and comparison against `datetime.now(UTC)`.
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr


class ScheduleError(ValueError):
    """Raised when a schedule's dtstart/rrule/timezone cannot be parsed."""


def _resolve_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ScheduleError(f"Unknown timezone: {tz_name}") from e


def compute_next_run(
    dtstart: Optional[datetime],
    rrule: Optional[str],
    tz_name: str,
    after: datetime,
) -> Optional[datetime]:
    """Return the next fire time strictly after `after`, in UTC, or None if the
    schedule has no further occurrences.

    Args:
        dtstart: anchor / first run. tz-naive values are interpreted in `tz_name`.
        rrule: an RRULE string (e.g. "FREQ=DAILY;INTERVAL=1"). None => one-off at dtstart.
        tz_name: IANA timezone the rule is evaluated in.
        after: lower bound (exclusive); tz-naive values are treated as UTC.

    Raises:
        ScheduleError: if dtstart is missing, the timezone is unknown, or the
            RRULE cannot be parsed.
    """
    if dtstart is None:
        raise ScheduleError("Schedule requires a dtstart.")

    tz = _resolve_tz(tz_name)
    local_dtstart = dtstart if dtstart.tzinfo else dtstart.replace(tzinfo=tz)
    after_utc = after if after.tzinfo else after.replace(tzinfo=timezone.utc)

    # One-off: fire once at dtstart, never again.
    if not rrule:
        return (
            local_dtstart.astimezone(timezone.utc)
            if local_dtstart > after_utc
            else None
        )

    try:
        rule = rrulestr(rrule, dtstart=local_dtstart)
    except (ValueError, TypeError) as e:
        raise ScheduleError(f"Invalid RRULE: {e}") from e

    # .after() needs a datetime in the same awareness as dtstart (tz-aware here).
    nxt = rule.after(after_utc.astimezone(tz), inc=False)
    return nxt.astimezone(timezone.utc) if nxt else None


def validate_schedule(
    dtstart: Optional[datetime], rrule: Optional[str], tz_name: str
) -> None:
    """Raise ScheduleError if the schedule config is unusable. Cheap pre-save check."""
    # Recomputing from epoch proves dtstart/rrule/tz all parse together.
    compute_next_run(dtstart, rrule, tz_name, datetime(1970, 1, 1, tzinfo=timezone.utc))
