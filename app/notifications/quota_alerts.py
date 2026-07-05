"""Quota Alerts

Fires webhook / email notifications when any subscription's quota crosses
the warning (80%) or critical (95%) thresholds.

Integrates with the existing webhook_dispatcher and email_digest from
app/notifications/.

Usage (from scheduler or endpoint):

    from app.notifications.quota_alerts import check_and_notify_quota
    await check_and_notify_quota(db, location="eastus")
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_WARN_PCT = 80.0
_CRITICAL_PCT = 95.0


def _build_quota_alert_payload(
    subscription_id: str,
    location: str,
    critical: list[dict],
    warning: list[dict],
) -> dict[str, Any]:
    """Build a normalised notification payload for quota breaches."""
    severity = "critical" if critical else "warning"
    lines = []
    for item in critical:
        lines.append(
            f"❌ CRITICAL: {item['localized_name']} — "
            f"{item['current']}/{item['limit']} ({item['usage_pct']}%)"
        )
    for item in warning:
        lines.append(
            f"⚠️ WARNING: {item['localized_name']} — "
            f"{item['current']}/{item['limit']} ({item['usage_pct']}%)"
        )
    return {
        "type": "quota_alert",
        "severity": severity,
        "subscription_id": subscription_id,
        "location": location,
        "critical_count": len(critical),
        "warning_count": len(warning),
        "summary": f"Quota alert for {subscription_id} @ {location}: "
                   f"{len(critical)} critical, {len(warning)} warning",
        "details": lines,
        "items": critical + warning,
    }


async def check_and_notify_quota(
    db,
    location: str,
    subscription_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Check quota for all (or specified) subscriptions and fire alerts.

    Returns a list of alert payloads fired.
    """
    from app.routers.quota import (
        _fetch_compute_quota,
        _fetch_network_quota,
        _fetch_storage_quota,
        _near_limit,
    )
    from app.auth import auth_headers

    if subscription_ids is None:
        from app.subscription_store import list_active_subscriptions
        subs = [s.subscription_id for s in list_active_subscriptions(db)]
    else:
        subs = subscription_ids

    headers = auth_headers(db)
    fired: list[dict[str, Any]] = []

    for sub in subs:
        all_items: list[dict] = []
        for fetcher in (_fetch_compute_quota, _fetch_network_quota, _fetch_storage_quota):
            all_items.extend(fetcher(sub, location, headers))

        near = _near_limit(all_items)
        critical = [i for i in near if i.get("status") == "critical"]
        warning = [i for i in near if i.get("status") == "warning"]

        if not near:
            continue

        payload = _build_quota_alert_payload(sub, location, critical, warning)
        fired.append(payload)

        # Fire webhook
        try:
            from app.notifications.webhook_dispatcher import dispatch_webhook
            await dispatch_webhook(payload)
        except Exception as exc:
            log.warning("quota_alert.webhook_failed", sub=sub, error=str(exc))

        # Fire email if critical
        if critical:
            try:
                from app.notifications.email_digest import send_email_alert
                await send_email_alert(
                    subject=f"[CRITICAL] Azure Quota Alert — {sub} @ {location}",
                    body="\n".join(payload["details"]),
                )
            except Exception as exc:
                log.warning("quota_alert.email_failed", sub=sub, error=str(exc))

        log.info(
            "quota_alert.fired",
            sub=sub,
            location=location,
            critical=len(critical),
            warning=len(warning),
        )

    return fired


async def check_and_notify_maintenance(
    db,
    subscription_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Check planned maintenance events across subscriptions and fire alerts.

    Fires a webhook for any subscription that has active planned maintenance
    health events or VMSS with pending model updates.
    Returns a list of alert payloads fired.
    """
    from app.azure_maintenance import AzureMaintenanceClient

    if subscription_ids is None:
        from app.subscription_store import list_active_subscriptions
        subs = [s.subscription_id for s in list_active_subscriptions(db)]
    else:
        subs = subscription_ids

    fired: list[dict[str, Any]] = []

    for sub in subs:
        mc = AzureMaintenanceClient(db=db)
        events = mc.list_resource_health_events(sub, filter_planned=True)

        # Check VMSS pending model updates
        from app.azure_resources import AzureResourcesClient
        rc = AzureResourcesClient(db=db)
        vmss_list = rc.list_vm_scale_sets(sub, include_maintenance=False)
        pending_vmss: list[dict] = []
        for vmss in vmss_list:
            rid = vmss.get("id", "")
            parts = rid.split("/")
            try:
                rg_idx = [p.lower() for p in parts].index("resourcegroups")
                rg = parts[rg_idx + 1]
            except (ValueError, IndexError):
                continue
            name = vmss.get("name", "")
            if not name:
                continue
            instances = mc.list_vmss_instance_maintenance(sub, rg, name)
            pending = sum(1 for i in instances if i.get("pending_model_update"))
            if pending > 0:
                pending_vmss.append({
                    "vmss_name": name,
                    "resource_group": rg,
                    "pending_updates": pending,
                    "instance_count": len(instances),
                })

        if not events and not pending_vmss:
            continue

        severity = "critical" if events else "warning"
        details = []
        for e in events:
            props = e.get("properties") or {}
            details.append(
                f"🔧 Planned Maintenance: {props.get('title', 'Unknown')} "
                f"| Resource: {props.get('impactedResource', 'N/A')} "
                f"| Start: {props.get('impactStartTime', 'TBD')}"
            )
        for v in pending_vmss:
            details.append(
                f"⏳ VMSS {v['vmss_name']} ({v['resource_group']}): "
                f"{v['pending_updates']}/{v['instance_count']} instances pending model update"
            )

        payload = {
            "type": "maintenance_alert",
            "severity": severity,
            "subscription_id": sub,
            "planned_maintenance_events": len(events),
            "vmss_pending_updates": len(pending_vmss),
            "summary": f"Maintenance alert for {sub}: "
                       f"{len(events)} planned events, "
                       f"{len(pending_vmss)} VMSS with pending updates",
            "details": details,
        }
        fired.append(payload)

        try:
            from app.notifications.webhook_dispatcher import dispatch_webhook
            await dispatch_webhook(payload)
        except Exception as exc:
            log.warning("maintenance_alert.webhook_failed", sub=sub, error=str(exc))

        if severity == "critical":
            try:
                from app.notifications.email_digest import send_email_alert
                await send_email_alert(
                    subject=f"[MAINTENANCE] Azure Planned Maintenance — {sub}",
                    body="\n".join(details),
                )
            except Exception as exc:
                log.warning("maintenance_alert.email_failed", sub=sub, error=str(exc))

        log.info(
            "maintenance_alert.fired",
            sub=sub,
            events=len(events),
            vmss_pending=len(pending_vmss),
        )

    return fired
