"""IT service entity — public exports for Azure ML workspace."""

from __future__ import annotations

SERVICE_ID = "analytics-mlworkspace"
CANONICAL_TYPE = "analytics/mlworkspace"
ARM_TYPE = "Microsoft.MachineLearningServices/workspaces"
DISPLAY_NAME = "Azure ML workspace"
API_SLUG = "mlworkspace"
COMPONENT = "Analytics"

from it_services.analytics_mlworkspace.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.analytics_mlworkspace.engine.sub_engine import MlWorkspaceSubEngine as SubEngine

