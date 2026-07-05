"""VM ↔ disk ↔ NIC relationship graph and remediation action chains."""
from __future__ import annotations

import uuid
from typing import Any

from app.focus_mapping import normalize_arm_id

_VM_STOP_RULES = frozenset({
    "VM_STOPPED_BILLING_EXTENDED",
    "VM_STOPPED_DEALLOCATED",
    "VM_IDLE",
})
_NIC_RULES = frozenset({"NIC_UNATTACHED", "NIC_ORPHANED_EXTENDED", "UNUSED_NIC"})
_PIP_RULES = frozenset({"IP_UNASSOCIATED", "PUBLIC_IP_IDLE_EXTENDED", "IP_IDLE_EXTENDED"})
_DISK_RULES = frozenset({
    "DISK_UNATTACHED",
    "DISK_UNUSED_EXTENDED",
    "DISK_OVERSIZE_EXTENDED",
})
_SNAPSHOT_RULES = frozenset({"SNAPSHOT_OLD", "SNAPSHOT_RETENTION_EXTENDED"})


def build_disk_snapshot_links(snapshots: list[dict]) -> dict[str, list[str]]:
    """Map source disk ARM id → snapshot ARM ids."""
    links: dict[str, list[str]] = {}
    for snap in snapshots or []:
        snap_id = normalize_arm_id(snap.get("id") or "")
        if not snap_id:
            continue
        props = snap.get("properties") or {}
        source = (props.get("creationData") or {}).get("sourceResourceId")
        if not source:
            continue
        disk_id = normalize_arm_id(source).lower()
        links.setdefault(disk_id, []).append(snap_id.lower())
    return links


def build_resource_graph(buckets: dict[str, list]) -> dict[str, dict[str, list[str]]]:
    """Map VM ARM ids to attached disk and NIC ids (and NIC public IPs)."""
    graph: dict[str, dict[str, list[str]]] = {}
    nics_by_id = {
        normalize_arm_id(n.get("id") or "").lower(): n
        for n in (buckets.get("network_interfaces") or [])
        if n.get("id")
    }

    for vm in buckets.get("vms") or []:
        vm_id = normalize_arm_id(vm.get("id") or "").lower()
        if not vm_id:
            continue
        props = vm.get("properties") or {}
        storage = props.get("storageProfile") or {}
        disk_ids: list[str] = []
        os_md = ((storage.get("osDisk") or {}).get("managedDisk") or {}).get("id")
        if os_md:
            disk_ids.append(normalize_arm_id(os_md).lower())
        for data_disk in storage.get("dataDisks") or []:
            md_id = ((data_disk.get("managedDisk") or {}).get("id"))
            if md_id:
                disk_ids.append(normalize_arm_id(md_id).lower())

        nic_ids: list[str] = []
        for nic_ref in (props.get("networkProfile") or {}).get("networkInterfaces") or []:
            nic_id = nic_ref.get("id")
            if nic_id:
                nic_ids.append(normalize_arm_id(nic_id).lower())

        pip_ids: list[str] = []
        for nic_id in nic_ids:
            nic = nics_by_id.get(nic_id) or {}
            for cfg in (nic.get("properties") or {}).get("ipConfigurations") or []:
                inner = cfg.get("properties") if isinstance(cfg.get("properties"), dict) else cfg
                pip_id = (inner or {}).get("publicIPAddress", {}).get("id")
                if pip_id:
                    pip_ids.append(normalize_arm_id(pip_id).lower())

        graph[vm_id] = {
            "disk_ids": list(dict.fromkeys(disk_ids)),
            "nic_ids": list(dict.fromkeys(nic_ids)),
            "public_ip_ids": list(dict.fromkeys(pip_ids)),
        }
    return graph


def assign_action_chains(
    findings: list[dict[str, Any]],
    resource_graph: dict[str, dict[str, list[str]]],
    *,
    disk_snapshot_links: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Group related remediation findings into ordered action chains."""
    if not findings:
        return findings

    by_resource: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        rid = normalize_arm_id(finding.get("resource_id") or "").lower()
        if rid:
            by_resource.setdefault(rid, []).append(finding)

    chained_ids: set[int] = set()

    def _chain_group(steps: list[dict[str, Any]]) -> None:
        if len(steps) < 2:
            return
        chain_id = uuid.uuid4().hex[:8]
        total = len(steps)
        for idx, finding in enumerate(steps, start=1):
            finding["chain_id"] = chain_id
            finding["chain_step"] = idx
            finding["chain_total"] = total
            chained_ids.add(id(finding))

    for vm_id, links in resource_graph.items():
        vm_findings = by_resource.get(vm_id) or []
        vm_anchor = next(
            (f for f in vm_findings if f.get("rule_id") in _VM_STOP_RULES),
            None,
        )
        if not vm_anchor:
            continue

        steps: list[dict[str, Any]] = [vm_anchor]
        related: list[str] = list(links.get("nic_ids") or [])
        related.extend(links.get("public_ip_ids") or [])

        for related_id in related:
            for finding in by_resource.get(related_id) or []:
                if finding.get("rule_id") in _NIC_RULES | _PIP_RULES:
                    steps.append(finding)
                    break

        _chain_group(steps)

    for vm_id, links in resource_graph.items():
        vm_findings = by_resource.get(vm_id) or []
        vm_anchor = next((f for f in vm_findings if f.get("rule_id") in _VM_STOP_RULES), None)
        if not vm_anchor:
            vm_anchor = next((f for f in vm_findings if "VM" in (f.get("rule_id") or "")), None)
        for disk_id in links.get("disk_ids") or []:
            for finding in by_resource.get(disk_id) or []:
                if id(finding) in chained_ids:
                    continue
                if finding.get("rule_id") not in _DISK_RULES:
                    continue
                if vm_anchor:
                    chain_id = uuid.uuid4().hex[:8]
                    if not vm_anchor.get("chain_id"):
                        vm_anchor["chain_id"] = chain_id
                        vm_anchor["chain_step"] = 1
                        vm_anchor["chain_total"] = 2
                    finding["chain_id"] = vm_anchor.get("chain_id") or chain_id
                    finding["chain_step"] = 2
                    finding["chain_total"] = max(vm_anchor.get("chain_total") or 2, 2)
                    chained_ids.add(id(finding))
                    chained_ids.add(id(vm_anchor))
                break

    for disk_id, snapshot_ids in (disk_snapshot_links or {}).items():
        disk_findings = [
            f for f in by_resource.get(disk_id) or []
            if f.get("rule_id") in _DISK_RULES
        ]
        if not disk_findings:
            continue
        disk_anchor = disk_findings[0]
        steps = [disk_anchor]
        for snap_id in snapshot_ids:
            for finding in by_resource.get(snap_id) or []:
                if finding.get("rule_id") in _SNAPSHOT_RULES:
                    steps.append(finding)
                    break
        _chain_group(steps)

    return findings
