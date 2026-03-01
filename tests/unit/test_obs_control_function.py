"""
tests/unit/test_obs_control_function.py

Unit tests for the obs_control_function in function_app.py, focused on the
Key Vault secret retrieval and base64 decode of the SSH private key.
"""

import base64
import json
import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure the project root is on the path so function_app can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sb_message(body: dict) -> MagicMock:
    """Return a mock ServiceBusMessage whose get_body() returns the JSON body."""
    msg = MagicMock()
    msg.get_body.return_value = json.dumps(body).encode("utf-8")
    return msg


VALID_BODY = {
    "command": "start",
    "server_id": "win-server-1",
    "action": "recording",
}


# ---------------------------------------------------------------------------
# Tests: SSH key base64 decode
# ---------------------------------------------------------------------------

class TestSshKeyBase64Decode:
    """Verify that obs_control_function decodes the base64 SSH key before use."""

    @patch("function_app.kill_obs")
    @patch("function_app.stop_action")
    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_base64_encoded_key_is_decoded_before_launch(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        mock_stop_action,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """launch_obs must receive the raw PEM string, not the base64-encoded blob."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(fake_pem.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
        mock_load_servers.return_value = fake_server_config
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )
        mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
        mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)

        obs_control_function(_make_sb_message(VALID_BODY))

        args = mock_launch_obs.call_args
        actual_key_pem = args[0][3]  # positional: host, port, user, key_pem, ...
        assert actual_key_pem == fake_pem

    @patch("function_app.kill_obs")
    @patch("function_app.stop_action")
    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_raw_pem_stored_in_key_vault_raises(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        mock_stop_action,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """If the Key Vault secret is raw PEM (not base64), decoding raises before
        reaching paramiko — surfacing the misconfiguration early."""
        from function_app import obs_control_function

        # Store raw PEM — not base64 encoded — simulating the original bug.
        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
        mock_load_servers.return_value = fake_server_config
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            fake_pem if "ssh-key" in name else "obs-password"
        )

        with pytest.raises(Exception):
            obs_control_function(_make_sb_message(VALID_BODY))

        mock_launch_obs.assert_not_called()

    @patch("function_app.kill_obs")
    @patch("function_app.stop_action")
    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_decoded_key_is_passed_to_obs_tunnel(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        mock_stop_action,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """obs_tunnel must also receive the decoded PEM, not the base64 blob."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(fake_pem.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
        mock_load_servers.return_value = fake_server_config
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )
        mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
        mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)

        obs_control_function(_make_sb_message(VALID_BODY))

        tunnel_call_args = mock_obs_tunnel.call_args
        actual_key_pem = tunnel_call_args[0][3]  # host, ssh_port, user, key_pem, ws_port
        assert actual_key_pem == fake_pem

    @patch("function_app.kill_obs")
    @patch("function_app.stop_action")
    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_server_id_underscore_converted_to_hyphen_for_kv_lookup(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        mock_stop_action,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """server_id underscores must be replaced with hyphens when building the
        Key Vault secret name (e.g. 'win_server_1' -> 'ssh-key-win-server-1')."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(fake_pem.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"

        # Register the server under an underscore ID in the servers config.
        servers_with_underscore = {
            "win_server_1": fake_server_config["win-server-1"]
        }
        mock_load_servers.return_value = servers_with_underscore
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )
        mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
        mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)

        body = {**VALID_BODY, "server_id": "win_server_1"}
        obs_control_function(_make_sb_message(body))

        called_names = [c[0][1] for c in mock_get_kv_secret.call_args_list]
        assert "ssh-key-win-server-1" in called_names
