"""Compatibility aggregate — functions moved to it_services."""
from it_services.messaging_eventhub.engine.analysis import analyze_event_hubs
from it_services.messaging_servicebus.engine.analysis import analyze_service_bus

__all__ = ['analyze_event_hubs', 'analyze_service_bus']
