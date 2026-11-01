"""Property tests verifying conservation of inventory in disaster supply allocation."""

from hypothesis import given, strategies as st
from supply_dispatch.allocator import ReliefZone, allocate_relief_supplies


@given(
    inventory=st.integers(min_value=1, max_value=500),
    req1=st.integers(min_value=1, max_value=200),
    req2=st.integers(min_value=1, max_value=200),
)
def test_inventory_conservation_invariant(inventory, req1, req2):
    """Conservation of mass/inventory: Total distributed + remaining must EQUAL initial inventory."""
    zones = [
        ReliefZone(zone_id="Z1", urgency_level=1, requested_units=req1),
        ReliefZone(zone_id="Z2", urgency_level=2, requested_units=req2),
    ]
    allocations, remaining = allocate_relief_supplies(zones, total_inventory=inventory)
    
    total_distributed = sum(allocations.values())
    assert total_distributed + remaining == inventory
    assert remaining >= 0
