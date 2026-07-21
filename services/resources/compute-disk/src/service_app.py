"""Compute-disk microservice — extended JSON rules and Azure-billed cost analysis."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_DISK_SPEC = ROOT / "data" / "disk-assessment.json"
os.environ.setdefault("ASSESSMENT_DATA_DIR", str(ROOT / "data"))

from costoptimizer_core import create_resource_service, get_service_config

SERVICE_ID = "compute-disk"
_base = create_resource_service(get_service_config(SERVICE_ID))


def _mount_disk_extensions(app):
    from typing import Any

    from app.disk_analysis_config import extended_disk_spec_payload, disk_rule_ids

    @app.get("/v1/rules/extended")
    def rules_extended() -> dict[str, Any]:
        return extended_disk_spec_payload()

    @app.get("/v1/rules")
    def list_disk_rules() -> dict[str, Any]:
        payload = extended_disk_spec_payload()
        return {
            "canonical_type": payload.get("canonical_type", "compute/disk"),
            "component": "Managed Disks",
            "rules": disk_rule_ids(),
            "cost_policy": payload.get("cost_policy") or {},
            "schema_version": payload.get("schema_version"),
            "assessment_file": payload.get("assessment_file"),
        }


_mount_disk_extensions(_base)
app = _base

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8108"))
    uvicorn.run(
        "service_app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        reload=os.getenv("RELOAD", "") == "1",
    )
