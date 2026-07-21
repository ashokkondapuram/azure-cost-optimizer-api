#!/usr/bin/env python3
"""Provision Kafka topics and register schemas for the sync pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.messaging.schema_registry import register_schemas, verify_schemas_registered  # noqa: E402
from scripts.kafka_topics_provision import provision_topics, verify_topics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision topics and register schemas.")
    parser.add_argument("--brokers", default="127.0.0.1:9092")
    parser.add_argument(
        "--registry-url",
        default=None,
        help="Schema Registry URL (default: KAFKA_SCHEMA_REGISTRY_URL)",
    )
    parser.add_argument("--wait-sec", type=float, default=60.0)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--skip-schemas", action="store_true")
    args = parser.parse_args()

    if args.verify:
        topic_rc = verify_topics(brokers=args.brokers, wait_sec=args.wait_sec)
        if args.skip_schemas:
            return topic_rc
        schema_rc = verify_schemas_registered(registry_url=args.registry_url)
        return max(topic_rc, schema_rc)

    topic_rc = provision_topics(brokers=args.brokers, wait_sec=args.wait_sec)
    if topic_rc != 0:
        return topic_rc
    if args.skip_schemas:
        return 0

    register_schemas(registry_url=args.registry_url, wait_sec=args.wait_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
