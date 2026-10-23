"""Parse standard Retry-After forms into an aware UTC instant."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re


def parse_retry_after(value: str | None, *, now: datetime) -> datetime | None:
    if now.tzinfo is None:
        raise ValueError("Retry-After clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"[0-9]+", value):
            return now + timedelta(seconds=int(value))
        parsed = parsedate_to_datetime(value)
        # The obsolete asctime HTTP-date form has no explicit zone; HTTP dates
        # use UTC. Current date forms already include GMT.
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None
