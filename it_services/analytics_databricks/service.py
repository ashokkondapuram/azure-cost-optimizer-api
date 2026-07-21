"""IT service entity — public exports for Azure Databricks."""

from __future__ import annotations

SERVICE_ID = "analytics-databricks"
CANONICAL_TYPE = "analytics/databricks"
ARM_TYPE = "Microsoft.Databricks/workspaces"
DISPLAY_NAME = "Azure Databricks"
API_SLUG = "databricks"
COMPONENT = "Analytics"

from it_services.analytics_databricks.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.analytics_databricks.engine.sub_engine import DatabricksSubEngine as SubEngine

