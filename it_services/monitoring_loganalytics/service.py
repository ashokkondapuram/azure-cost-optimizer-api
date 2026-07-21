"""IT service entity — public exports for Log Analytics workspace."""

from __future__ import annotations

SERVICE_ID = "monitoring-loganalytics"
CANONICAL_TYPE = "monitoring/loganalytics"
ARM_TYPE = "Microsoft.OperationalInsights/workspaces"
DISPLAY_NAME = "Log Analytics workspace"
API_SLUG = "loganalytics"
COMPONENT = "Monitoring"

from it_services.monitoring_loganalytics.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.monitoring_loganalytics.engine.sub_engine import LogAnalyticsSubEngine as SubEngine

