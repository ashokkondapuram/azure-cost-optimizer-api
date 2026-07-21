"""Kafka-backed Azure API throttling for sync pipeline stages."""

from app.messaging.api_throttle.config import kafka_api_throttle_enabled

__all__ = ["kafka_api_throttle_enabled"]
