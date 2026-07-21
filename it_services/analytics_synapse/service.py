"""IT service entity — public exports for Azure Synapse."""

from __future__ import annotations

SERVICE_ID = "analytics-synapse"
CANONICAL_TYPE = "analytics/synapse"
ARM_TYPE = "Microsoft.Synapse/workspaces"
DISPLAY_NAME = "Azure Synapse"
API_SLUG = "synapse"
COMPONENT = "Analytics"

from it_services.analytics_synapse.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.analytics_synapse.engine.sub_engine import SynapseSubEngine as SubEngine

