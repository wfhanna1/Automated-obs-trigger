"""
tests/unit/test_load_schedule_function.py

Unit tests for the load_schedule_function (HTTP trigger) and its helper
functions (_get_env, _fetch_text, _load_servers_config, _get_kv_secret)
in function_app.py.

All external dependencies (requests, yaml, Azure SDK) are mocked.
"""

import json
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz

# Ensure the project root is on the path so function_app can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ---------------------------------------------------------------------------
# Tests: _get_env helper
# ---------------------------------------------------------------------------

class TestGetEnv:

    def test_returns_value_when_set(self):
        from function_app import _get_env

        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            assert _get_env("MY_VAR") == "hello"

    def test_raises_runtime_error_when_missing(self):
        from function_app import _get_env

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="MY_VAR"):
                _get_env("MY_VAR")

    def test_raises_runtime_error_when_empty_string(self):
        from function_app import _get_env

        with patch.dict(os.environ, {"MY_VAR": ""}):
            with pytest.raises(RuntimeError, match="MY_VAR"):
                _get_env("MY_VAR")


# ---------------------------------------------------------------------------
# Tests: _fetch_text helper
# ---------------------------------------------------------------------------

class TestFetchText:

    @patch("function_app.requests.get")
    def test_returns_text_on_success(self, mock_get):
        from function_app import _fetch_text

        mock_resp = MagicMock()
        mock_resp.text = "csv content here"
        mock_get.return_value = mock_resp

        result = _fetch_text("https://example.com/file.csv")

        assert result == "csv content here"
        mock_get.assert_called_once_with("https://example.com/file.csv", timeout=15)

    @patch("function_app.requests.get")
    def test_raises_on_http_error(self, mock_get):
        from function_app import _fetch_text

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_resp

        with pytest.raises(Exception, match="404"):
            _fetch_text("https://example.com/missing.csv")


# ---------------------------------------------------------------------------
# Tests: _load_servers_config helper
# ---------------------------------------------------------------------------

class TestLoadServersConfig:

    @patch("function_app._fetch_text")
    def test_returns_servers_dict(self, mock_fetch):
        from function_app import _load_servers_config

        mock_fetch.return_value = (
            "servers:\n"
            "  win-server-1:\n"
            "    name: Test\n"
        )

        result = _load_servers_config("https://example.com/servers.yaml")

        assert "win-server-1" in result
        assert result["win-server-1"]["name"] == "Test"

    @patch("function_app._fetch_text")
    def test_returns_empty_dict_when_servers_key_missing(self, mock_fetch):
        from function_app import _load_servers_config

        mock_fetch.return_value = "other_key: value\n"

        result = _load_servers_config("https://example.com/servers.yaml")

        assert result == {}

    @patch("function_app._fetch_text")
    def test_propagates_fetch_errors(self, mock_fetch):
        from function_app import _load_servers_config

        mock_fetch.side_effect = Exception("network error")

        with pytest.raises(Exception, match="network error"):
            _load_servers_config("https://example.com/servers.yaml")


# ---------------------------------------------------------------------------
# Tests: _get_kv_secret helper
# ---------------------------------------------------------------------------

class TestGetKvSecret:

    @patch("function_app.SecretClient")
    @patch("function_app.DefaultAzureCredential")
    def test_returns_secret_value(self, mock_cred_class, mock_client_class):
        from function_app import _get_kv_secret

        mock_secret = MagicMock()
        mock_secret.value = "my-secret-value"
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret
        mock_client_class.return_value = mock_client

        result = _get_kv_secret("https://vault.azure.net/", "secret-name")

        assert result == "my-secret-value"
        mock_client.get_secret.assert_called_once_with("secret-name")

    @patch("function_app.SecretClient")
    @patch("function_app.DefaultAzureCredential")
    def test_raises_runtime_error_when_value_is_none(self, mock_cred_class, mock_client_class):
        from function_app import _get_kv_secret

        mock_secret = MagicMock()
        mock_secret.value = None
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError, match="has no value"):
            _get_kv_secret("https://vault.azure.net/", "empty-secret")


# ---------------------------------------------------------------------------
# Helpers for load_schedule_function tests
# ---------------------------------------------------------------------------

def _make_http_request(body: bytes = b"") -> MagicMock:
    """Return a mock HttpRequest."""
    req = MagicMock()
    req.get_body.return_value = body
    return req


# ---------------------------------------------------------------------------
# Tests: load_schedule_function — env var failures
# ---------------------------------------------------------------------------

class TestLoadScheduleFunctionEnvErrors:

    @patch("function_app._get_env")
    def test_missing_env_var_returns_500(self, mock_get_env):
        from function_app import load_schedule_function

        mock_get_env.side_effect = RuntimeError("Required environment variable 'GITHUB_RAW_CSV_URL' is not set.")

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 500
        assert "GITHUB_RAW_CSV_URL" in resp.get_body().decode()


