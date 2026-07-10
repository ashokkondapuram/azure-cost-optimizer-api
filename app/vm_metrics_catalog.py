"""Azure VM metrics thresholds — loaded from data/vm_metrics_thresholds.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "vm_metrics_thresholds.json"


@lru_cache(maxsize=1)
def load_vm_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_vm_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


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
