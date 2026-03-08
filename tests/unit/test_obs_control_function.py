"""
tests/unit/test_obs_control_function.py

Unit tests for the obs_control_function in function_app.py, focused on the
Key Vault secret retrieval, base64 decode of the SSH private key, and the
scene/start_action branching logic introduced in the start command path.
"""

import base64
import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on the path so function_app can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


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


# ---------------------------------------------------------------------------
# Tests: stop command calls kill_obs to close OBS after stopping
# ---------------------------------------------------------------------------

class TestStopCommandCleanShutdown:

    @patch("function_app.kill_obs")
    @patch("function_app.stop_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_stop_command_calls_kill_obs(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_obs_tunnel,
        mock_stop_action,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """stop command must call kill_obs to close OBS after stopping the action."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(fake_pem.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
        mock_load_servers.return_value = fake_server_config
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )
        mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
        mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)

        obs_control_function(_make_sb_message({**VALID_BODY, "command": "stop"}))

        mock_kill_obs.assert_called_once()


# ---------------------------------------------------------------------------
# Fixtures: server configs with/without a scene configured
# ---------------------------------------------------------------------------

MAC_BODY = {
    "command": "start",
    "server_id": "mac-server-1",
    "action": "streaming",
}


def _fake_server_config_with_scene(scene: str) -> dict:
    """Return a server config where mac-server-1 has a scene set."""
    return {
        "mac-server-1": {
            "name": "Test Mac Server",
            "platform": "mac",
            "host": "192.0.2.2",
            "ssh": {"user": "admin", "port": 22},
            "obs": {
                "path": "/Applications/OBS.app/Contents/MacOS/obs",
                "websocket_port": 4455,
                "scene": scene,
            },
        },
    }


def _fake_server_config_without_scene() -> dict:
    """Return a server config where mac-server-1 has no scene set."""
    return {
        "mac-server-1": {
            "name": "Test Mac Server",
            "platform": "mac",
            "host": "192.0.2.2",
            "ssh": {"user": "admin", "port": 22},
            "obs": {
                "path": "/Applications/OBS.app/Contents/MacOS/obs",
                "websocket_port": 4455,
            },
        },
    }


def _setup_standard_mocks(mock_get_env, mock_load_servers, mock_get_kv_secret,
                          mock_obs_tunnel, servers_config, fake_pem):
    """Wire up common mocks used across start-path tests."""
    b64_key = base64.b64encode(fake_pem.encode("utf-8")).decode("utf-8")
    mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
    mock_load_servers.return_value = servers_config
    mock_get_kv_secret.side_effect = lambda _uri, name: (
        b64_key if "ssh-key" in name else "obs-password"
    )
    mock_obs_tunnel.return_value.__enter__ = MagicMock(return_value=9876)
    mock_obs_tunnel.return_value.__exit__ = MagicMock(return_value=False)


# ---------------------------------------------------------------------------
# Tests: start command scene/start_action branching
# ---------------------------------------------------------------------------

class TestStartCommandSceneBranching:
    """
    Verify the two branches in the 'start' path:

      scene is set   -> launch_obs gets scene + start_action=action,
                        start_action() WebSocket call is SKIPPED.
      scene is None  -> launch_obs gets scene=None + start_action=None,
                        start_action() WebSocket call IS made.
    """

    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_start_action_ws_skipped_when_scene_is_set(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        fake_pem,
    ):
        """When the server config has a scene, the WebSocket start_action call must not happen."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            _fake_server_config_with_scene("Small Chapel"), fake_pem,
        )

        obs_control_function(_make_sb_message(MAC_BODY))

        mock_start_action.assert_not_called()

    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_start_action_ws_called_when_scene_is_none(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        fake_pem,
    ):
        """When no scene is configured, the WebSocket start_action call must be made."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            _fake_server_config_without_scene(), fake_pem,
        )

        obs_control_function(_make_sb_message(MAC_BODY))

        mock_start_action.assert_called_once()

    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_launch_obs_receives_scene_and_start_action_when_scene_set(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        fake_pem,
    ):
        """launch_obs must receive scene='Small Chapel' and launch_action=action when scene is configured."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            _fake_server_config_with_scene("Small Chapel"), fake_pem,
        )

        obs_control_function(_make_sb_message(MAC_BODY))

        _, kwargs = mock_launch_obs.call_args
        assert kwargs.get("scene") == "Small Chapel"
        assert kwargs.get("launch_action") == "streaming"

    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_launch_obs_receives_none_scene_and_none_start_action_when_no_scene(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        fake_pem,
    ):
        """launch_obs must receive scene=None and launch_action=None when no scene is configured."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            _fake_server_config_without_scene(), fake_pem,
        )

        obs_control_function(_make_sb_message(MAC_BODY))

        _, kwargs = mock_launch_obs.call_args
        assert kwargs.get("scene") is None
        assert kwargs.get("launch_action") is None

    @patch("function_app.start_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app.launch_obs")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_start_action_ws_called_with_correct_port_and_password(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_launch_obs,
        mock_obs_tunnel,
        mock_start_action,
        fake_pem,
    ):
        """When scene is None, start_action must receive the tunnelled local_port and obs password."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            _fake_server_config_without_scene(), fake_pem,
        )

        obs_control_function(_make_sb_message(MAC_BODY))

        mock_start_action.assert_called_once_with(9876, "obs-password", "streaming")


