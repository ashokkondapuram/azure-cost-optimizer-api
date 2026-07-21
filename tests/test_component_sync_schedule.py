"""Tests for per-component sync scheduling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.component_sync_schedule import (
    interval_minutes_for_component,
    pick_next_due_component,
    syncable_components,
)


def test_syncable_components_excludes_commitments_and_budgets():
    names = syncable_components()
    assert "Commitments" not in names
    assert "Budgets" not in names
    assert "Virtual Machines" in names


def test_fast_components_use_shorter_default_interval(monkeypatch):
    monkeypatch.delenv("SCHEDULED_SYNC_INTERVAL_FAST_MINUTES", raising=False)
    assert interval_minutes_for_component("Virtual Machines") == 15
    assert interval_minutes_for_component("Load Balancers") == 60


def test_pick_next_due_prefers_never_synced():
    component, overdue = pick_next_due_component({})
    assert component == syncable_components()[0]
    assert overdue > 0


def test_pick_next_due_respects_interval():
    now = datetime.now(timezone.utc)
    component = "Virtual Machines"
    last = {name: now for name in syncable_components()}
    last[component] = now - timedelta(minutes=5)
    due, overdue = pick_next_due_component(last, now=now)
    assert due is None
    assert overdue < 0

    later = now + timedelta(minutes=20)
    due, overdue = pick_next_due_component(last, now=later)
    assert due == component
    assert overdue >= 0
