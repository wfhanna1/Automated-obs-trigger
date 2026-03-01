"""
tests/unit/test_obs_websocket.py

Unit tests for src/obs_websocket.py

All external dependencies (obsws_python, time) are mocked.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from unittest.mock import MagicMock, patch, call
import pytest

from obs_websocket import (
    _connect,
    start_action,
    stop_action,
    WS_MAX_RETRIES,
    WS_RETRY_INTERVAL,
)


# ---------------------------------------------------------------------------
# _connect tests
# ---------------------------------------------------------------------------

class TestConnect:

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_returns_client_on_first_successful_attempt(
        self, mock_req_client, mock_sleep
    ):
        mock_client = MagicMock()
        mock_req_client.return_value = mock_client

        result = _connect(12345, "password")

        assert result is mock_client
        mock_sleep.assert_not_called()

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_connects_to_localhost_on_given_port(self, mock_req_client, mock_sleep):
        mock_req_client.return_value = MagicMock()

        _connect(9999, "password")

        _, kwargs = mock_req_client.call_args
        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 9999

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_passes_password_to_client(self, mock_req_client, mock_sleep):
        mock_req_client.return_value = MagicMock()

        _connect(12345, "secret123")

        _, kwargs = mock_req_client.call_args
        assert kwargs["password"] == "secret123"

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_retries_on_failure_and_succeeds(self, mock_req_client, mock_sleep):
        mock_client = MagicMock()
        mock_req_client.side_effect = [Exception("not ready"), mock_client]

        result = _connect(12345, "password")

        assert result is mock_client
        assert mock_req_client.call_count == 2
        mock_sleep.assert_called_once_with(WS_RETRY_INTERVAL)

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_raises_runtime_error_after_all_retries_exhausted(
        self, mock_req_client, mock_sleep
    ):
        mock_req_client.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError, match="Could not connect to OBS WebSocket"):
            _connect(12345, "password")

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_retries_exactly_ws_max_retries_times(self, mock_req_client, mock_sleep):
        mock_req_client.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError):
            _connect(12345, "password")

        assert mock_req_client.call_count == WS_MAX_RETRIES

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_sleeps_between_retries(self, mock_req_client, mock_sleep):
        mock_req_client.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError):
            _connect(12345, "password")

        # Sleep should be called WS_MAX_RETRIES - 1 times (not after last attempt)
        assert mock_sleep.call_count == WS_MAX_RETRIES - 1

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_sleeps_with_correct_interval(self, mock_req_client, mock_sleep):
        mock_req_client.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError):
            _connect(12345, "password")

        for sleep_call in mock_sleep.call_args_list:
            assert sleep_call == call(WS_RETRY_INTERVAL)

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_no_sleep_after_final_failed_attempt(self, mock_req_client, mock_sleep):
        mock_req_client.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError):
            _connect(12345, "password")

        assert mock_sleep.call_count == WS_MAX_RETRIES - 1

    @patch("obs_websocket.time.sleep")
    @patch("obs_websocket.obs.ReqClient")
    def test_error_message_includes_port(self, mock_req_client, mock_sleep):
        mock_req_client.side_effect = Exception("timeout")

        with pytest.raises(RuntimeError, match="localhost:8765"):
            _connect(8765, "password")


# ---------------------------------------------------------------------------
# start_action tests
# ---------------------------------------------------------------------------

class TestStartAction:

    @patch("obs_websocket._connect")
    def test_start_recording_calls_start_record(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(12345, "password", "recording")

        mock_client.start_record.assert_called_once()

    @patch("obs_websocket._connect")
    def test_start_streaming_calls_start_stream(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(12345, "password", "streaming")

        mock_client.start_stream.assert_called_once()

    @patch("obs_websocket._connect")
    def test_unknown_action_raises_value_error(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        with pytest.raises(ValueError, match="Unknown action"):
            start_action(12345, "password", "broadcasting")

    @patch("obs_websocket._connect")
    def test_client_disconnected_after_start_recording(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(12345, "password", "recording")

        mock_client.disconnect.assert_called_once()

    @patch("obs_websocket._connect")
    def test_client_disconnected_after_start_streaming(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(12345, "password", "streaming")

        mock_client.disconnect.assert_called_once()

    @patch("obs_websocket._connect")
    def test_client_disconnected_even_when_unknown_action_raises(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        with pytest.raises(ValueError):
            start_action(12345, "password", "unknown")

        mock_client.disconnect.assert_called_once()

    @patch("obs_websocket._connect")
    def test_start_recording_does_not_call_start_stream(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(12345, "password", "recording")

        mock_client.start_stream.assert_not_called()

    @patch("obs_websocket._connect")
    def test_start_streaming_does_not_call_start_record(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(12345, "password", "streaming")

        mock_client.start_record.assert_not_called()

    @patch("obs_websocket._connect")
    def test_connect_called_with_correct_port_and_password(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        start_action(7777, "mysecret", "recording")

        mock_connect.assert_called_once_with(7777, "mysecret")


# ---------------------------------------------------------------------------
# stop_action tests
# ---------------------------------------------------------------------------

class TestStopAction:

    @patch("obs_websocket._connect")
    def test_stop_recording_calls_stop_record(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(12345, "password", "recording")

        mock_client.stop_record.assert_called_once()

    @patch("obs_websocket._connect")
    def test_stop_streaming_calls_stop_stream(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(12345, "password", "streaming")

        mock_client.stop_stream.assert_called_once()

    @patch("obs_websocket._connect")
    def test_unknown_action_raises_value_error(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        with pytest.raises(ValueError, match="Unknown action"):
            stop_action(12345, "password", "broadcasting")

    @patch("obs_websocket._connect")
    def test_client_disconnected_after_stop_recording(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(12345, "password", "recording")

        mock_client.disconnect.assert_called_once()

    @patch("obs_websocket._connect")
    def test_client_disconnected_after_stop_streaming(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(12345, "password", "streaming")

        mock_client.disconnect.assert_called_once()

    @patch("obs_websocket._connect")
    def test_client_disconnected_even_when_unknown_action_raises(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        with pytest.raises(ValueError):
            stop_action(12345, "password", "unknown")

        mock_client.disconnect.assert_called_once()

    @patch("obs_websocket._connect")
    def test_stop_recording_does_not_call_stop_stream(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(12345, "password", "recording")

        mock_client.stop_stream.assert_not_called()

    @patch("obs_websocket._connect")
    def test_stop_streaming_does_not_call_stop_record(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(12345, "password", "streaming")

        mock_client.stop_record.assert_not_called()

    @patch("obs_websocket._connect")
    def test_connect_called_with_correct_port_and_password(self, mock_connect):
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        stop_action(8888, "mypass", "streaming")

        mock_connect.assert_called_once_with(8888, "mypass")
