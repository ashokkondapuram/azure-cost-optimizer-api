"""IT service entity — public exports for Event Hubs namespace."""

from __future__ import annotations

SERVICE_ID = "messaging-eventhub"
CANONICAL_TYPE = "messaging/eventhub"
ARM_TYPE = "Microsoft.EventHub/namespaces"
DISPLAY_NAME = "Event Hubs namespace"
API_SLUG = "eventhubs"
COMPONENT = "Messaging"

from it_services.messaging_eventhub.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.messaging_eventhub.engine.sub_engine import EventHubSubEngine as SubEngine

