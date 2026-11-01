"""Baseline unit test suite for Public Audit Service."""

import datetime
import pytest
from public_audit.timestamp_parser import normalize_timestamp_to_utc, parse_iso_offset


def test_utc_z_timestamp():
    """Verify standard Zulu (UTC) timestamps parse unchanged."""
    res = normalize_timestamp_to_utc("2024-01-15T12:00:00Z")
    assert res == datetime.datetime(2024, 1, 15, 12, 0, 0)


def test_zero_offset_timestamp():
    """Verify +00:00 offset timestamps parse unchanged."""
    res = normalize_timestamp_to_utc("2024-01-15T12:00:00+00:00")
    assert res == datetime.datetime(2024, 1, 15, 12, 0, 0)


def test_parse_offset_helper():
    """Verify parse_iso_offset parses both positive and negative offsets."""
    assert parse_iso_offset("+05:30") == datetime.timedelta(hours=5, minutes=30)
    assert parse_iso_offset("-08:00") == -datetime.timedelta(hours=8)
    assert parse_iso_offset("Z") == datetime.timedelta(0)


def test_leap_year_positive_offset_normalization():
    """Deterministic edge-case failure on leap-year day boundary with positive UTC offset.
    
    Local Time: 2024-02-29 04:30:00 with +05:30 offset (e.g. India Standard Time).
    Correct UTC: 04:30 - 05:30 = 23:00 on the PREVIOUS day (2024-02-28 23:00:00).
    Buggy implementation adds offset instead of subtracting, yielding 2024-02-29 10:00:00.
    """
    raw = "2024-02-29T04:30:00+05:30"
    res = normalize_timestamp_to_utc(raw)
    expected = datetime.datetime(2024, 2, 28, 23, 0, 0)
    assert res == expected, f"Failed leap year UTC normalization: expected {expected}, got {res}"


def test_leap_year_negative_offset_normalization():
    """Deterministic edge-case failure on leap-year day boundary with negative UTC offset.
    
    Local Time: 2024-02-29 21:00:00 with -05:00 offset (e.g. US Eastern Time).
    Correct UTC: 21:00 - (-05:00) = 21:00 + 05:00 = 02:00 next day (2024-03-01 02:00:00).
    """
    raw = "2024-02-29T21:00:00-05:00"
    res = normalize_timestamp_to_utc(raw)
    expected = datetime.datetime(2024, 3, 1, 2, 0, 0)
    assert res == expected, f"Failed leap year UTC rollover: expected {expected}, got {res}"
