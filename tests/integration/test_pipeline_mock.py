"""
tests/integration/test_pipeline_mock.py

CI-runnable integration tests that exercise real module interactions
with only Azure SDK dependencies mocked. These tests verify the seams
between modules without requiring live Azure infrastructure.
"""

import base64
import json
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CSV = (
    "server_id,date,start_time,stop_time,action,timezone\n"
    "win-server-1,2099-01-15,09:00,10:00,recording,America/New_York\n"
)

SERVERS_YAML = """\
servers:
  win-server-1:
    name: "Windows Server 1"
    platform: windows
    host: "192.0.2.1"
    ssh:
      user: admin
      port: 22
    obs:
      path: 'C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe'
      websocket_port: 4455
"""

FAKE_PEM = """\
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4PAtEsHAkiDqAPpRN7yLarKAhSm
wfX/TBpJDTMHFe1Hk4KQMH1mvRRBOWMBUFAKEFAKEFAKEFAKEFAKEFAKEFAKEF
-----END RSA PRIVATE KEY-----
"""


def _make_http_request() -> MagicMock:
    req = MagicMock()
    req.get_body.return_value = b""
    return req


# ---------------------------------------------------------------------------
# Integration: load_schedule_function with real CSV parsing
# ---------------------------------------------------------------------------

class TestLoadSchedulePipeline:
    """Exercise load_schedule_function with real schedule_loader parsing,
    mocking only the network (fetch) and Azure (Service Bus) layers."""

    @patch("function_app.ServiceBusClient")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_real_csv_parsing_and_enqueue(self, mock_get_env, mock_fetch, mock_sb_class):
        """End-to-end: real CSV -> real schedule_loader -> mocked Service Bus."""
        from function_app import load_schedule_function

        mock_get_env.return_value = "https://example.com"
        # First call fetches CSV, _load_servers_config calls _fetch_text again
        mock_fetch.side_effect = [VALID_CSV, SERVERS_YAML]

        mock_sender = MagicMock()
        mock_sb_client = MagicMock()
        mock_sb_client.get_queue_sender.return_value.__enter__ = MagicMock(return_value=mock_sender)
        mock_sb_client.get_queue_sender.return_value.__exit__ = MagicMock(return_value=False)
        mock_sb_class.from_connection_string.return_value.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_class.from_connection_string.return_value.__exit__ = MagicMock(return_value=False)

        resp = load_schedule_function(_make_http_request())

        assert resp.status_code == 200
        assert "Enqueued 2 message(s)" in resp.get_body().decode()
        assert mock_sender.send_messages.call_count == 2


# ---------------------------------------------------------------------------
# Integration: obs_control_function start path
# ---------------------------------------------------------------------------

class TestObsControlStartPipeline:
    """Exercise obs_control_function start path with real config parsing,
    mocking SSH/WebSocket and Key Vault."""

    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_start_with_real_yaml_config(
        self, mock_get_env, mock_fetch, mock_get_kv_secret,
        mock_launch_obs, mock_obs_tunnel, mock_start_action
    ):
        """Start path: real YAML config parsing, mocked SSH/WS/KV."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(FAKE_PEM.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = SERVERS_YAML
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )
        mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
        mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)

        msg = MagicMock()
        msg.get_body.return_value = json.dumps({
            "command": "start",
            "server_id": "win-server-1",
            "action": "recording",
        }).encode("utf-8")

        obs_control_function(msg)

        mock_launch_obs.assert_called_once()
        # Verify parsed config was used — host from YAML
        assert mock_launch_obs.call_args[0][0] == "192.0.2.1"


# ---------------------------------------------------------------------------
# Integration: obs_control_function stop path
# ---------------------------------------------------------------------------

class TestObsControlStopPipeline:
    """Exercise obs_control_function stop path with real config parsing."""

    @patch("function_app.kill_obs")
    @patch("function_app.quit_obs_ws")
    @patch("function_app.stop_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._fetch_text")
    @patch("function_app._get_env")
    def test_stop_with_real_yaml_config(
        self, mock_get_env, mock_fetch, mock_get_kv_secret,
        mock_obs_tunnel, mock_stop_action, mock_quit_obs_ws, mock_kill_obs
    ):
        """Stop path: real YAML parsing, mocked SSH/WS/KV."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(FAKE_PEM.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://example.com"
        mock_fetch.return_value = SERVERS_YAML
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )
        mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
        mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)

        msg = MagicMock()
        msg.get_body.return_value = json.dumps({
            "command": "stop",
            "server_id": "win-server-1",
            "action": "recording",
        }).encode("utf-8")

        obs_control_function(msg)

        mock_stop_action.assert_called_once()
        mock_quit_obs_ws.assert_called_once()
        mock_kill_obs.assert_called_once()
        # Verify platform from config
        assert mock_kill_obs.call_args[0][4] == "windows"
