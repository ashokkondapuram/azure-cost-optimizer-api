"""VM SKU parsing, Azure Monitor utilization, and rightsizing recommendations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

SKU_NAME_RE = re.compile(
    r"^(?P<tier>Standard|Basic)_(?P<family>[A-Za-z]+)(?P<vcpus>\d+)(?P<variant>[a-z]*)(?:_v(?P<version>\d+))?$",
    re.IGNORECASE,
)

# Memory GB per vCPU by family (used when catalog / ARM SKU list is unavailable).
FAMILY_PROFILES: dict[str, dict[str, Any]] = {
    "B": {"label": "Burstable", "memory_gb_per_vcpu": 4.0, "workload": "dev_test_burst"},
    "D": {"label": "General purpose", "memory_gb_per_vcpu": 4.0, "workload": "balanced"},
    "DC": {"label": "Confidential compute", "memory_gb_per_vcpu": 4.0, "workload": "balanced"},
    "E": {"label": "Memory optimized", "memory_gb_per_vcpu": 8.0, "workload": "memory"},
    "F": {"label": "Compute optimized", "memory_gb_per_vcpu": 2.0, "workload": "compute"},
    "G": {"label": "GPU optimized", "memory_gb_per_vcpu": 4.0, "workload": "gpu"},
    "H": {"label": "High performance compute", "memory_gb_per_vcpu": 2.0, "workload": "compute"},
    "L": {"label": "Storage optimized", "memory_gb_per_vcpu": 8.0, "workload": "storage"},
    "M": {"label": "Memory optimized (large)", "memory_gb_per_vcpu": 16.0, "workload": "memory"},
    "N": {"label": "Network optimized", "memory_gb_per_vcpu": 4.0, "workload": "network"},
}

SizingAction = Literal["downgrade", "upgrade", "cross_family", "no_change", "insufficient_data"]


@dataclass(frozen=True)
class ParsedVmSku:
    name: str
    tier: str
    family: str
    family_label: str
    vcpus: int
    variant: str
    version: int | None
    memory_gb: float

    @property
    def profile(self) -> str:
        return str(FAMILY_PROFILES.get(self.family, {}).get("workload", "balanced"))


@dataclass
class VmUtilization:
    avg_cpu_pct: float | None = None
    avg_memory_pct: float | None = None
    avg_available_memory_bytes: float | None = None
    memory_gb_total: float | None = None
    metrics_window: str | None = None
    has_cpu: bool = False
    has_memory: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "avg_cpu_pct": round(self.avg_cpu_pct, 2) if self.avg_cpu_pct is not None else None,
            "avg_memory_pct": round(self.avg_memory_pct, 2) if self.avg_memory_pct is not None else None,
            "avg_available_memory_bytes": self.avg_available_memory_bytes,
            "memory_gb_total": self.memory_gb_total,
            "metrics_window": self.metrics_window,
            "has_cpu": self.has_cpu,
            "has_memory": self.has_memory,
        }


@dataclass
class VmSizingRecommendation:
    action: SizingAction
    current_sku: str
    suggested_sku: str | None
    current_family: str
    suggested_family: str | None
    family_label: str
    direction: Literal["down", "up", "lateral", "none"]
    avg_cpu_pct: float | None
    avg_memory_pct: float | None
    confidence: int
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "current_sku": self.current_sku,
            "suggested_sku": self.suggested_sku,
            "current_family": self.current_family,
            "suggested_family": self.suggested_family,
            "family_label": self.family_label,
            "direction": self.direction,
            "avg_cpu_pct": self.avg_cpu_pct,
            "avg_memory_pct": self.avg_memory_pct,
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


def parse_vm_sku(sku: str | None, *, catalog_entry: dict[str, Any] | None = None) -> ParsedVmSku | None:
    """Parse an Azure VM SKU name into family, vCPU count, and estimated memory."""
    if not sku or not str(sku).strip():
        return None
    name = str(sku).strip()
    match = SKU_NAME_RE.match(name)
    if not match:
        return None

    family = match.group("family").upper()
    vcpus = int(match.group("vcpus"))
    version_raw = match.group("version")
    profile = FAMILY_PROFILES.get(family, {"label": family, "memory_gb_per_vcpu": 4.0})

    memory_gb: float
    if catalog_entry:
        mem_mb = catalog_entry.get("memoryInMB") or catalog_entry.get("memory_in_mb")
        if mem_mb:
            memory_gb = float(mem_mb) / 1024.0
        else:
            memory_gb = _memory_from_capabilities(catalog_entry) or vcpus * float(profile["memory_gb_per_vcpu"])
    else:
        memory_gb = vcpus * float(profile["memory_gb_per_vcpu"])

    return ParsedVmSku(
        name=name,
        tier=match.group("tier").title(),
        family=family,
        family_label=str(profile.get("label", family)),
        vcpus=vcpus,
        variant=(match.group("variant") or "").lower(),
        version=int(version_raw) if version_raw else None,
        memory_gb=round(memory_gb, 2),
    )


def _memory_from_capabilities(catalog_entry: dict[str, Any]) -> float | None:
    for cap in catalog_entry.get("capabilities") or []:
        if (cap.get("name") or "").lower() == "memoryingb":
            try:
                return float(cap.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def _avg_metric(metrics: dict[str, Any] | None, metric_name: str) -> float | None:
    if not metrics:
        return None
    for item in metrics.get("value", []):
        if (item.get("name") or {}).get("value") != metric_name:
            continue
        vals: list[float] = []
        for ts in item.get("timeseries", []):
            for point in ts.get("data", []):
                avg = point.get("average")
                if avg is not None:
                    vals.append(float(avg))
        if vals:
            return sum(vals) / len(vals)
    return None


def extract_vm_utilization(
    metrics: dict[str, Any] | None,
    *,
    sku: str | None = None,
    catalog_entry: dict[str, Any] | None = None,
    timespan: str | None = None,
) -> VmUtilization:
    """Derive CPU % and memory utilization % from Azure Monitor VM metrics."""
    parsed = parse_vm_sku(sku, catalog_entry=catalog_entry)
    cpu = _avg_metric(metrics, "Percentage CPU")
    avail_bytes = _avg_metric(metrics, "Available Memory Bytes")

    mem_pct: float | None = None
    mem_gb_total = parsed.memory_gb if parsed else None
    if avail_bytes is not None and mem_gb_total and mem_gb_total > 0:
        total_bytes = mem_gb_total * (1024**3)
        used_ratio = max(0.0, min(1.0, 1.0 - (avail_bytes / total_bytes)))
        mem_pct = used_ratio * 100.0

    return VmUtilization(
        avg_cpu_pct=cpu,
        avg_memory_pct=mem_pct,
        avg_available_memory_bytes=avail_bytes,
        memory_gb_total=mem_gb_total,
        metrics_window=timespan,
        has_cpu=cpu is not None,
        has_memory=mem_pct is not None,
    )


def _format_sku(parsed: ParsedVmSku, vcpus: int, *, family: str | None = None) -> str:
    fam = family or parsed.family
    base = f"{parsed.tier}_{fam}{vcpus}{parsed.variant}"
    if parsed.version is not None:
        base += f"_v{parsed.version}"
    return base


def _catalog_index(catalog: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in catalog or []:
        key = (row.get("name") or "").strip()
        if key:
            out[key] = row
    return out


def sku_in_catalog(sku: str | None, catalog: list[dict[str, Any]] | None) -> bool:
    if not sku or not catalog:
        return False
    return sku in _catalog_index(catalog)


def _find_catalog_sku(
    catalog: list[dict[str, Any]] | None,
    *,
    family: str,
    vcpus: int,
    variant: str = "",
    version: int | None = None,
    tier: str = "Standard",
) -> str | None:
    """Pick a valid regional SKU matching family and vCPU count."""
    if not catalog:
        return None
    exact: list[ParsedVmSku] = []
    relaxed: list[ParsedVmSku] = []
    for name, row in _catalog_index(catalog).items():
        candidate = parse_vm_sku(name, catalog_entry=row)
        if not candidate:
            continue
        if candidate.family.upper() != family.upper() or candidate.vcpus != vcpus:
            continue
        if (
            candidate.variant == (variant or "").lower()
            and candidate.version == version
            and candidate.tier.lower() == tier.lower()
        ):
            exact.append(candidate)
        else:
            relaxed.append(candidate)
    pool = exact or relaxed
    if not pool:
        return None
    pool.sort(key=lambda s: (s.variant, s.version or 0))
    return pool[0].name


def _resolve_suggested_sku(
    suggested: str | None,
    catalog: list[dict[str, Any]] | None,
) -> str | None:
    if not suggested:
        return None
    if not catalog:
        return suggested
    return suggested if sku_in_catalog(suggested, catalog) else None


def _family_peers(parsed: ParsedVmSku, catalog_index: dict[str, dict[str, Any]]) -> list[ParsedVmSku]:
    peers: list[ParsedVmSku] = []
    for name, row in catalog_index.items():
        candidate = parse_vm_sku(name, catalog_entry=row)
        if not candidate:
            continue
        if (
            candidate.family == parsed.family
            and candidate.variant == parsed.variant
            and candidate.version == parsed.version
            and candidate.tier == parsed.tier
        ):
            peers.append(candidate)
    peers.sort(key=lambda s: s.vcpus)
    return peers


def _step_sku_within_family(
    parsed: ParsedVmSku,
    direction: Literal["down", "up"],
    catalog: list[dict[str, Any]] | None,
) -> str | None:
    catalog_index = _catalog_index(catalog)
    peers = _family_peers(parsed, catalog_index)
    if peers:
        vcpu_list = [p.vcpus for p in peers]
        if parsed.vcpus in vcpu_list:
            idx = vcpu_list.index(parsed.vcpus)
            if direction == "down" and idx > 0:
                return peers[idx - 1].name
            if direction == "up" and idx < len(peers) - 1:
                return peers[idx + 1].name
        return None

    if direction == "down":
        new_vcpu = parsed.vcpus // 2
        if new_vcpu < 1 or new_vcpu >= parsed.vcpus:
            return None
        return _format_sku(parsed, new_vcpu)
    new_vcpu = parsed.vcpus * 2
    if new_vcpu <= parsed.vcpus:
        return None
    return _format_sku(parsed, new_vcpu)


def _cross_family_target(parsed: ParsedVmSku, util: VmUtilization) -> tuple[str, int, str] | None:
    """Suggest target family, vCPU count, and rationale for a lateral SKU move."""
    cpu = util.avg_cpu_pct
    mem = util.avg_memory_pct
    if cpu is None or mem is None:
        return None

    if parsed.family == "D" and cpu < 20 and mem < 25:
        return "B", max(1, parsed.vcpus // 2), "Burstable fits sustained low CPU and memory with lower baseline cost"
    if mem >= 75 and cpu < 55 and parsed.family in {"D", "F", "B"}:
        return "E", parsed.vcpus, "Memory utilization is high relative to CPU — memory-optimized SKU may fit better"
    if cpu >= 75 and mem < 45 and parsed.family in {"D", "E", "B"}:
        return "F", parsed.vcpus, "CPU utilization is high relative to memory — compute-optimized SKU may fit better"
    if cpu < 20 and mem < 25 and parsed.family == "E":
        return "D", parsed.vcpus, "Memory-optimized SKU appears larger than workload needs"
    return None


def _cross_family_sku(
    parsed: ParsedVmSku,
    util: VmUtilization,
    catalog: list[dict[str, Any]] | None,
) -> tuple[str | None, str | None]:
    target = _cross_family_target(parsed, util)
    if not target:
        return None, None
    family, vcpus, _why = target
    sku = _find_catalog_sku(
        catalog,
        family=family,
        vcpus=vcpus,
        variant=parsed.variant,
        version=parsed.version,
        tier=parsed.tier,
    )
    if not sku:
        sku = _format_sku(parsed, vcpus, family=family)
        sku = _resolve_suggested_sku(sku, catalog)
    return sku, family


def recommend_vm_sku(
    *,
    current_sku: str,
    utilization: VmUtilization,
    catalog: list[dict[str, Any]] | None = None,
    cpu_down_pct: float = 25.0,
    cpu_up_pct: float = 75.0,
    memory_down_pct: float = 30.0,
    memory_up_pct: float = 85.0,
    require_memory_for_downgrade: bool = True,
) -> VmSizingRecommendation | None:
    """
    Recommend downgrade, upgrade, or cross-family SKU change from CPU and memory signals.
    """
    parsed = parse_vm_sku(current_sku, catalog_entry=_catalog_index(catalog).get(current_sku))
    if not parsed:
        return None

    cpu = utilization.avg_cpu_pct
    mem = utilization.avg_memory_pct
    if cpu is None and mem is None:
        return VmSizingRecommendation(
            action="insufficient_data",
            current_sku=current_sku,
            suggested_sku=None,
            current_family=parsed.family,
            suggested_family=None,
            family_label=parsed.family_label,
            direction="none",
            avg_cpu_pct=cpu,
            avg_memory_pct=mem,
            confidence=0,
            reasons=["CPU and memory metrics are not available for this VM."],
        )

    reasons: list[str] = []
    if cpu is not None:
        reasons.append(f"Average CPU is {cpu:.1f}% over the metrics window.")
    if mem is not None:
        reasons.append(f"Estimated memory utilization is {mem:.1f}%.")

    cpu_low = cpu is not None and cpu < cpu_down_pct
    cpu_high = cpu is not None and cpu > cpu_up_pct
    mem_low = mem is not None and mem < memory_down_pct
    mem_high = mem is not None and mem > memory_up_pct
    can_downgrade = (cpu_low and mem_low) if require_memory_for_downgrade else (
        cpu_low or mem_low
    )

    if not cpu_high and not mem_high and not can_downgrade:
        return VmSizingRecommendation(
            action="no_change",
            current_sku=current_sku,
            suggested_sku=None,
            current_family=parsed.family,
            suggested_family=None,
            family_label=parsed.family_label,
            direction="none",
            avg_cpu_pct=cpu,
            avg_memory_pct=mem,
            confidence=72 if utilization.has_cpu and utilization.has_memory else 58,
            reasons=reasons + ["Current SKU matches observed CPU and memory utilization."],
        )

    if cpu_high or mem_high:
        suggested = _step_sku_within_family(parsed, "up", catalog)
        action: SizingAction = "upgrade"
        direction: Literal["down", "up", "lateral", "none"] = "up"
        confidence = 80
        if cpu_high:
            reasons.append(f"CPU exceeds {cpu_up_pct:.0f}% — consider a larger SKU.")
        if mem_high:
            reasons.append(f"Memory exceeds {memory_up_pct:.0f}% — consider more memory.")
        if not suggested:
            suggested, target_family = _cross_family_sku(parsed, utilization, catalog)
            if suggested:
                action = "cross_family"
                direction = "lateral"
                reasons.append(
                    f"Workload shape may fit the {FAMILY_PROFILES.get(target_family or '', {}).get('label', target_family)} family better."
                )
                confidence = 68
            else:
                return VmSizingRecommendation(
                    action="no_change",
                    current_sku=current_sku,
                    suggested_sku=None,
                    current_family=parsed.family,
                    suggested_family=None,
                    family_label=parsed.family_label,
                    direction="none",
                    avg_cpu_pct=cpu,
                    avg_memory_pct=mem,
                    confidence=55,
                    reasons=reasons + ["Workload needs more capacity but no safe larger SKU was identified."],
                )
        suggested = _resolve_suggested_sku(suggested, catalog)
        if not suggested:
            return VmSizingRecommendation(
                action="no_change",
                current_sku=current_sku,
                suggested_sku=None,
                current_family=parsed.family,
                suggested_family=None,
                family_label=parsed.family_label,
                direction="none",
                avg_cpu_pct=cpu,
                avg_memory_pct=mem,
                confidence=55,
                reasons=reasons + ["No validated larger SKU is available in this region."],
            )
        suggested_family = parse_vm_sku(suggested).family if suggested else None
        return VmSizingRecommendation(
            action=action,
            current_sku=current_sku,
            suggested_sku=suggested,
            current_family=parsed.family,
            suggested_family=suggested_family,
            family_label=parsed.family_label,
            direction=direction,
            avg_cpu_pct=cpu,
            avg_memory_pct=mem,
            confidence=confidence,
            reasons=reasons,
        )

    # Downsize path
    suggested = _step_sku_within_family(parsed, "down", catalog)
    action = "downgrade"
    direction = "down"
    confidence = 78
    if cpu_low:
        reasons.append(f"CPU is below {cpu_down_pct:.0f}% — a smaller SKU may be sufficient.")
    if mem_low:
        reasons.append(f"Memory utilization is below {memory_down_pct:.0f}%.")

    if not suggested:
        suggested, target_family = _cross_family_sku(parsed, utilization, catalog)
        if suggested:
            action = "cross_family"
            direction = "lateral"
            reasons.append(
                f"Workload shape may fit the {FAMILY_PROFILES.get(target_family or '', {}).get('label', target_family)} family better."
            )
            confidence = 66
        else:
            return VmSizingRecommendation(
                action="no_change",
                current_sku=current_sku,
                suggested_sku=None,
                current_family=parsed.family,
                suggested_family=None,
                family_label=parsed.family_label,
                direction="none",
                avg_cpu_pct=cpu,
                avg_memory_pct=mem,
                confidence=54,
                reasons=reasons + ["Workload is underutilized but this is already the smallest matching SKU."],
            )

    suggested = _resolve_suggested_sku(suggested, catalog)
    if not suggested:
        return VmSizingRecommendation(
            action="no_change",
            current_sku=current_sku,
            suggested_sku=None,
            current_family=parsed.family,
            suggested_family=None,
            family_label=parsed.family_label,
            direction="none",
            avg_cpu_pct=cpu,
            avg_memory_pct=mem,
            confidence=54,
            reasons=reasons + ["Workload is underutilized but no validated smaller SKU was found in this region."],
        )

    suggested_family = parse_vm_sku(suggested).family if suggested else None
    return VmSizingRecommendation(
        action=action,
        current_sku=current_sku,
        suggested_sku=suggested,
        current_family=parsed.family,
        suggested_family=suggested_family,
        family_label=parsed.family_label,
        direction=direction,
        avg_cpu_pct=cpu,
        avg_memory_pct=mem,
        confidence=confidence,
        reasons=reasons,
    )


def suggest_smaller_sku(sku: str, catalog: list[dict[str, Any]] | None = None) -> str | None:
    """Suggest a smaller SKU within the same family for the standard engine."""
    parsed = parse_vm_sku(sku)
    if not parsed:
        return None
    stepped = _step_sku_within_family(parsed, "down", catalog)
    return _resolve_suggested_sku(stepped, catalog)
