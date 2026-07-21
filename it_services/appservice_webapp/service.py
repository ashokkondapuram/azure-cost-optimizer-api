"""IT service entity — public exports for App Service."""

from __future__ import annotations

SERVICE_ID = "appservice-webapp"
CANONICAL_TYPE = "appservice/webapp"
ARM_TYPE = "Microsoft.Web/sites"
DISPLAY_NAME = "App Service"
API_SLUG = "appservices"
COMPONENT = "App Service"

from it_services.appservice_webapp.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.appservice_webapp.engine.sub_engine import AppServiceSubEngine as SubEngine

