"""
event_publisher.py

Publishes StreamStarted domain events to Azure Service Bus for the
livestream platform. Fire-and-forget: never raises exceptions.

Uses tenacity for retry with exponential backoff and pybreaker for
circuit breaker protection.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import pybreaker
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Circuit breaker: open after 3 consecutive failures, half-open after 60s
_circuit_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)

# Retry policy: 3 attempts, exponential backoff, max 30s wait
RETRY_MAX_ATTEMPTS = 3
RETRY_MAX_WAIT_SECONDS = 30


def build_stream_started_event(location: str, title: str | None = None) -> str:
    """
    Build a StreamStarted event JSON string matching the platform event contract.

    Args:
        location: Logical location of the stream (e.g. "st. mary and st. joseph").
        title:    Optional stream title suffix. Omitted from data if None.

    Returns:
        JSON string conforming to the StreamStarted event schema.
    """
    data: dict[str, str] = {}
    if title is not None:
        data["title"] = title

    event = {
        "eventType": "StreamStarted",
        "source": "automated-obs-trigger",
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "location": location,
        "traceId": uuid.uuid4().hex,
        "spanId": uuid.uuid4().hex[:16],
        "parentSpanId": None,
        "data": data,
    }
    return json.dumps(event)


@retry(
    stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=1, max=RETRY_MAX_WAIT_SECONDS),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
@_circuit_breaker
def _send_event(connection_str: str, topic_name: str, event_json: str) -> None:
    """Send an event message to the Service Bus topic with retry and circuit breaker."""
    with ServiceBusClient.from_connection_string(connection_str) as sb_client:
        with sb_client.get_topic_sender(topic_name) as sender:
            sender.send_messages(ServiceBusMessage(event_json, subject="StreamStarted"))


def publish_stream_started(
    connection_str: str,
    topic_name: str,
    location: str,
    title: str | None = None,
) -> None:
    """
    Build and publish a StreamStarted event. Fire-and-forget: catches ALL
    exceptions, logs them, but never raises.

    Args:
        connection_str: Service Bus connection string.
        topic_name:     Service Bus topic name (e.g. "stream-title").
        location:       Logical location of the stream.
        title:          Optional stream title suffix.
    """
    try:
        event_json = build_stream_started_event(location, title)
        _send_event(connection_str, topic_name, event_json)
        logger.info(
            "Published StreamStarted event for location=%s title=%s",
            location, title,
        )
    except Exception as exc:
        logger.error(
            "Failed to publish StreamStarted event for location=%s: %s",
            location, exc,
        )