# ---------------------------------------------------------------------------
# Tests: load_schedule_function — fetch failures
# ---------------------------------------------------------------------------

class TestLoadScheduleFunctionFetchErrors:

    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_csv_fetch_failure_returns_502(self, mock_get_env, mock_fetch, mock_load_servers):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.side_effect = Exception("Connection timeout")

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 502
        assert "Failed to fetch schedule CSV" in resp.get_body().decode()

    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_servers_config_fetch_failure_returns_502(self, mock_get_env, mock_fetch, mock_load_servers):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.side_effect = Exception("YAML parse error")

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 502
        assert "Failed to fetch/parse servers.yaml" in resp.get_body().decode()


# ---------------------------------------------------------------------------
# Tests: load_schedule_function — validation errors
# ---------------------------------------------------------------------------

class TestLoadScheduleFunctionValidationErrors:

    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_csv_validation_error_returns_400(self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.side_effect = ValueError("CSV is missing required columns")

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 400
        assert "Schedule validation error" in resp.get_body().decode()


# ---------------------------------------------------------------------------
# Tests: load_schedule_function — empty schedule
# ---------------------------------------------------------------------------

class TestLoadScheduleFunctionEmptySchedule:

    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_no_entries_returns_200_with_info(self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = []

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 200
        assert "No future sessions" in resp.get_body().decode()


# ---------------------------------------------------------------------------
# Tests: load_schedule_function — successful enqueue
# ---------------------------------------------------------------------------

class TestLoadScheduleFunctionEnqueue:

    def _make_entry(self, server_id="win-server-1", action="recording"):
        """Create a mock ScheduleEntry."""
        from schedule_loader import ScheduleEntry
        start = datetime(2099, 1, 15, 14, 0, tzinfo=pytz.utc)
        stop = datetime(2099, 1, 15, 15, 0, tzinfo=pytz.utc)
        return ScheduleEntry(server_id=server_id, action=action, start_dt=start, stop_dt=stop)

    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_successful_enqueue_returns_200(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule, mock_sb_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = [self._make_entry()]

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 200
        assert "Enqueued 2 message(s)" in resp.get_body().decode()

    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_each_entry_produces_start_and_stop_messages(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule, mock_sb_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = [self._make_entry()]

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        load_schedule_function(_make_http_request())

        assert mock_sender.send_messages.call_count == 2

    @patch("function_app.ServiceBusMessage")
    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_message_payload_contains_correct_json_keys(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule,
        mock_sb_class, mock_sb_message_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = [self._make_entry()]

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        load_schedule_function(_make_http_request())

        # First call should be "start", second should be "stop"
        first_payload = json.loads(mock_sb_message_class.call_args_list[0][0][0])
        second_payload = json.loads(mock_sb_message_class.call_args_list[1][0][0])

        assert first_payload["command"] == "start"
        assert first_payload["server_id"] == "win-server-1"
        assert first_payload["action"] == "recording"

        assert second_payload["command"] == "stop"
        assert second_payload["server_id"] == "win-server-1"
        assert second_payload["action"] == "recording"

    @patch("function_app.ServiceBusMessage")
    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_scheduled_time_has_tzinfo_stripped(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule,
        mock_sb_class, mock_sb_message_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = [self._make_entry()]

        mock_msg_instance = MagicMock()
        mock_sb_message_class.return_value = mock_msg_instance

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        load_schedule_function(_make_http_request())

        # The scheduled_enqueue_time_utc should have been set to a naive datetime
        set_time = mock_msg_instance.scheduled_enqueue_time_utc
        assert set_time.tzinfo is None

    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_partial_enqueue_failure_returns_207(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule, mock_sb_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = [self._make_entry()]

        mock_sender = MagicMock()
        # First send succeeds, second fails
        mock_sender.send_messages.side_effect = [None, Exception("Service Bus error")]
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 207
        assert "Enqueued 1 message(s)" in resp.get_body().decode()
        assert "Errors" in resp.get_body().decode()

    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_multiple_entries_enqueue_correct_count(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule, mock_sb_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}, "mac-server-1": {}}
        mock_load_schedule.return_value = [
            self._make_entry("win-server-1", "recording"),
            self._make_entry("mac-server-1", "streaming"),
        ]

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 200
        # 2 entries * 2 messages each = 4
        assert "Enqueued 4 message(s)" in resp.get_body().decode()
        assert mock_sender.send_messages.call_count == 4

    @patch("function_app.ServiceBusClient")
    @patch("function_app.load_schedule")
    @patch("function_app._load_servers_config")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_queue_name_is_obs_jobs(
        self, mock_get_env, mock_fetch, mock_load_servers, mock_load_schedule, mock_sb_class
    ):
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = "csv data"
        mock_load_servers.return_value = {"win-server-1": {}}
        mock_load_schedule.return_value = [self._make_entry()]

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        load_schedule_function(_make_http_request())

        mock_sb_client.get_queue_sender.assert_called_once_with("obs-jobs")
