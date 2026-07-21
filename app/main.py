"""Backward-compatible ASGI entry shim (integration tests and legacy tooling only).

Production runs split platform microservices. Prefer:
  ./docker/build.sh up
  services/README.md — per-service uvicorn targets
"""

from __future__ import annotations

import warnings

warnings.warn(
    "app.main is deprecated. Use platform microservices (./docker/build.sh up) "
    "or app.integration_app for pytest.",
    DeprecationWarning,
    stacklevel=2,
)

from app.integration_app import app  # noqa: F401

__all__ = ["app"]
