"""IT service entity — public exports for Logic App."""

from __future__ import annotations

SERVICE_ID = "integration-logicapp"
CANONICAL_TYPE = "integration/logicapp"
ARM_TYPE = "Microsoft.Logic/workflows"
DISPLAY_NAME = "Logic App"
API_SLUG = "logicapps"
COMPONENT = "Integration"

from it_services.integration_logicapp.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.integration_logicapp.engine.sub_engine import LogicAppSubEngine as SubEngine

