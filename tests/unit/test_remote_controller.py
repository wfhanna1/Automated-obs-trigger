"""
tests/unit/test_remote_controller.py

Unit tests for src/remote_controller.py

All external dependencies (paramiko, time) are mocked.
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
    def test_launches_obs_on_windows_with_task_scheduler(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        register_cmd = mock_client.exec_command.call_args_list[0][0][0]
        run_cmd = mock_client.exec_command.call_args_list[1][0][0]
        assert "Register-ScheduledTask" in register_cmd
        assert "Start-ScheduledTask" in run_cmd

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_windows_launch_makes_two_exec_command_calls(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        assert mock_client.exec_command.call_count == 2

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_windows_task_uses_interactive_logon_type(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\obs64.exe")

        register_cmd = mock_client.exec_command.call_args_list[0][0][0]
        assert "Interactive" in register_cmd

    @patch("remote_controller.time.sleep")
    @patch("remote_controller._make_ssh_client")
    def test_windows_task_sets_working_directory_to_obs_dir(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows",
                   r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")

        register_cmd = mock_client.exec_command.call_args_list[0][0][0]
        assert r"C:\Program Files\obs-studio\bin\64bit" in register_cmd
        assert "WorkingDirectory" in register_cmd

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
    def test_includes_obs_path_in_windows_register_command(
        self, mock_make_client, mock_sleep, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        launch_obs("host", 22, "user", fake_pem, "windows", r"C:\custom\obs64.exe")

        register_cmd = mock_client.exec_command.call_args_list[0][0][0]
        assert r"C:\custom\obs64.exe" in register_cmd

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
    def test_kills_obs_on_windows_with_taskkill_command(
        self, mock_make_client, fake_pem
    ):
        mock_client = self._make_connected_client()
        mock_make_client.return_value = mock_client

        kill_obs("host", 22, "user", fake_pem, "windows")

        cmd_arg = mock_client.exec_command.call_args[0][0]
        assert "taskkill" in cmd_arg
        assert "/F" not in cmd_arg

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
# obs_tunnel — paramiko.Transport-based implementation
# ---------------------------------------------------------------------------


class TestObsTunnelParamiko:
    """
    obs_tunnel must use paramiko.Transport directly — no sshtunnel dependency.

    Behaviours under test:
      - yields the local port that the server socket was bound to
      - creates a paramiko.Transport to (host, ssh_port)
      - authenticates with the correct username and RSA key
      - closes the transport on clean exit
      - closes the transport even when an exception is raised inside the with-block
      - forwards to the correct remote ws_port (open_channel called with ws_port)
    """

    def _setup_mocks(self, mock_transport_class, mock_rsa_key_class, mock_socket_class):
        """Wire up standard happy-path mocks and return the key objects."""
        mock_transport = MagicMock()
        mock_transport_class.return_value = mock_transport

        mock_pkey = MagicMock()
        mock_rsa_key_class.from_private_key.return_value = mock_pkey

        # Server socket: bind() sets getsockname() to return a free port.
        mock_server_sock = MagicMock()
        mock_server_sock.getsockname.return_value = ("127.0.0.1", 54321)
        # accept() raises OSError after the first call so the accept loop exits.
        mock_server_sock.accept.side_effect = OSError("closed")
        mock_socket_class.return_value = mock_server_sock

        return mock_transport, mock_pkey, mock_server_sock

    @patch("remote_controller.socket.socket")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.Transport")
    def test_yields_local_bind_port(
        self, mock_transport_class, mock_rsa_key_class, mock_socket_class, fake_pem
    ):
        """The yielded value must be the port the server socket bound to."""
        self._setup_mocks(mock_transport_class, mock_rsa_key_class, mock_socket_class)

        with obs_tunnel("host", 22, "user", fake_pem, 4455) as port:
            assert port == 54321

    @patch("remote_controller.socket.socket")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.Transport")
    def test_transport_created_with_host_and_ssh_port(
        self, mock_transport_class, mock_rsa_key_class, mock_socket_class, fake_pem
    ):
        """paramiko.Transport must be constructed with (host, ssh_port)."""
        self._setup_mocks(mock_transport_class, mock_rsa_key_class, mock_socket_class)

        with obs_tunnel("myhost", 2222, "user", fake_pem, 4455):
            pass

        mock_transport_class.assert_called_once_with(("myhost", 2222))

    @patch("remote_controller.socket.socket")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.Transport")
    def test_transport_authenticated_with_correct_user_and_key(
        self, mock_transport_class, mock_rsa_key_class, mock_socket_class, fake_pem
    ):
        """transport.connect() must receive the correct username and RSA key."""
        mock_transport, mock_pkey, _ = self._setup_mocks(
            mock_transport_class, mock_rsa_key_class, mock_socket_class
        )

        with obs_tunnel("host", 22, "myuser", fake_pem, 4455):
            pass

        mock_transport.connect.assert_called_once_with(username="myuser", pkey=mock_pkey)

    @patch("remote_controller.socket.socket")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.Transport")
    def test_transport_closed_on_clean_exit(
        self, mock_transport_class, mock_rsa_key_class, mock_socket_class, fake_pem
    ):
        """transport.close() must be called when the with-block exits normally."""
        mock_transport, _, _ = self._setup_mocks(
            mock_transport_class, mock_rsa_key_class, mock_socket_class
        )

        with obs_tunnel("host", 22, "user", fake_pem, 4455):
            pass

        mock_transport.close.assert_called_once()

    @patch("remote_controller.socket.socket")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.Transport")
    def test_transport_closed_on_exception(
        self, mock_transport_class, mock_rsa_key_class, mock_socket_class, fake_pem
    ):
        """transport.close() must be called even when an exception escapes the block."""
        mock_transport, _, _ = self._setup_mocks(
            mock_transport_class, mock_rsa_key_class, mock_socket_class
        )

        with pytest.raises(RuntimeError):
            with obs_tunnel("host", 22, "user", fake_pem, 4455):
                raise RuntimeError("boom inside tunnel")

        mock_transport.close.assert_called_once()

    @patch("remote_controller.socket.socket")
    @patch("remote_controller.paramiko.RSAKey")
    @patch("remote_controller.paramiko.Transport")
    def test_open_channel_targets_correct_remote_ws_port(
        self, mock_transport_class, mock_rsa_key_class, mock_socket_class, fake_pem
    ):
        """When a local connection arrives, open_channel must target ws_port on the remote."""
        mock_transport, _, mock_server_sock = self._setup_mocks(
            mock_transport_class, mock_rsa_key_class, mock_socket_class
        )

        # Simulate one incoming local connection before raising OSError to stop the loop.
        mock_local_conn = MagicMock()
        mock_local_conn.recv.return_value = b""  # signal EOF so forwarder exits
        mock_server_sock.accept.side_effect = [(mock_local_conn, ("127.0.0.1", 9999)), OSError("closed")]

        mock_channel = MagicMock()
        mock_channel.recv.return_value = b""
        mock_transport.open_channel.return_value = mock_channel

        with obs_tunnel("host", 22, "user", fake_pem, 7777):
            import time as _time
            _time.sleep(0.05)  # let accept thread process one connection

        dest = mock_transport.open_channel.call_args[0][1]  # (dest_addr, dest_port)
        assert dest[1] == 7777
