"""IT service entity — public exports for Service Bus namespace."""

from __future__ import annotations

SERVICE_ID = "messaging-servicebus"
CANONICAL_TYPE = "messaging/servicebus"
ARM_TYPE = "Microsoft.ServiceBus/namespaces"
DISPLAY_NAME = "Service Bus namespace"
API_SLUG = "servicebus"
COMPONENT = "Messaging"

from it_services.messaging_servicebus.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.messaging_servicebus.engine.sub_engine import ServiceBusSubEngine as SubEngine

