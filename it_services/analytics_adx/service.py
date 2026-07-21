"""IT service entity — public exports for Azure Data Explorer."""

from __future__ import annotations

SERVICE_ID = "analytics-adx"
CANONICAL_TYPE = "analytics/adx"
ARM_TYPE = "Microsoft.Kusto/clusters"
DISPLAY_NAME = "Azure Data Explorer"
API_SLUG = "adx"
COMPONENT = "Analytics"

from it_services.analytics_adx.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.analytics_adx.engine.sub_engine import AdxSubEngine as SubEngine

