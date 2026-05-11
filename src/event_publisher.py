"""
event_publisher.py

Publishes StreamStarted domain events to Azure Service Bus for the
livestream platform. Fire-and-forget: never raises exceptions.

Uses tenacity for retry with exponential backoff and pybreaker for
circuit breaker protection.

Trace context propagation:
    When this function is invoked inside an Azure Functions worker that has
    Azure Monitor OpenTelemetry configured (see telemetry.py), there is an
    active span on the current execution. We extract its W3C trace_id /
    span_id and use them in two places so the downstream consumer
    (stream-title-service) can adopt the same trace_id:

      1) the body's traceId/spanId fields (legacy custom contract); and
      2) the Service Bus message's application_properties["traceparent"],
         which Azure Functions' .NET isolated SB binding reads to set the
         operation parent on the consumer side.

    Without (2), the consumer creates a brand-new operation_Id on receive
    and the cross-app App Insights correlation breaks at this hop.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import pybreaker
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from opentelemetry import trace as _otel_trace
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Circuit breaker: open after 3 consecutive failures, half-open after 60s
_circuit_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)

# Retry policy: 3 attempts, exponential backoff, max 30s wait
RETRY_MAX_ATTEMPTS = 3
RETRY_MAX_WAIT_SECONDS = 30


def _current_trace_ids() -> tuple[str, str, str | None]:
    """
    Return (trace_id_hex, span_id_hex, traceparent) for the currently active
    OpenTelemetry span. If there is no valid active span (e.g. running offline
    or in a unit test without instrumentation), generate fresh random IDs and
    return None for traceparent so the caller can omit application_properties.

    trace_id_hex: 32 lowercase hex chars
    span_id_hex:  16 lowercase hex chars
    traceparent:  W3C "00-{trace_id}-{span_id}-{flags}" or None
    """
    span = _otel_trace.get_current_span()
    ctx = span.get_span_context() if span is not None else None
    if ctx is not None and ctx.is_valid:
        trace_id_hex = format(ctx.trace_id, "032x")
        span_id_hex = format(ctx.span_id, "016x")
        flags = "01" if ctx.trace_flags.sampled else "00"
        traceparent = f"00-{trace_id_hex}-{span_id_hex}-{flags}"
        return trace_id_hex, span_id_hex, traceparent

    return uuid.uuid4().hex, uuid.uuid4().hex[:16], None


def build_stream_started_event(location: str, title: str | None = None) -> str:
    """
    Build a StreamStarted event JSON string matching the platform event contract.

    When an OpenTelemetry span is active, the body's traceId/spanId reflect that
    span so downstream consumers can correlate against the same operation. When
    no span is active, fresh random IDs are used (preserves prior behavior).
    """
    data: dict[str, str] = {}
    if title is not None:
        data["title"] = title

    trace_id_hex, span_id_hex, _ = _current_trace_ids()

    event = {
        "eventType": "StreamStarted",
        "source": "automated-obs-trigger",
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "location": location,
        "traceId": trace_id_hex,
        "spanId": span_id_hex,
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
    # Match azure-servicebus's expected type for ServiceBusMessage.application_properties.
    # dict is invariant in mypy, so a narrower dict[str, str] won't satisfy it even though
    # every concrete value here is a string.
    application_properties: dict[str | bytes, int | float | bytes | bool | str | UUID] = {}
    _, _, traceparent = _current_trace_ids()
    if traceparent is not None:
        application_properties["traceparent"] = traceparent
        # Diagnostic-Id is the legacy header still respected by some Azure SDKs;
        # set it to the same value so older receivers correlate too.
        application_properties["Diagnostic-Id"] = traceparent

    message = ServiceBusMessage(
        event_json,
        subject="StreamStarted",
        application_properties=application_properties or None,
    )

    with ServiceBusClient.from_connection_string(connection_str) as sb_client:
        with sb_client.get_topic_sender(topic_name) as sender:
            sender.send_messages(message)


def publish_stream_started(
    connection_str: str,
    topic_name: str,
    location: str,
    title: str | None = None,
) -> None:
    """
    Build and publish a StreamStarted event. Fire-and-forget: catches ALL
    exceptions, logs them, but never raises.
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
