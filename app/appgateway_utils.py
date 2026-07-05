"""Application Gateway technical helpers."""

from __future__ import annotations

from typing import Any


def _listener_ref_id(listener_ref: Any) -> str:
    if isinstance(listener_ref, dict):
        return (listener_ref.get("id") or "").strip().lower()
    return ""


def http_listener_count(properties: dict[str, Any] | None) -> int:
    """
    Count HTTP/HTTPS listeners on an Application Gateway.

    ARM list-all responses often omit or empty ``httpListeners`` even when the
    gateway has listeners; use a per-resource GET during sync for authoritative data.
    Falls back to unique httpListener references on requestRoutingRules when needed.
    """
    props = properties or {}
    listeners = props.get("httpListeners")
    if isinstance(listeners, list) and listeners:
        return len(listeners)

    refs: set[str] = set()
    for rule in props.get("requestRoutingRules") or []:
        if not isinstance(rule, dict):
            continue
        rid = _listener_ref_id((rule.get("properties") or {}).get("httpListener"))
        if rid:
            refs.add(rid)
    return len(refs)


def application_gateway_has_listeners(properties: dict[str, Any] | None) -> bool:
    return http_listener_count(properties) > 0


def application_gateway_listener_details(properties: dict[str, Any] | None) -> list[dict[str, str]]:
    """Summarize listeners for engine evidence and UI (name + protocol)."""
    props = properties or {}
    details: list[dict[str, str]] = []
    listeners = props.get("httpListeners") or []
    if isinstance(listeners, list) and listeners:
        for item in listeners:
            if not isinstance(item, dict):
                continue
            lip = item.get("properties") or {}
            details.append({
                "name": str(item.get("name") or "").strip(),
                "protocol": str(lip.get("protocol") or "").strip(),
            })
        return [d for d in details if d.get("name")]

    for rule in props.get("requestRoutingRules") or []:
        if not isinstance(rule, dict):
            continue
        rprops = rule.get("properties") or {}
        listener_ref = rprops.get("httpListener") or {}
        ref_id = _listener_ref_id(listener_ref)
        if not ref_id:
            continue
        name = ref_id.rsplit("/", 1)[-1]
        details.append({
            "name": name,
            "protocol": "",
            "routing_rule": str(rule.get("name") or "").strip(),
        })
    return details
