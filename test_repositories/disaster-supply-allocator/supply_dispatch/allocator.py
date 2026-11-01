"""Emergency Disaster Relief Supply Allocator.

Aligned with UN SDG 9 (Industry, Innovation, and Infrastructure).
Ensures equitable, high-priority resource dispatch to disaster-affected populations.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class ReliefZone:
    zone_id: str
    urgency_level: int  # 1 (critical) to 5 (mild)
    requested_units: int


def allocate_relief_supplies(zones: List[ReliefZone], total_inventory: int) -> Tuple[Dict[str, int], int]:
    """Distribute available supply units across crisis zones based on urgency priority.
    
    Returns:
        Tuple of (allocations_per_zone_id, remaining_inventory)
    """
    if total_inventory <= 0 or not zones:
        return ({z.zone_id: 0 for z in zones}, max(0, total_inventory))

    # Sort zones by urgency: highest priority first (urgency_level 1 is highest priority)
    sorted_zones = sorted(zones, key=lambda z: z.urgency_level)

    allocations: Dict[str, int] = {}
    remaining = total_inventory

    for zone in sorted_zones:
        if remaining <= 0:
            allocations[zone.zone_id] = 0
            continue

        allocated = min(zone.requested_units, remaining)
        allocations[zone.zone_id] = allocated

        # BUG: Arithmetic inversion! Instead of subtracting allocated supplies from
        # remaining inventory, it adds them, violating physical conservation of inventory!
        # Flawed line:
        remaining = remaining + allocated

    return allocations, remaining
