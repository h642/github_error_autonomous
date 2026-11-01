import pytest
from water_telemetry.monitor import evaluate_water_safety


def test_empty_readings():
    report = evaluate_water_safety("RES-0", [])
    assert report.status == "NO_DATA"
    assert report.sample_count == 0


def test_invalid_sensor_noise():
    report = evaluate_water_safety("RES-FAULT", [-5.0, 99.0])
    assert report.status == "SENSOR_FAULT"
    assert not report.is_potable


def test_single_reading_no_zerodivision():
    # A single valid sensor reading must evaluate cleanly without ZeroDivisionError
    # (Bug causes ZeroDivisionError: division by zero)
    report = evaluate_water_safety("RES-1", [7.2])
    assert report.sample_count == 1
    assert report.mean_ph == 7.2
    assert report.is_potable


def test_potable_multi_readings():
    # Average of [7.0, 7.2, 7.4] = 21.6 / 3 = 7.2
    # Bug divides by (3 - 1) = 2 -> 10.8 (erroneously triggers contamination alert!)
    report = evaluate_water_safety("RES-MAIN", [7.0, 7.2, 7.4])
    assert report.sample_count == 3
    assert report.mean_ph == 7.2
    assert report.is_potable
    assert report.status == "SAFE"


def test_acidic_contamination():
    # Average of [4.5, 5.0, 4.0] = 13.5 / 3 = 4.5 -> Unsafe
    report = evaluate_water_safety("RES-ACID", [4.5, 5.0, 4.0])
    assert report.sample_count == 3
    assert report.mean_ph == 4.5
    assert not report.is_potable
    assert report.status == "CONTAMINATION_ALERT"
