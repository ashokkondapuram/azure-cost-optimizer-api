"""IT service entity — public exports for Container registry."""

from __future__ import annotations

SERVICE_ID = "containers-acr"
CANONICAL_TYPE = "containers/acr"
ARM_TYPE = "Microsoft.ContainerRegistry/registries"
DISPLAY_NAME = "Container registry"
API_SLUG = "acr"
COMPONENT = "Container Registry"

from it_services.containers_acr.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.containers_acr.engine.sub_engine import AcrSubEngine as SubEngine

