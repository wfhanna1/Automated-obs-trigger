"""
tests/unit/test_remote_controller.py

Unit tests for src/remote_controller.py

All external dependencies (paramiko, sshtunnel, time, tempfile, os) are mocked.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from unittest.mock import MagicMock, patch
import pytest

from remote_controller import (
    _make_ssh_client,
    _ssh_exec,
    launch_obs,
    kill_obs,
    obs_tunnel,
    SSH_MAX_RETRIES,
    OBS_LAUNCH_WAIT_SECONDS,
)


# ---------------------------------------------------------------------------
# _make_ssh_client tests
# ---------------------------------------------------------------------------

class TestMakeSshClient:

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_returns_connected_client_on_first_attempt(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()

        result = _make_ssh_client("host", 22, "user", fake_pem)

        assert result is mock_client
        mock_client.connect.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_uses_autoaddpolicy(self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()

        _make_ssh_client("host", 22, "user", fake_pem)

        mock_client.set_missing_host_key_policy.assert_called_once()

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_passes_correct_host_port_user_to_connect(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()

        _make_ssh_client("myhost", 2222, "myuser", fake_pem)

        _, kwargs = mock_client.connect.call_args
        assert kwargs["hostname"] == "myhost"
        assert kwargs["port"] == 2222
        assert kwargs["username"] == "myuser"

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_retries_on_connection_failure_and_succeeds(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()
        # Fail once, then succeed
        mock_client.connect.side_effect = [Exception("timeout"), None]

        result = _make_ssh_client("host", 22, "user", fake_pem)

        assert result is mock_client
        assert mock_client.connect.call_count == 2
        mock_sleep.assert_called_once()

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_raises_runtime_error_after_all_retries_exhausted(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()
        mock_client.connect.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError, match="Could not SSH"):
            _make_ssh_client("host", 22, "user", fake_pem)

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_retries_exactly_ssh_max_retries_times(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()
        mock_client.connect.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError):
            _make_ssh_client("host", 22, "user", fake_pem)

        assert mock_client.connect.call_count == SSH_MAX_RETRIES

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_sleep_uses_exponential_backoff(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()
        mock_client.connect.side_effect = Exception("fail")

        with pytest.raises(RuntimeError):
            _make_ssh_client("host", 22, "user", fake_pem)

        # With SSH_MAX_RETRIES=3, sleep is called after attempt 1 (2s) and attempt 2 (4s)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [2, 4]

    @patch("remote_controller.time.sleep")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.SSHClient")
    def test_no_sleep_after_final_failed_attempt(
        self, mock_ssh_class, mock_rsa_key, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_rsa_key.from_private_key.return_value = MagicMock()
        mock_client.connect.side_effect = Exception("fail")

        with pytest.raises(RuntimeError):
            _make_ssh_client("host", 22, "user", fake_pem)

        # Should only sleep SSH_MAX_RETRIES - 1 times (not after the last attempt)
        assert mock_sleep.call_count == SSH_MAX_RETRIES - 1


# ---------------------------------------------------------------------------
# _ssh_exec tests
# ---------------------------------------------------------------------------

class TestSshExec:

    def test_returns_stdout_and_stderr(self):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b"  output  "
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        out, err = _ssh_exec(mock_client, "echo hello")

        assert out == "output"
        assert err == ""

    def test_strips_stdout_and_stderr(self):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b"  output\n  "
        mock_stderr.read.return_value = b"  warning  "
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        out, err = _ssh_exec(mock_client, "cmd")

        assert out == "output"
        assert err == "warning"

    def test_exec_command_called_with_correct_command(self):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b""
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        _ssh_exec(mock_client, "my-command")

        mock_client.exec_command.assert_called_once_with("my-command", timeout=30)


# ---------------------------------------------------------------------------
# launch_obs tests
# ---------------------------------------------------------------------------

class TestLaunchObs:

    def _make_connected_client(self):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b""
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        return mock_client

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_launches_obs_on_windows_with_powershell_command(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "powershell" in cmd_arg
        assert "Start-Process" in cmd_arg

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_launches_obs_on_mac_with_nohup_command(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "mac", "/Applications/OBS.app/Contents/MacOS/obs")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "nohup" in cmd_arg

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_includes_obs_path_in_windows_command(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\custom\obs64.exe")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert r"C:\custom\obs64.exe" in cmd_arg

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_includes_obs_path_in_mac_command(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "mac", "/custom/obs")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "/custom/obs" in cmd_arg

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_client_is_closed_after_launch(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        mock_client.close.assert_called_once()

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_waits_obs_launch_wait_seconds_after_launch(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        mock_sleep.assert_called_once_with(OBS_LAUNCH_WAIT_SECONDS)

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_client_closed_even_if_exec_raises(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = MagicMock()
        mock_client.exec_command.side_effect = Exception("exec failed")
        mock_make_client.return_value = mock_client

        with pytest.raises(Exception, match="exec failed"):
            launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        mock_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# kill_obs tests
# ---------------------------------------------------------------------------

class TestKillObs:

    def _make_connected_client(self):
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        mock_stdout.read.return_value = b""
        mock_stderr.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
        return mock_client

    @patch("remote_controller._make_ssh_client")
    def test_kills_obs_on_windows_with_stop_process_command(
        self, mock_make_client, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        kill_obs("host", 22, "user", fake_pem, "windows")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "Stop-Process" in cmd_arg

    @patch("remote_controller._make_ssh_client")
    def test_kills_obs_on_mac_with_pkill_command(
        self, mock_make_client, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        kill_obs("host", 22, "user", fake_pem, "mac")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "pkill" in cmd_arg

    @patch("remote_controller._make_ssh_client")
    def test_client_is_closed_after_kill(self, mock_make_client, fake_pem):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        kill_obs("host", 22, "user", fake_pem, "windows")

        mock_client.close.assert_called_once()

    @patch("remote_controller._make_ssh_client")
    def test_client_closed_even_if_exec_raises(self, mock_make_client, fake_pem):
        mock_client = MagicMock()
        mock_client.exec_command.side_effect = Exception("exec failed")
        mock_make_client.return_value = mock_client

        with pytest.raises(Exception, match="exec failed"):
            kill_obs("host", 22, "user", fake_pem, "windows")

        mock_client.close.assert_called_once()

    @patch("remote_controller._make_ssh_client")
    def test_windows_kill_targets_obs64_process(self, mock_make_client, fake_pem):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        kill_obs("host", 22, "user", fake_pem, "windows")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "obs64" in cmd_arg


# ---------------------------------------------------------------------------
# obs_tunnel tests
# ---------------------------------------------------------------------------

class TestObsTunnel:

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_yields_local_bind_port(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 4455) as port:
            assert port == 12345

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_tunnel_started_on_enter(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 4455):
            mock_tunnel.start.assert_called_once()

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_tunnel_stopped_on_exit(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 4455):
            pass

        mock_tunnel.stop.assert_called_once()

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_temp_file_deleted_on_exit(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 4455):
            pass

        mock_unlink.assert_called_once_with("/tmp/fake_key.pem")

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_pem_key_permissions_set_to_600(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 4455):
            pass

        mock_chmod.assert_called_once_with("/tmp/fake_key.pem", 0o600)

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_forwarder_configured_with_correct_remote_port(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 9999):
            pass

        _, kwargs = mock_forwarder_class.call_args
        assert kwargs["remote_bind_address"] == ("127.0.0.1", 9999)

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_tunnel_stopped_and_temp_file_deleted_on_exception(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with pytest.raises(RuntimeError):
            with obs_tunnel("host", 22, "user", fake_pem, 4455):
                raise RuntimeError("something failed inside the tunnel")

        mock_tunnel.stop.assert_called_once()
        mock_unlink.assert_called_once_with("/tmp/fake_key.pem")

    @patch("remote_controller.os.unlink")
    @patch("remote_controller.os.chmod")
    @patch("remote_controller.SSHTunnelForwarder")
    @patch("remote_controller.tempfile.NamedTemporaryFile")
    def test_pem_key_written_to_temp_file(
        self, mock_tmp_file, mock_forwarder_class, mock_chmod, mock_unlink, fake_pem
    ):
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/fake_key.pem"
        mock_tmp_file.return_value = mock_tmp

        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 12345
        mock_forwarder_class.return_value = mock_tunnel

        with obs_tunnel("host", 22, "user", fake_pem, 4455):
            pass

        mock_tmp.write.assert_called_once_with(fake_pem)
