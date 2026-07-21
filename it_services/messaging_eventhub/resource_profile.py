"""Resource profile — owned by messaging-eventhub IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, metric, utilization_metric as um

CANONICAL_TYPE = "messaging/eventhub"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.EventHub/namespaces",
    display_name="Event Hubs namespace",
    sync_property_paths=("provisioningState", "kafkaEnabled", "isAutoInflateEnabled"),
    generic_arm_sync=True,
    fields=(),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.eventhub/namespaces",
    canonical_type=CANONICAL_TYPE,
    display_name="Event Hubs namespace",
    doc_ref="microsoft-eventhub-namespaces-metrics",
    metrics=(
        um("IncomingMessages", "incoming_messages", "Incoming messages", aggregation="Total",
           rules=("EVENT_HUBS_TIER",)),
        um("OutgoingMessages", "outgoing_messages", "Outgoing messages", aggregation="Total",
           rules=("EVENT_HUBS_TIER",)),
    ),
)

EXTRA_USAGE_METRICS = (
    metric("cost_export", "mtd_cost", "monthly_cost_usd",
           "Month-to-date billed cost", "P7D", "EVENT_HUBS_TIER"),
)
