"""Tests for shared optimization savings rollups."""

from __future__ import annotations

from app.optimization_savings import distinct_action_savings, distinct_scoreboard_savings


def test_distinct_action_savings_uses_max_per_resource():
    rows = [
        ("/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1", 100.0),
        ("/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1", 40.0),
        ("/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2", 50.0),
    ]
    assert distinct_action_savings(rows) == 150.0


def test_distinct_scoreboard_savings_uses_max_per_resource():
    rows = [
        ("/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1", 80.0),
        ("/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1", 30.0),
        ("/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm2", 20.0),
    ]
    assert distinct_scoreboard_savings(rows) == 100.0
