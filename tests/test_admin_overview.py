"""Tests for optimization center overview metrics."""

from app.admin_overview import _is_idle_state
from app.optimizer.component_map import WASTE_STATE_PATTERNS


def test_waste_state_excludes_deallocated():
    assert _is_idle_state("PowerState/deallocated", waste_only=True) is False
    assert _is_idle_state("deallocated", waste_only=True) is False


def test_waste_state_includes_stopped_and_unattached():
    assert _is_idle_state("PowerState/stopped", waste_only=True) is True
    assert _is_idle_state("Unattached", waste_only=True) is True


def test_idle_state_includes_deallocated():
    assert _is_idle_state("PowerState/deallocated", waste_only=False) is True


def test_waste_patterns_exclude_deallocated():
    assert "deallocated" not in WASTE_STATE_PATTERNS
