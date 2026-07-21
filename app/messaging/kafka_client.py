"""Thin Kafka producer/consumer wrapper (confluent-kafka)."""

from __future__ import annotations

import atexit
import threading
import time
from typing import Any, Callable

import structlog

from app.messaging.config import (
    kafka_auto_offset_reset,
    kafka_bootstrap_servers,
    kafka_client_id,
    kafka_connect_retry_delay_sec,
    kafka_connect_retry_max_delay_sec,
    kafka_consumer_group,
    kafka_enabled,
    kafka_message_max_bytes,
    kafka_poll_timeout_sec,
    kafka_publish_delivery_timeout_sec,
    kafka_publish_max_retries,
    kafka_publish_retry_backoff_sec,
    kafka_security_protocol,
    kafka_session_timeout_ms,
)
from app.messaging.job_envelope import JobEnvelope
from app.messaging.schema_registry import deserialize_envelope, serialize_envelope

log = structlog.get_logger(__name__)

_producer = None
_producer_lock = threading.Lock()
_consumer_threads: list[threading.Thread] = []
_shutdown = threading.Event()


def _require_confluent():
    try:
        from confluent_kafka import Consumer, Producer
    except ImportError as exc:
        raise RuntimeError(
            "confluent-kafka is not installed. Add it to requirements.txt or set KAFKA_ENABLED=false."
        ) from exc
    return Consumer, Producer


def _base_config() -> dict[str, Any]:
    return {
        "bootstrap.servers": kafka_bootstrap_servers(),
        "security.protocol": kafka_security_protocol(),
    }


def get_producer():
    """Return a process-wide Kafka producer (lazy singleton)."""
    global _producer
    if _producer is not None:
        return _producer
    with _producer_lock:
        if _producer is not None:
            return _producer
        _, Producer = _require_confluent()
        max_bytes = kafka_message_max_bytes()
        _producer = Producer(
            {
                **_base_config(),
                "client.id": kafka_client_id(),
                "acks": "all",
                "enable.idempotence": True,
                "compression.type": "lz4",
                "message.max.bytes": max_bytes,
            }
        )
        return _producer


def publish_envelope(
    envelope: JobEnvelope,
    *,
    topic: str,
    on_delivery: Callable[[Any, Any], None] | None = None,
) -> None:
    """Publish a job envelope to Kafka."""
    if not kafka_enabled():
        raise RuntimeError("Kafka is disabled (KAFKA_ENABLED=false).")

    producer = get_producer()
    value = serialize_envelope(envelope, topic=topic)
    producer.produce(
        topic=topic,
        key=envelope.partition_key(),
        value=value,
        on_delivery=on_delivery,
    )
    producer.poll(0)
    log.info(
        "kafka.publish",
        topic=topic,
        job_type=envelope.job_type.value,
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
    )


def flush_producer(timeout: float = 5.0) -> None:
    if _producer is not None:
        _producer.flush(timeout)


def _wait_for_delivery(
    producer,
    delivered: threading.Event,
    *,
    timeout_sec: float,
) -> bool:
    deadline = time.monotonic() + timeout_sec
    while not delivered.is_set() and time.monotonic() < deadline:
        producer.poll(0.1)
    return delivered.is_set()


def _publish_single_attempt(
    envelope: JobEnvelope,
    *,
    topic: str,
    delivery_timeout_sec: float,
) -> tuple[bool, str | None]:
    """Produce one message and wait for broker delivery acknowledgement."""
    delivery_error: dict[str, str] = {}
    delivered = threading.Event()

    def on_delivery(err, msg) -> None:
        if err is not None:
            delivery_error["error"] = str(err)
        delivered.set()

    try:
        publish_envelope(envelope, topic=topic, on_delivery=on_delivery)
        producer = get_producer()
        if not _wait_for_delivery(producer, delivered, timeout_sec=delivery_timeout_sec):
            return False, "delivery_timeout"
        if delivery_error:
            return False, delivery_error["error"]
        return True, None
    except Exception as exc:
        return False, str(exc)


