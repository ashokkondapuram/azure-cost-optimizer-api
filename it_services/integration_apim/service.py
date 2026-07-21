"""IT service entity — public exports for API Management."""

from __future__ import annotations

SERVICE_ID = "integration-apim"
CANONICAL_TYPE = "integration/apim"
ARM_TYPE = "Microsoft.ApiManagement/service"
DISPLAY_NAME = "API Management"
API_SLUG = "apim"
COMPONENT = "Integration"

from it_services.integration_apim.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.integration_apim.engine.sub_engine import ApimSubEngine as SubEngine

