"""IT service entity — public exports for App Service plan."""

from __future__ import annotations

SERVICE_ID = "appservice-plan"
CANONICAL_TYPE = "appservice/plan"
ARM_TYPE = "Microsoft.Web/serverFarms"
DISPLAY_NAME = "App Service plan"
API_SLUG = "appserviceplans"
COMPONENT = "App Service"

from it_services.appservice_plan.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC


SubEngine = None  # profile-only service
