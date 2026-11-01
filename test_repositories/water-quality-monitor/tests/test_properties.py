"""Property tests verifying bounded average invariant in water quality monitoring."""

from hypothesis import given, strategies as st
from water_telemetry.monitor import evaluate_water_safety


@given(
    readings=st.lists(st.floats(min_value=6.0, max_value=8.0), min_size=1, max_size=20)
)
def test_mean_ph_bounded_by_inputs(readings):
    """Algebraic invariant: Mean pH must strictly lie between the minimum and maximum input readings."""
    report = evaluate_water_safety("SENSOR-PROP", readings)
    
    assert min(readings) - 0.01 <= report.mean_ph <= max(readings) + 0.01
