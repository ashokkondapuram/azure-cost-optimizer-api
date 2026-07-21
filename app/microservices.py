"""Microservices platform configuration helpers."""

from __future__ import annotations

import os

MICROSERVICES_ENABLED = os.getenv("MICROSERVICES_ENABLED", "1") == "1"
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")


def gateway_handles_resource(api_slug: str) -> bool:
    if not MICROSERVICES_ENABLED:
        return False
    try:
        from costoptimizer_core.registry import get_service_by_api_slug
    except ImportError:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "packages" / "costoptimizer-core"))
        from costoptimizer_core.registry import get_service_by_api_slug

    cfg = get_service_by_api_slug(api_slug)
    return bool(cfg and cfg.migrated)
