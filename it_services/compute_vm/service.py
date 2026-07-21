"""IT service entity — public exports for Virtual machine."""

from __future__ import annotations

SERVICE_ID = "compute-vm"
CANONICAL_TYPE = "compute/vm"
ARM_TYPE = "Microsoft.Compute/virtualMachines"
DISPLAY_NAME = "Virtual machine"
API_SLUG = "vms"
COMPONENT = "Virtual Machines"

from it_services.compute_vm.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.compute_vm.engine.sub_engine import VmSubEngine as SubEngine

