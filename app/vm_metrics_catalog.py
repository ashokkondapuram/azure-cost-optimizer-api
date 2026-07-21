"""Azure VM specifications — vm-assessment.json is the single source of truth."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.assessment.config_resolver import load_resource_config


@lru_cache(maxsize=1)
def load_vm_specifications() -> dict[str, Any]:
    return load_resource_config("compute/vm")


def optimization_thresholds() -> dict[str, float]:
    from app.assessment.config_resolver import load_optimization_thresholds

    return load_optimization_thresholds("compute/vm")


def pricing_config() -> dict[str, Any]:
    return dict(load_vm_specifications().get("pricing") or {})


def parse_vm_arm(vm: dict[str, Any]) -> dict[str, Any]:
    props = vm.get("properties") or {}
    sku = ((props.get("hardwareProfile") or {}).get("vmSize") or "")
    return {
        "vm_size": sku,
        "location": vm.get("location") or "",
        "power_state": props.get("powerState") or "",
    }
