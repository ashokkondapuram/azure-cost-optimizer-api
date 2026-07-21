"""Workload schedule classification for VM shutdown and zombie detection."""
from __future__ import annotations

from typing import Any

from app.resource_utilization import fact_value, technical_facts
from app.vm_uptime import vm_is_running

_NONPROD_ENVS = frozenset({
    "dev", "development", "test", "qa", "staging", "sandbox", "nonprod", "non-prod", "uat",
})
_IDLE_COST_USD_PER_DAY = 0.50
_ZOMBIE_CPU_PCT = 5.0


def _environment_tag(vm: dict[str, Any]) -> str:
    tags = vm.get("tags") or {}
    return str(tags.get("environment") or tags.get("env") or "").strip().lower()


def _normalize_power(power_state: str) -> str:
    return (power_state or "").replace("PowerState/", "").strip().lower()


def _idle_days_from_cost(daily_cost: list[float], *, window: int = 7) -> int:
    if not daily_cost:
        return 0
    recent = daily_cost[-window:]
    return sum(1 for amount in recent if float(amount or 0.0) < _IDLE_COST_USD_PER_DAY)


def classify_workload_schedule(
    vm: dict[str, Any],
    facts: dict[str, Any] | None = None,
    *,
    daily_cost: list[float] | None = None,
    power_state: str = "",
) -> str:
    """
    Classify VM workload scheduling pattern.

    Returns one of:
    - schedule_candidate — often stopped/deallocated; automate shutdown or delete
    - zombie_candidate — always on but near-zero CPU; delete or decommission
    - always_on — running workload with meaningful utilization
    - unknown — insufficient signals
    """
    merged_facts = dict(technical_facts(vm))
    if facts:
        merged_facts.update(facts)

    env = _environment_tag(vm)
    nonprod = env in _NONPROD_ENVS
    power = _normalize_power(power_state)
    stopped_now = power in {"stopped", "deallocated"}
    idle_days = _idle_days_from_cost(daily_cost or [])

    if stopped_now and (nonprod or idle_days >= 3):
        return "schedule_candidate"
    if idle_days >= 5:
        return "schedule_candidate"

    avg_cpu = fact_value({**vm, "_technical_facts": merged_facts}, "avg_cpu_pct")
    running = vm_is_running(vm, power_state=power)
    if running and avg_cpu is not None and avg_cpu < _ZOMBIE_CPU_PCT:
        if daily_cost and len(daily_cost) >= 7 and idle_days == 0:
            return "zombie_candidate"
        if nonprod or (avg_cpu < 2.0):
            return "zombie_candidate"

    if running:
        return "always_on"
    if stopped_now:
        return "schedule_candidate"
    return "unknown"
