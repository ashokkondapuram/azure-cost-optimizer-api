"""Kafka messaging errors."""

from __future__ import annotations


class KafkaPublishExhaustedError(RuntimeError):
    """Raised when all publish retries are exhausted.

    The pipeline is left in a retriable ``running`` state so resume or consumer
    redelivery can re-drive the stage.
    """
