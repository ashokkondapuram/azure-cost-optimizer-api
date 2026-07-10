"""Azure VMSS autoscale parameters — loaded from data/vmss_autoscale_parameters.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_PATH = Path(__file__).resolve().parents[1] / "data" / "vmss_autoscale_parameters.json"


@lru_cache(maxsize=1)
def load_vmss_specifications() -> dict[str, Any]:
    if not _SPEC_PATH.is_file():
        return {}
    with _SPEC_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def optimization_thresholds() -> dict[str, float]:
    specs = load_vmss_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def autoscale_defaults() -> dict[str, float]:
    specs = load_vmss_specifications()
    raw = specs.get("autoscale_defaults") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def parse_vmss_arm(vmss: dict[str, Any]) -> dict[str, Any]:
    props = vmss.get("properties") or {}
    sku_obj = vmss.get("sku") or {}
    return {
        "capacity": int(sku_obj.get("capacity") or 0),
        "vm_size": ((props.get("virtualMachineProfile") or {}).get("hardwareProfile") or {}).get("vmSize") or "",
        "has_autoscale": bool(props.get("autoscaleSettings") or props.get("profiles")),
    }
