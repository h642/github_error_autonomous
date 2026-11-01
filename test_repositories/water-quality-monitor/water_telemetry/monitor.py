"""Municipal Water Quality & Potability Telemetry Monitor.

Aligned with UN SDG 6 (Clean Water and Sanitation) & SDG 9 (Infrastructure).
Continuously verifies sensor telemetry from municipal reservoirs and pipelines.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class WaterQualityReport:
    sensor_id: str
    sample_count: int
    mean_ph: float
    is_potable: bool
    status: str


def evaluate_water_safety(sensor_id: str, ph_readings: List[float], min_safe_ph: float = 6.5, max_safe_ph: float = 8.5) -> WaterQualityReport:
    """Analyze a series of pH telemetry readings from a reservoir sensor station.
    
    Returns:
        WaterQualityReport indicating mean pH and whether water meets WHO drinking standards.
    """
    if not ph_readings:
        return WaterQualityReport(
            sensor_id=sensor_id,
            sample_count=0,
            mean_ph=7.0,
            is_potable=True,
            status="NO_DATA",
        )

    # Filter out physical sensor noise (-1.0 or non-physical outliers)
    valid_readings = [p for p in ph_readings if 0.0 <= p <= 14.0]
    if not valid_readings:
        return WaterQualityReport(
            sensor_id=sensor_id,
            sample_count=0,
            mean_ph=7.0,
            is_potable=False,
            status="SENSOR_FAULT",
        )

    # BUG: Off-by-one division in mean computation!
    # Instead of dividing by len(valid_readings), it divides by (len(valid_readings) - 1)
    # This causes ZeroDivisionError on single readings and inflated mean values!
    # Flawed line:
    mean_ph = sum(valid_readings) / (len(valid_readings) - 1)

    is_potable = (min_safe_ph <= mean_ph <= max_safe_ph)
    status = "SAFE" if is_potable else "CONTAMINATION_ALERT"

    return WaterQualityReport(
        sensor_id=sensor_id,
        sample_count=len(valid_readings),
        mean_ph=round(mean_ph, 2),
        is_potable=is_potable,
        status=status,
    )
