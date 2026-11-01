"""Property-based fuzz testing using Hypothesis (Gate 2: Anti-Overfitting)."""

import datetime
from hypothesis import given, settings, strategies as st
from public_audit.timestamp_parser import normalize_timestamp_to_utc, parse_iso_offset


# Hypothesis strategies for generating diverse ISO timestamps
valid_years = st.integers(min_value=1980, max_value=2050)
valid_months = st.integers(min_value=1, max_value=12)
valid_days = st.integers(min_value=1, max_value=28)  # Safe days present in all months
valid_hours = st.integers(min_value=0, max_value=23)
valid_minutes = st.integers(min_value=0, max_value=59)
valid_seconds = st.integers(min_value=0, max_value=59)

# Valid timezone offsets from -12:00 to +14:00
offset_hours = st.integers(min_value=-12, max_value=14)
offset_minutes = st.sampled_from([0, 15, 30, 45])


@settings(max_examples=100, deadline=None)
@given(
    year=valid_years,
    month=valid_months,
    day=valid_days,
    hour=valid_hours,
    minute=valid_minutes,
    second=valid_seconds,
    tz_h=offset_hours,
    tz_m=offset_minutes,
)
def test_property_invertibility(year, month, day, hour, minute, second, tz_h, tz_m):
    """Property Invariant: T_utc + offset must equal the original local time T_local."""
    sign = "+" if tz_h >= 0 else "-"
    tz_str = f"{sign}{abs(tz_h):02d}:{tz_m:02d}"
    iso_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{tz_str}"

    local_dt = datetime.datetime(year, month, day, hour, minute, second)
    offset = parse_iso_offset(tz_str)

    utc_dt = normalize_timestamp_to_utc(iso_str)

    # Invariant: Re-adding the offset to UTC must reconstruct the local timestamp
    reconstructed_local = utc_dt + offset
    assert reconstructed_local == local_dt, (
        f"Invertibility invariant violated for {iso_str}: "
        f"utc={utc_dt}, offset={offset}, reconstructed={reconstructed_local}, expected={local_dt}"
    )


@settings(max_examples=50, deadline=None)
@given(
    hour=valid_hours,
    minute=valid_minutes,
    second=valid_seconds,
    tz_h=st.integers(min_value=1, max_value=12),  # strictly positive offsets
)
def test_property_positive_offset_is_earlier_in_utc(hour, minute, second, tz_h):
    """Property Invariant: Positive offset (east of Greenwich) must yield earlier UTC timestamp."""
    iso_str = f"2024-02-29T{hour:02d}:{minute:02d}:{second:02d}+{tz_h:02d}:00"
    local_dt = datetime.datetime(2024, 2, 29, hour, minute, second)
    utc_dt = normalize_timestamp_to_utc(iso_str)

    assert utc_dt < local_dt, f"Positive offset must yield earlier UTC time: local={local_dt}, utc={utc_dt}"
