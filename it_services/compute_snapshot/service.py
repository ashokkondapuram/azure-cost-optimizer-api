"""IT service entity — public exports for Disk snapshot."""

from __future__ import annotations

SERVICE_ID = "compute-snapshot"
CANONICAL_TYPE = "compute/snapshot"
ARM_TYPE = "Microsoft.Compute/snapshots"
DISPLAY_NAME = "Disk snapshot"
API_SLUG = "snapshots"
COMPONENT = "Disk Snapshots"

from it_services.compute_snapshot.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.compute_snapshot.engine.sub_engine import SnapshotSubEngine as SubEngine

