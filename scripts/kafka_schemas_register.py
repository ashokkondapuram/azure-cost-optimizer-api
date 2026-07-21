#!/usr/bin/env python3
"""Register sync pipeline JSON schemas with Redpanda Schema Registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.messaging.schema_registry import register_schemas, verify_schemas_registered  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Register or verify Kafka message schemas.")
    parser.add_argument(
        "--registry-url",
        default=None,
        help="Schema Registry URL (default: KAFKA_SCHEMA_REGISTRY_URL or http://127.0.0.1:18081)",
    )
    parser.add_argument(
        "--wait-sec",
        type=float,
        default=60.0,
        help="Seconds to wait for registry readiness (default: 60)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify schemas are registered (do not register)",
    )
    args = parser.parse_args()

    if args.verify:
        return verify_schemas_registered(registry_url=args.registry_url)

    register_schemas(registry_url=args.registry_url, wait_sec=args.wait_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
