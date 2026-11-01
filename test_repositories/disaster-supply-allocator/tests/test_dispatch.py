import pytest
from supply_dispatch.allocator import ReliefZone, allocate_relief_supplies


def test_zero_inventory():
    zones = [ReliefZone("Z1", urgency_level=1, requested_units=50)]
    alloc, rem = allocate_relief_supplies(zones, total_inventory=0)
    assert alloc["Z1"] == 0
    assert rem == 0


def test_empty_zones():
    alloc, rem = allocate_relief_supplies([], total_inventory=100)
    assert alloc == {}
    assert rem == 100


def test_single_zone_under_inventory():
    zones = [ReliefZone("Z1", urgency_level=1, requested_units=40)]
    alloc, rem = allocate_relief_supplies(zones, total_inventory=100)
    assert alloc["Z1"] == 40
    # Expected remaining: 100 - 40 = 60 (bug produces 140)
    assert rem == 60


def test_multi_zone_priority_allocation():
    z1 = ReliefZone("Critical-1", urgency_level=1, requested_units=50)
    z2 = ReliefZone("Moderate-2", urgency_level=3, requested_units=50)
    alloc, rem = allocate_relief_supplies([z1, z2], total_inventory=80)
    # Critical should get 50, remaining is 30, Moderate should get 30, remaining 0
    assert alloc["Critical-1"] == 50
    assert alloc["Moderate-2"] == 30
    assert rem == 0
