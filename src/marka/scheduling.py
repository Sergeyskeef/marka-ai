"""Explicit wall-clock context and bounded, offset-aware schedule requests."""
from datetime import datetime, timedelta, timezone
import math
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def owner_timezone(name: str):
    if not isinstance(name, str) or not name or len(name) > 100:
        raise ValueError("Timezone must be UTC, UTC+03:00 or an installed IANA zone")
    if name == "UTC":
        return timezone.utc
    fixed = re.fullmatch(r"UTC([+-])(\d{2}):(\d{2})", name)
    if fixed:
        hours, minutes = int(fixed[2]), int(fixed[3])
        if minutes > 59 or hours > 14 or (hours == 14 and minutes):
            raise ValueError("Timezone offset must be within UTC-14:00 and UTC+14:00")
        return timezone(timedelta(minutes=(hours * 60 + minutes) * (1 if fixed[1] == "+" else -1)))
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unknown timezone; use UTC+03:00 or an installed IANA zone") from None


def clock_context(zone="UTC", *, now=None):
    instant = time.time() if now is None else now
    utc = datetime.fromtimestamp(instant, timezone.utc)
    local = utc.astimezone(owner_timezone(zone))
    return {"utc": utc.isoformat(timespec="seconds"), "local": local.isoformat(timespec="seconds"),
            "timezone": zone, "weekday_iso": local.isoweekday(), "unix_seconds": instant}


def schedule_due(args, *, now):
    """Reject ambiguous input before enqueueing; never silently move a past date."""
    if ("due_at" in args) == ("delay_seconds" in args):
        raise ValueError("Provide exactly one of delay_seconds or due_at with an explicit UTC offset")
    if "due_at" in args:
        value = args["due_at"]
        if not isinstance(value, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value):
            raise ValueError("due_at must be RFC3339 with seconds and an explicit UTC offset")
        # -00:00 means unknown local offset in RFC3339, not an owner timezone.
        if value.endswith("-00:00"):
            raise ValueError("due_at requires a known UTC offset")
        if not value.endswith("Z"):
            owner_timezone("UTC" + value[-6:])
        try:
            due = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (ValueError, OverflowError, OSError):
            raise ValueError("Invalid due_at date") from None
    else:
        delay = args["delay_seconds"]
        if type(delay) is not int or not 1 <= delay <= 366 * 86400:
            raise ValueError("delay_seconds must be an integer from 1 second to 366 days")
        due = now + delay
    if not math.isfinite(due) or not 1 <= due - now <= 366 * 86400:
        raise ValueError("Scheduled start must be 1 second–366 days in the future")
    return due