def publish_envelope_safe(envelope: JobEnvelope, *, topic: str) -> bool:
    """Publish with retries and delivery acknowledgement.

    Returns False when all retry attempts are exhausted.
    """
    max_retries = kafka_publish_max_retries()
    backoff = kafka_publish_retry_backoff_sec()
    delivery_timeout = kafka_publish_delivery_timeout_sec()
    total_attempts = max_retries + 1
    last_error: str | None = None

    for attempt in range(1, total_attempts + 1):
        ok, err = _publish_single_attempt(
            envelope,
            topic=topic,
            delivery_timeout_sec=delivery_timeout,
        )
        if ok:
            if attempt > 1:
                log.info(
                    "kafka.publish_recovered",
                    topic=topic,
                    pipeline_id=envelope.pipeline_id,
                    subscription_id=envelope.subscription_id,
                    attempt=attempt,
                )
            return True

        last_error = err or "unknown_publish_error"
        if attempt < total_attempts:
            delay = backoff * (2 ** (attempt - 1))
            log.warning(
                "kafka.publish_retry",
                topic=topic,
                pipeline_id=envelope.pipeline_id,
                subscription_id=envelope.subscription_id,
                attempt=attempt,
                max_attempts=total_attempts,
                error=last_error[:300],
                retry_in_sec=delay,
            )
            time.sleep(delay)

    log.error(
        "kafka.publish_exhausted",
        topic=topic,
        pipeline_id=envelope.pipeline_id,
        subscription_id=envelope.subscription_id,
        attempts=total_attempts,
        error=(last_error or "unknown")[:300],
    )
    return False


def publish_bytes_safe(*, topic: str, key: bytes, value: bytes) -> bool:
    """Publish raw bytes to Kafka with delivery acknowledgement and retries."""
    if not kafka_enabled():
        return False

    max_retries = kafka_publish_max_retries()
    backoff = kafka_publish_retry_backoff_sec()
    delivery_timeout = kafka_publish_delivery_timeout_sec()
    total_attempts = max_retries + 1
    last_error: str | None = None

    for attempt in range(1, total_attempts + 1):
        delivery_error: dict[str, str] = {}
        delivered = threading.Event()

        def on_delivery(err, msg) -> None:
            if err is not None:
                delivery_error["error"] = str(err)
            delivered.set()

        try:
            producer = get_producer()
            producer.produce(topic=topic, key=key, value=value, on_delivery=on_delivery)
            producer.poll(0)
            if not _wait_for_delivery(producer, delivered, timeout_sec=delivery_timeout):
                last_error = "delivery_timeout"
            elif delivery_error:
                last_error = delivery_error["error"]
            else:
                return True
        except Exception as exc:
            last_error = str(exc)

        if attempt < total_attempts:
            delay = backoff * (2 ** (attempt - 1))
            log.warning(
                "kafka.publish_bytes_retry",
                topic=topic,
                attempt=attempt,
                max_attempts=total_attempts,
                error=(last_error or "unknown")[:300],
                retry_in_sec=delay,
            )
            time.sleep(delay)

    log.error(
        "kafka.publish_bytes_exhausted",
        topic=topic,
        attempts=total_attempts,
        error=(last_error or "unknown")[:300],
    )
    return False


def _is_unknown_topic_error(err) -> bool:
    try:
        from confluent_kafka import KafkaError

        if isinstance(err, KafkaError):
            return err.code() == KafkaError.UNKNOWN_TOPIC_OR_PART
    except Exception:
        pass
    text = str(err)
    return "UNKNOWN_TOPIC_OR_PART" in text or "Unknown topic" in text


def _connect_consumer(service_id: str, topics: list[str], *, group_id: str | None = None):
    """Create and subscribe a Kafka consumer (may raise on broker unavailable)."""
    Consumer, _ = _require_confluent()
    resolved_group = group_id or kafka_consumer_group(service_id)
    max_bytes = kafka_message_max_bytes()
    consumer = Consumer(
        {
            **_base_config(),
            "group.id": resolved_group,
            "client.id": f"{kafka_client_id()}.{service_id}",
            "auto.offset.reset": kafka_auto_offset_reset(),
            "enable.auto.commit": False,
            "session.timeout.ms": kafka_session_timeout_ms(),
            "max.poll.interval.ms": 900_000,
            "fetch.max.bytes": max_bytes * 2,
            "max.partition.fetch.bytes": max_bytes,
        }
    )
    consumer.subscribe(topics)
    return consumer, resolved_group