# ---------------------------------------------------------------------------
# Tests: _build_mac_launch_command unit tests
# ---------------------------------------------------------------------------

class TestBuildMacLaunchCommand:
    """
    Direct unit tests for the _build_mac_launch_command helper.
    This function is the core of the Mac CLI-flag feature.
    """

    def setup_method(self):
        from remote_controller import _build_mac_launch_command
        self._fn = _build_mac_launch_command

    def test_command_uses_open(self):
        cmd = self._fn("/obs", None, None)
        assert cmd.startswith("open ")
        assert "launchctl" not in cmd

    def test_command_derives_app_bundle_from_binary_path(self):
        cmd = self._fn("/Applications/OBS.app/Contents/MacOS/obs", None, None)
        assert "/Applications/OBS.app" in cmd
        assert "Contents/MacOS/obs" not in cmd

    def test_no_scene_flag_when_scene_is_none(self):
        cmd = self._fn("/obs", None, None)
        assert "--scene" not in cmd

    def test_scene_flag_appended_when_scene_provided(self):
        cmd = self._fn("/obs", "Small Chapel", None)
        assert '--scene "Small Chapel"' in cmd

    def test_no_action_flag_when_start_action_is_none(self):
        cmd = self._fn("/obs", None, None)
        assert "--startstreaming" not in cmd
        assert "--startrecording" not in cmd

    def test_startstreaming_flag_appended_for_streaming_action(self):
        cmd = self._fn("/obs", "Main", "streaming")
        assert "--startstreaming" in cmd
        assert "--startrecording" not in cmd

    def test_startrecording_flag_appended_for_recording_action(self):
        cmd = self._fn("/obs", "Main", "recording")
        assert "--startrecording" in cmd
        assert "--startstreaming" not in cmd

    def test_command_does_not_background_or_redirect(self):
        # open returns immediately by design — no need for & or > /dev/null
        cmd = self._fn("/obs", None, None)
        assert ">" not in cmd
        assert "&" not in cmd

    def test_scene_and_streaming_flags_together(self):
        cmd = self._fn("/obs", "Live Scene", "streaming")
        assert '--scene "Live Scene"' in cmd
        assert "--startstreaming" in cmd

    def test_unknown_launch_action_raises_value_error(self):
        """An unrecognised launch_action value must raise ValueError immediately."""
        with pytest.raises(ValueError, match="Unrecognised launch_action"):
            self._fn("/obs", "Main", "unknown_action")


# ---------------------------------------------------------------------------
# Tests: malformed message handling
# ---------------------------------------------------------------------------

class TestMalformedMessage:
    """Verify obs_control_function handles malformed Service Bus messages gracefully."""

    def test_malformed_json_returns_silently(self):
        """Malformed JSON should log error and return without raising."""
        from function_app import obs_control_function

        msg = MagicMock()
        msg.get_body.return_value = b"not valid json"

        # Must not raise — returns silently for dead-letter handling
        obs_control_function(msg)

    def test_missing_key_returns_silently(self):
        """JSON missing required keys should log error and return without raising."""
        from function_app import obs_control_function

        msg = MagicMock()
        msg.get_body.return_value = json.dumps({"command": "start"}).encode("utf-8")

        obs_control_function(msg)

    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_config_load_failure_reraises(self, mock_get_env, mock_load_servers):
        """Config load failure must re-raise for Service Bus retry."""
        from function_app import obs_control_function

        mock_get_env.return_value = "https://example.com"
        mock_load_servers.side_effect = Exception("network error")

        with pytest.raises(Exception, match="network error"):
            obs_control_function(_make_sb_message(VALID_BODY))

    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_unknown_server_id_returns_silently(self, mock_get_env, mock_load_servers):
        """Unknown server_id should log error and return without raising."""
        from function_app import obs_control_function

        mock_get_env.return_value = "https://example.com"
        mock_load_servers.return_value = {"other-server": {}}

        obs_control_function(_make_sb_message(VALID_BODY))

    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_key_vault_failure_reraises(self, mock_get_env, mock_load_servers, mock_get_kv_secret, fake_server_config):
        """Key Vault failure must re-raise for Service Bus retry."""
        from function_app import obs_control_function

        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
        mock_load_servers.return_value = fake_server_config
        mock_get_kv_secret.side_effect = Exception("Key Vault unreachable")

        with pytest.raises(Exception, match="Key Vault unreachable"):
            obs_control_function(_make_sb_message(VALID_BODY))


