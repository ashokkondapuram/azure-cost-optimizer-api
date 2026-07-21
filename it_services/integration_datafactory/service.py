"""IT service entity — public exports for Data Factory."""

from __future__ import annotations

SERVICE_ID = "integration-datafactory"
CANONICAL_TYPE = "integration/datafactory"
ARM_TYPE = "Microsoft.DataFactory/factories"
DISPLAY_NAME = "Data Factory"
API_SLUG = "datafactory"
COMPONENT = "Integration"

from it_services.integration_datafactory.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.integration_datafactory.engine.sub_engine import DataFactorySubEngine as SubEngine

