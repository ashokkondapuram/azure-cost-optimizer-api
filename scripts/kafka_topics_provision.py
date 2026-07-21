#!/usr/bin/env python3
"""Provision Kafka topics from data/kafka-topics.yaml using confluent-kafka Admin API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.messaging.topic_admin import provision_topics, verify_topics, wait_for_broker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision or verify Kafka sync pipeline topics.")
    parser.add_argument(
        "--brokers",
        default="127.0.0.1:9092",
        help="Kafka bootstrap servers (default: 127.0.0.1:9092)",
    )
    parser.add_argument(
        "--wait-sec",
        type=float,
        default=60.0,
        help="Seconds to wait for broker readiness (default: 60)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify topics exist with expected partition counts",
    )
    args = parser.parse_args()

    if args.verify:
        return verify_topics(brokers=args.brokers, wait_sec=args.wait_sec)
    provision_topics(brokers=args.brokers, wait_sec=args.wait_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