def start_consumer_loop(
    *,
    service_id: str,
    topics: list[str],
    handler: Callable[[JobEnvelope, str], None],
    stop_event: threading.Event | None = None,
    consumer_group: str | None = None,
) -> threading.Thread | None:
    """Start a daemon consumer thread with connection retry (non-blocking for uvicorn)."""
    if not kafka_enabled():
        log.info("kafka.consumer_skipped", service_id=service_id, reason="kafka_disabled")
        return None

    stop = stop_event or _shutdown

    def _run() -> None:
        delay = kafka_connect_retry_delay_sec()
        max_delay = kafka_connect_retry_max_delay_sec()
        attempt = 0
        consumer = None
        group_id = consumer_group or kafka_consumer_group(service_id)

        while not stop.is_set() and consumer is None:
            try:
                consumer, group_id = _connect_consumer(service_id, topics, group_id=group_id)
                log.info(
                    "kafka.consumer_started",
                    service_id=service_id,
                    topics=topics,
                    group_id=group_id,
                )
            except Exception as exc:
                attempt += 1
                log.warning(
                    "kafka.consumer_connect_retry",
                    service_id=service_id,
                    attempt=attempt,
                    error=str(exc),
                    retry_in_sec=delay,
                )
                if stop.wait(delay):
                    return
                delay = min(delay * 1.5, max_delay)

        if consumer is None:
            return

        try:
            while not stop.is_set():
                try:
                    msg = consumer.poll(kafka_poll_timeout_sec())
                except Exception as exc:
                    log.warning("kafka.consumer_poll_error", service_id=service_id, error=str(exc))
                    if stop.wait(delay):
                        break
                    continue
                if msg is None:
                    continue
                if msg.error():
                    err = msg.error()
                    if _is_unknown_topic_error(err):
                        log.warning(
                            "kafka.consumer_unknown_topic",
                            service_id=service_id,
                            topics=topics,
                            error=str(err),
                        )
                        try:
                            consumer.close()
                        except Exception:
                            pass
                        consumer = None
                        from app.messaging.topic_provision import ensure_topics_provisioned

                        ensure_topics_provisioned()
                        if stop.wait(delay):
                            break
                        continue
                    log.warning("kafka.consumer_error", error=str(err))
                    continue
                try:
                    topic_name = msg.topic()
                    envelope = deserialize_envelope(msg.value(), topic=topic_name)
                    handler(envelope, topic_name)
                    consumer.commit(asynchronous=False)
                except Exception:
                    log.exception(
                        "kafka.handler_failed",
                        service_id=service_id,
                        topic=msg.topic(),
                        hint="Offset not committed; message will be redelivered.",
                    )
        finally:
            try:
                consumer.close()
            except Exception:
                log.exception("kafka.consumer_close_failed", service_id=service_id)
            log.info("kafka.consumer_stopped", service_id=service_id)

    thread = threading.Thread(
        target=_run,
        name=f"kafka-{service_id}",
        daemon=True,
    )
    thread.start()
    _consumer_threads.append(thread)
    return thread


def start_bytes_consumer_loop(
    *,
    service_id: str,
    topics: list[str],
    handler: Callable[[bytes, str], None],
    stop_event: threading.Event | None = None,
) -> threading.Thread | None:
    """Consumer loop for raw byte handlers (data pipeline)."""
    if not kafka_enabled():
        return None

    stop = stop_event or _shutdown

    def _run() -> None:
        delay = kafka_connect_retry_delay_sec()
        max_delay = kafka_connect_retry_max_delay_sec()
        consumer = None

        while not stop.is_set():
            if consumer is None:
                try:
                    consumer, group_id = _connect_consumer(service_id, topics)
                    log.info(
                        "kafka.bytes_consumer_started",
                        service_id=service_id,
                        topics=topics,
                        group_id=group_id,
                    )
                except Exception as exc:
                    log.warning(
                        "kafka.bytes_consumer_connect_retry",
                        service_id=service_id,
                        error=str(exc),
                        retry_in_sec=delay,
                    )
                    from app.messaging.topic_provision import ensure_topics_provisioned

                    ensure_topics_provisioned()
                    if stop.wait(delay):
                        return
                    delay = min(delay * 1.5, max_delay)
                    continue

            try:
                msg = consumer.poll(kafka_poll_timeout_sec())
            except Exception as exc:
                log.warning("kafka.consumer_poll_error", service_id=service_id, error=str(exc))
                if stop.wait(delay):
                    break
                continue

            if msg is None:
                continue
            if msg.error():
                err = msg.error()
                if _is_unknown_topic_error(err):
                    try:
                        consumer.close()
                    except Exception:
                        pass
                    consumer = None
                    from app.messaging.topic_provision import ensure_topics_provisioned

                    ensure_topics_provisioned()
                    if stop.wait(delay):
                        break
                    continue
                log.warning("kafka.consumer_error", error=str(err))
                continue

            try:
                handler(msg.value(), msg.topic())
                consumer.commit(asynchronous=False)
            except Exception:
                log.exception(
                    "kafka.bytes_handler_failed",
                    service_id=service_id,
                    topic=msg.topic(),
                    hint="Offset not committed; message will be redelivered.",
                )

        if consumer is not None:
            try:
                consumer.close()
            except Exception:
                pass

    thread = threading.Thread(target=_run, name=f"kafka-bytes-{service_id}", daemon=True)
    thread.start()
    _consumer_threads.append(thread)
    return thread


def shutdown_consumers() -> None:
    _shutdown.set()
    flush_producer()


atexit.register(shutdown_consumers)
