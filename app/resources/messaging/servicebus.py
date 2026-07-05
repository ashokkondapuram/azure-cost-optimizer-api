from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "messaging/servicebus"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.ServiceBus/namespaces",
    display_name="Service Bus namespace",
    sync_property_paths=("provisioningState", "zoneRedundant"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.servicebus/namespaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Service Bus namespace",
    doc_ref="microsoft-servicebus-namespaces-metrics",
    metrics=(
        um("ActiveMessages", "active_messages", "Active messages in queues/topics",
           aggregation="Average",
           rules=("SERVICE_BUS_TIER",)),
        um("IncomingRequests", "incoming_requests", "Incoming requests", aggregation="Total",
           rules=("SERVICE_BUS_TIER",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "SERVICE_BUS_TIER"),
)
