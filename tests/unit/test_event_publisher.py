"""
tests/unit/test_event_publisher.py

Unit tests for src/event_publisher.py :: build_stream_started_event, publish_stream_started
"""

import json
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ---------------------------------------------------------------------------
# Tests: build_stream_started_event
# ---------------------------------------------------------------------------

class TestBuildStreamStartedEvent:

    def test_returns_valid_json_string(self):
        from event_publisher import build_stream_started_event

        result = build_stream_started_event("st. mary and st. joseph")
        parsed = json.loads(result)

        assert isinstance(parsed, dict)

    def test_event_type_is_stream_started(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert parsed["eventType"] == "StreamStarted"

    def test_source_is_automated_obs_trigger(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert parsed["source"] == "automated-obs-trigger"

    def test_location_is_set_correctly(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. anthony chapel"))

        assert parsed["location"] == "st. anthony chapel"

    def test_timestamp_is_iso8601_utc(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert parsed["timestamp"].endswith("Z") or "+00:00" in parsed["timestamp"]

    def test_data_contains_title_when_provided(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event(
            "st. mary and st. joseph", title="Palm Sunday - Divine Liturgy"
        ))

        assert parsed["data"]["title"] == "Palm Sunday - Divine Liturgy"

    def test_data_is_empty_dict_when_no_title(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. anthony chapel"))

        assert parsed["data"] == {}

    def test_data_is_empty_dict_when_title_is_none(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph", title=None))

        assert parsed["data"] == {}

    def test_has_trace_id_field(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert "traceId" in parsed
        assert isinstance(parsed["traceId"], str)
        assert len(parsed["traceId"]) > 0

    def test_has_span_id_field(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert "spanId" in parsed
        assert isinstance(parsed["spanId"], str)
        assert len(parsed["spanId"]) > 0

    def test_parent_span_id_is_null(self):
        from event_publisher import build_stream_started_event

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert parsed["parentSpanId"] is None


# ---------------------------------------------------------------------------
# Tests: publish_stream_started — fire-and-forget behavior
# ---------------------------------------------------------------------------

class TestPublishStreamStarted:

    @patch("event_publisher.ServiceBusClient")
    def test_publish_does_not_raise_on_success(self, mock_sb_class):
        from event_publisher import publish_stream_started

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        # Must not raise
        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph", title="Test")

    @patch("event_publisher.ServiceBusClient")
    def test_publish_sends_message_to_topic(self, mock_sb_class):
        from event_publisher import publish_stream_started

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph")

        mock_sender.send_messages.assert_called_once()

    @patch("event_publisher.ServiceBusClient")
    def test_publish_uses_correct_topic_name(self, mock_sb_class):
        from event_publisher import publish_stream_started

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        publish_stream_started("conn-str", "my-topic", "st. mary and st. joseph")

        mock_sb_client.get_topic_sender.assert_called_once_with("my-topic")

    @patch("event_publisher.ServiceBusClient")
    def test_publish_swallows_service_bus_exception(self, mock_sb_class):
        """Fire-and-forget: exceptions from Service Bus must not propagate."""
        from event_publisher import publish_stream_started

        mock_sb_class.from_connection_string.side_effect = Exception("Service Bus unavailable")

        # Must not raise
        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph")

    @patch("event_publisher.ServiceBusClient")
    def test_publish_swallows_send_exception(self, mock_sb_class):
        """Fire-and-forget: send failure must not propagate."""
        from event_publisher import publish_stream_started

        mock_sender = MagicMock()
        mock_sender.send_messages.side_effect = Exception("Network error")
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        # Must not raise
        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph")

    @patch("event_publisher.ServiceBusClient")
    def test_publish_swallows_circuit_breaker_open(self, mock_sb_class):
        """Fire-and-forget: circuit breaker open must not propagate."""
        from event_publisher import publish_stream_started
        import pybreaker

        mock_sb_class.from_connection_string.side_effect = pybreaker.CircuitBreakerError(MagicMock())

        # Must not raise
        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph")


# ---------------------------------------------------------------------------
# Tests: W3C trace context propagation
#
# When an OpenTelemetry span is active on the current execution, the publisher
# must (a) put that span's trace_id/span_id in the event body, and (b) set
# application_properties["traceparent"] on the Service Bus message so the
# downstream consumer (stream-title-service) adopts the same trace_id and the
# end-to-end trace stays correlated in App Insights.
#
# Without (b), the consumer's SB receive auto-generates a fresh operation_Id,
# breaking the cross-app trace at this hop. That was observed in production
# on 2026-04-27 — see commit message for the investigation summary.
# ---------------------------------------------------------------------------

class TestTraceContextPropagation:

    def setup_method(self):
        # The module-level pybreaker.CircuitBreaker accumulates failures across
        # tests in this file, so by the time we get here the swallows-* tests
        # may have tripped it open. Reset it so the tests below actually
        # exercise the send path.
        import event_publisher
        event_publisher._circuit_breaker.close()

    @patch("event_publisher._otel_trace.get_current_span")
    def test_body_uses_active_span_ids_when_span_is_valid(self, mock_get_span):
        from event_publisher import build_stream_started_event

        # Synthesize a span whose context reports a deterministic trace/span id
        ctx = MagicMock()
        ctx.is_valid = True
        ctx.trace_id = 0x4BF92F3577B34DA6A3CE929D0E0E4736
        ctx.span_id = 0x00F067AA0BA902B7
        ctx.trace_flags.sampled = True
        span = MagicMock()
        span.get_span_context.return_value = ctx
        mock_get_span.return_value = span

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        assert parsed["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert parsed["spanId"] == "00f067aa0ba902b7"

    @patch("event_publisher._otel_trace.get_current_span")
    def test_body_falls_back_to_uuid_when_no_valid_span(self, mock_get_span):
        from event_publisher import build_stream_started_event

        ctx = MagicMock()
        ctx.is_valid = False
        span = MagicMock()
        span.get_span_context.return_value = ctx
        mock_get_span.return_value = span

        parsed = json.loads(build_stream_started_event("st. mary and st. joseph"))

        # 32 hex chars from uuid4().hex; not zero
        assert len(parsed["traceId"]) == 32
        assert len(parsed["spanId"]) == 16
        assert int(parsed["traceId"], 16) != 0

    @patch("event_publisher.ServiceBusClient")
    @patch("event_publisher._otel_trace.get_current_span")
    def test_send_sets_traceparent_application_property(self, mock_get_span, mock_sb_class):
        from event_publisher import publish_stream_started

        ctx = MagicMock()
        ctx.is_valid = True
        ctx.trace_id = 0x4BF92F3577B34DA6A3CE929D0E0E4736
        ctx.span_id = 0x00F067AA0BA902B7
        ctx.trace_flags.sampled = True
        span = MagicMock()
        span.get_span_context.return_value = ctx
        mock_get_span.return_value = span

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph", title="X")

        # Inspect the ServiceBusMessage that was sent
        sent = mock_sender.send_messages.call_args[0][0]
        assert sent.subject == "StreamStarted"
        assert sent.application_properties == {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "Diagnostic-Id": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        }

    @patch("event_publisher.ServiceBusClient")
    @patch("event_publisher._otel_trace.get_current_span")
    def test_send_omits_traceparent_when_no_valid_span(self, mock_get_span, mock_sb_class):
        from event_publisher import publish_stream_started

        ctx = MagicMock()
        ctx.is_valid = False
        span = MagicMock()
        span.get_span_context.return_value = ctx
        mock_get_span.return_value = span

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph")

        sent = mock_sender.send_messages.call_args[0][0]
        assert sent.subject == "StreamStarted"
        # Falsy / unset — we don't want to put a fabricated traceparent on the wire
        assert not sent.application_properties

    @patch("event_publisher.ServiceBusClient")
    @patch("event_publisher._otel_trace.get_current_span")
    def test_traceparent_flag_reflects_sampled_decision(self, mock_get_span, mock_sb_class):
        from event_publisher import publish_stream_started

        ctx = MagicMock()
        ctx.is_valid = True
        ctx.trace_id = 0x4BF92F3577B34DA6A3CE929D0E0E4736
        ctx.span_id = 0x00F067AA0BA902B7
        ctx.trace_flags.sampled = False  # not-sampled span
        span = MagicMock()
        span.get_span_context.return_value = ctx
        mock_get_span.return_value = span

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_topic_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_topic_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        publish_stream_started("conn-str", "stream-title", "st. mary and st. joseph")

        sent = mock_sender.send_messages.call_args[0][0]
        assert sent.application_properties["traceparent"].endswith("-00")
