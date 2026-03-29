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
