"""Azure Managed Disk specifications — disk-assessment.json is the single source of truth."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from it_services.compute_disk.arm_disk_properties import disk_property_value


def disk_sku_name(
    sku: dict[str, Any] | str | None,
    *,
    props: dict[str, Any] | None = None,
) -> str:
    """Resolve disk SKU name when ARM returns a string or {name: ...} dict."""
    if isinstance(sku, str):
        return sku.strip()
    if isinstance(sku, dict):
        return (sku.get("name") or "").strip()
    if props:
        fallback = props.get("sku")
        if isinstance(fallback, str):
            return fallback.strip()
        if isinstance(fallback, dict):
            return (fallback.get("name") or "").strip()
    return ""


@lru_cache(maxsize=1)
def load_disk_specifications() -> dict[str, Any]:
    from it_services.compute_disk.assessment_bridge import load_disk_assessment

    return load_disk_assessment()


def optimization_thresholds() -> dict[str, float]:
    try:
        from it_services.compute_disk.assessment_bridge import optimization_thresholds as assessment_thresholds

        return assessment_thresholds()
    except (FileNotFoundError, ImportError, RuntimeError):
        pass
    specs = load_disk_specifications()
    raw = specs.get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def disk_type_spec(sku_name: str | None) -> dict[str, Any]:
    specs = load_disk_specifications()
    types = specs.get("disk_types") or {}
    key = (sku_name or "StandardSSD_LRS").strip()
    return dict(types.get(key) or {})


def provisioned_limits_from_performance_tier(
    performance_tier: str | None,
) -> tuple[int | None, int | None]:
    """
    IOPS/MBps from properties.tier (P10, S10, E20, etc.) on Disk GET response.

    See Disk.properties.tier — does not apply to Ultra SSD.
    """
    tier = (performance_tier or "").strip().upper()
    if not tier:
        return None, None
    specs = load_disk_specifications()
    limits = (specs.get("performance_tier_limits") or {}).get(tier)
    if not isinstance(limits, dict):
        return None, None
    iops = limits.get("iops")
    mbps = limits.get("mbps")
    return (
        int(iops) if iops is not None else None,
        int(mbps) if mbps is not None else None,
    )


def provisioned_limits_from_tier(
    sku_name: str | None,
    size_gb: int | float | None,
) -> tuple[int | None, int | None]:
    """
    Size-based provisioned IOPS and throughput for SKUs where ARM does not set
    diskIOPSReadWrite / diskMBpsReadWrite (Standard HDD/SSD, Premium SSD v1).

    Explicit ARM properties take precedence — used for Ultra SSD and Premium SSD v2.
    Limits align with Azure managed disk type documentation (disk size bands).
    """
    specs = load_disk_specifications()
    tier_specs = specs.get("disk_tier_specs") or {}
    sku = (sku_name or "").strip()
    if not sku:
        return None, None

    spec = tier_specs.get(sku)
    if not spec:
        # Premium_ZRS mirrors Premium_LRS performance bands.
        if sku == "Premium_ZRS" and "Premium_LRS" in tier_specs:
            spec = tier_specs["Premium_LRS"]
        elif sku == "StandardSSD_ZRS" and "StandardSSD_LRS" in tier_specs:
            spec = tier_specs["StandardSSD_LRS"]
        else:
            return None, None

    size = int(size_gb or 0)
    size_ranges = spec.get("size_ranges") or []
    if size > 0 and size_ranges:
        for band in size_ranges:
            min_gb = int(band.get("min_gb") or 0)
            max_gb = band.get("max_gb")
            if size < min_gb:
                continue
            if max_gb is None or size <= int(max_gb):
                iops = band.get("iops")
                mbps = band.get("mbps")
                return (
                    int(iops) if iops is not None else None,
                    int(mbps) if mbps is not None else None,
                )

    default_iops = spec.get("default_iops")
    default_mbps = spec.get("default_mbps")
    return (
        int(default_iops) if default_iops is not None else None,
        int(default_mbps) if default_mbps is not None else None,
    )


def resolve_disk_provisioned_performance(disk: dict[str, Any]) -> dict[str, Any]:
    """
    Merge ARM provisioned caps with properties.tier and SKU size-table limits.

    diskIOPSReadWrite / diskMBpsReadWrite are set on Ultra SSD and Premium SSD v2
    per Disks - Get; other SKUs use properties.tier or size bands.
    """
    props = disk.get("properties") or {}
    sku_name = disk_sku_name(disk.get("sku"), props=props)
    size_gb = disk_property_value(disk, "diskSizeGB") or props.get("diskSizeGB") or 0
    performance_tier = disk_property_value(disk, "tier") or props.get("tier")

    arm_iops = disk_property_value(disk, "diskIOPSReadWrite")
    arm_mbps = disk_property_value(disk, "diskMBpsReadWrite")

    perf_iops, perf_mbps = provisioned_limits_from_performance_tier(performance_tier)
    tier_iops, tier_mbps = perf_iops, perf_mbps
    if tier_iops is None and tier_mbps is None:
        tier_iops, tier_mbps = provisioned_limits_from_tier(sku_name, size_gb)

    iops = arm_iops if arm_iops is not None else tier_iops
    mbps = arm_mbps if arm_mbps is not None else tier_mbps

    if arm_iops is not None or arm_mbps is not None:
        source = "arm"
    elif perf_iops is not None or perf_mbps is not None:
        source = "performance_tier"
    elif iops is not None or mbps is not None:
        source = "tier_spec"
    else:
        source = None

    return {
        "diskIOPSReadWrite": iops,
        "diskMBpsReadWrite": mbps,
        "provisionedPerformanceSource": source,
    }


def enrich_disk_provisioned_properties(
    props: dict[str, Any],
    *,
    sku: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Persist resolved provisioned IOPS/MBps on synced disk properties."""
    sku_obj = sku if isinstance(sku, dict) else {"name": sku} if sku else {}
    perf = resolve_disk_provisioned_performance({"properties": props, "sku": sku_obj})
    if perf.get("diskIOPSReadWrite") is not None:
        props["diskIOPSReadWrite"] = perf["diskIOPSReadWrite"]
    if perf.get("diskMBpsReadWrite") is not None:
        props["diskMBpsReadWrite"] = perf["diskMBpsReadWrite"]
    if perf.get("provisionedPerformanceSource"):
        props["provisionedPerformanceSource"] = perf["provisionedPerformanceSource"]
    return props


def parse_disk_arm(disk: dict[str, Any]) -> dict[str, Any]:
    props = disk.get("properties") or {}
    sku = disk.get("sku")
    merged_props = dict(props)
    enrich_disk_provisioned_properties(merged_props, sku=sku)
    return {
        "disk_state": (props.get("diskState") or disk.get("state") or "").strip(),
        "size_gb": int(props.get("diskSizeGB") or 0),
        "sku_name": disk_sku_name(sku, props=props),
        "provisioned_iops": merged_props.get("diskIOPSReadWrite"),
        "provisioned_mbps": merged_props.get("diskMBpsReadWrite"),
    }
