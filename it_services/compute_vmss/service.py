"""IT service entity — public exports for Virtual machine scale set."""

from __future__ import annotations

SERVICE_ID = "compute-vmss"
CANONICAL_TYPE = "compute/vmss"
ARM_TYPE = "Microsoft.Compute/virtualMachineScaleSets"
DISPLAY_NAME = "Virtual machine scale set"
API_SLUG = "vmss"
COMPONENT = "Virtual Machine Scale Sets"

from it_services.compute_vmss.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.compute_vmss.engine.sub_engine import VmssSubEngine as SubEngine

