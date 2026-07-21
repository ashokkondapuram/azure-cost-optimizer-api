"""IT service entity — public exports for AKS cluster."""

from __future__ import annotations

SERVICE_ID = "containers-aks"
CANONICAL_TYPE = "containers/aks"
ARM_TYPE = "Microsoft.ContainerService/managedClusters"
DISPLAY_NAME = "AKS cluster"
API_SLUG = "aks"
COMPONENT = "AKS"

from it_services.containers_aks.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.containers_aks.engine.sub_engine import AksSubEngine as SubEngine

