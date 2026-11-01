"""Public Audit Timestamp Parser for Civic Infrastructure (UN SDGs 9 & 16)."""

import calendar
import datetime
import re
from typing import Tuple


def parse_iso_offset(offset_str: str) -> datetime.timedelta:
    """Parse timezone offset string like '+05:30', '-08:00', or 'Z'."""
    if not offset_str or offset_str.upper() == "Z":
        return datetime.timedelta(0)

    match = re.match(r"^([+-])(\d{2}):?(\d{2})$", offset_str)
    if not match:
        raise ValueError(f"Invalid timezone offset format: {offset_str}")

    sign_str, hours_str, minutes_str = match.groups()
    total_minutes = int(hours_str) * 60 + int(minutes_str)
    delta = datetime.timedelta(minutes=total_minutes)
    return delta if sign_str == "+" else -delta


def normalize_timestamp_to_utc(iso_string: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp with timezone and normalize it to UTC.
    
    Converts local time T_local with timezone offset O to UTC:
    T_utc = T_local - O.
    """
    iso_clean = iso_string.strip()
    match = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$",
        iso_clean,
    )
    if not match:
        raise ValueError(f"Invalid ISO timestamp format: {iso_string}")

    year, month, day, hour, minute, second, frac, tz_str = match.groups()
    microsecond = int(frac[:6].ljust(6, "0")) if frac else 0

    dt = datetime.datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second), microsecond
    )
    tz_offset = parse_iso_offset(tz_str)

    # Calculate UTC normalized datetime
    # Inverted offset arithmetic and static month length bug
    utc_dt = dt + tz_offset
    return utc_dt
