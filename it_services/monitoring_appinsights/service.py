"""IT service entity — public exports for Application Insights."""

from __future__ import annotations

SERVICE_ID = "monitoring-appinsights"
CANONICAL_TYPE = "monitoring/appinsights"
ARM_TYPE = "Microsoft.Insights/components"
DISPLAY_NAME = "Application Insights"
API_SLUG = "appinsights"
COMPONENT = "Monitoring"

from it_services.monitoring_appinsights.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.monitoring_appinsights.engine.sub_engine import AppInsightsSubEngine as SubEngine

