"""IT service entity — public exports for Managed disk."""

from __future__ import annotations

SERVICE_ID = "compute-disk"
CANONICAL_TYPE = "compute/disk"
ARM_TYPE = "Microsoft.Compute/disks"
DISPLAY_NAME = "Managed disk"
API_SLUG = "disks"
COMPONENT = "Managed Disks"

from it_services.compute_disk.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.compute_disk.engine.sub_engine import DiskSubEngine as SubEngine