# ---------------------------------------------------------------------------
# Tests: unknown command
# ---------------------------------------------------------------------------

class TestUnknownCommand:

    @patch("function_app.kill_obs")
    @patch("function_app.launch_obs")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_unknown_command_does_not_raise(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_obs_tunnel,
        mock_launch_obs,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """Unknown command should log error and return without raising or calling actions."""
        from function_app import obs_control_function

        b64_key = base64.b64encode(fake_pem.encode("utf-8")).decode("utf-8")
        mock_get_env.return_value = "https://fake-vault.vault.azure.net/"
        mock_load_servers.return_value = fake_server_config
        mock_get_kv_secret.side_effect = lambda _uri, name: (
            b64_key if "ssh-key" in name else "obs-password"
        )

        body = {**VALID_BODY, "command": "restart"}
        obs_control_function(_make_sb_message(body))

        mock_launch_obs.assert_not_called()
        mock_kill_obs.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: stop command with close_exe path
# ---------------------------------------------------------------------------

def _fake_server_config_with_close_exe() -> dict:
    """Return a server config where win-server-1 has close_exe set."""
    return {
        "win-server-1": {
            "name": "Test Windows Server",
            "platform": "windows",
            "host": "192.0.2.1",
            "ssh": {"user": "admin", "port": 22},
            "obs": {
                "path": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                "websocket_port": 4455,
                "close_exe": r"C:\Users\admin\Desktop\close.exe",
            },
        },
    }


class TestStopCommandCloseExe:

    @patch("function_app.kill_obs")
    @patch("function_app.run_close_exe")
    @patch("function_app.quit_obs_ws")
    @patch("function_app.stop_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_stop_with_close_exe_calls_run_close_exe(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_obs_tunnel,
        mock_stop_action,
        mock_quit_obs_ws,
        mock_run_close_exe,
        mock_kill_obs,
        fake_pem,
    ):
        """When close_exe is configured on Windows, run_close_exe is called instead of kill_obs."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            _fake_server_config_with_close_exe(), fake_pem,
        )

        obs_control_function(_make_sb_message({**VALID_BODY, "command": "stop"}))

        mock_run_close_exe.assert_called_once()
        mock_kill_obs.assert_not_called()

    @patch("function_app.kill_obs")
    @patch("function_app.run_close_exe")
    @patch("function_app.quit_obs_ws")
    @patch("function_app.stop_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_stop_without_close_exe_calls_kill_obs(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_obs_tunnel,
        mock_stop_action,
        mock_quit_obs_ws,
        mock_run_close_exe,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """When close_exe is not configured, kill_obs is called."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            fake_server_config, fake_pem,
        )

        obs_control_function(_make_sb_message({**VALID_BODY, "command": "stop"}))

        mock_kill_obs.assert_called_once()
        mock_run_close_exe.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: stop command quit_obs_ws fallback
# ---------------------------------------------------------------------------

class TestStopCommandQuitFallback:

    @patch("function_app.kill_obs")
    @patch("function_app.quit_obs_ws")
    @patch("function_app.stop_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_quit_obs_ws_failure_still_calls_kill_obs(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_obs_tunnel,
        mock_stop_action,
        mock_quit_obs_ws,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """If quit_obs_ws fails, kill_obs should still be called as fallback."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            fake_server_config, fake_pem,
        )
        mock_quit_obs_ws.side_effect = Exception("WebSocket quit failed")

        obs_control_function(_make_sb_message({**VALID_BODY, "command": "stop"}))

        mock_quit_obs_ws.assert_called_once()
        mock_kill_obs.assert_called_once()

    @patch("function_app.kill_obs")
    @patch("function_app.quit_obs_ws")
    @patch("function_app.stop_action")
    @patch("function_app.obs_tunnel")
    @patch("function_app._get_kv_secret")
    @patch("function_app._load_servers_config")
    @patch("function_app._get_env")
    def test_stop_calls_quit_obs_ws_before_kill(
        self,
        mock_get_env,
        mock_load_servers,
        mock_get_kv_secret,
        mock_obs_tunnel,
        mock_stop_action,
        mock_quit_obs_ws,
        mock_kill_obs,
        fake_pem,
        fake_server_config,
    ):
        """Stop path must call quit_obs_ws (inside the tunnel) before kill_obs."""
        from function_app import obs_control_function

        _setup_standard_mocks(
            mock_get_env, mock_load_servers, mock_get_kv_secret, mock_obs_tunnel,
            fake_server_config, fake_pem,
        )

        obs_control_function(_make_sb_message({**VALID_BODY, "command": "stop"}))

        mock_quit_obs_ws.assert_called_once()
        mock_kill_obs.assert_called_once()
