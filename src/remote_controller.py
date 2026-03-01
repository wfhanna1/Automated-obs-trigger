"""
remote_controller.py

SSH operations for launching and killing OBS on remote Windows and Mac machines,
plus an SSH-tunnel context manager for OBS WebSocket access.

Secrets (SSH private key PEM text) are passed in at call time — this module
never reads from disk or environment variables directly.
"""

from __future__ import annotations

import io
import logging
import socket
import threading
import time
from contextlib import contextmanager

import paramiko

logger = logging.getLogger(__name__)

# How long to wait after launching OBS before attempting WebSocket connection
OBS_LAUNCH_WAIT_SECONDS = 10

# SSH connection timeout in seconds
SSH_CONNECT_TIMEOUT = 15

# Number of SSH connection retries
SSH_MAX_RETRIES = 3


def _make_ssh_client(host: str, port: int, user: str, key_pem: str) -> paramiko.SSHClient:
    """
    Create and return a connected paramiko SSHClient.
    Retries up to SSH_MAX_RETRIES times on connection failure.

    Args:
        host:    Remote hostname or IP.
        port:    SSH port (usually 22).
        user:    SSH username.
        key_pem: PEM-encoded private key as a string.

    Returns:
        Connected SSHClient.

    Raises:
        RuntimeError: If all retries fail.
    """
    pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_pem))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    last_exc: Exception | None = None
    for attempt in range(1, SSH_MAX_RETRIES + 1):
        try:
            client.connect(
                hostname=host,
                port=port,
                username=user,
                pkey=pkey,
                timeout=SSH_CONNECT_TIMEOUT,
                banner_timeout=SSH_CONNECT_TIMEOUT,
            )
            logger.debug("SSH connected to %s:%d (attempt %d).", host, port, attempt)
            return client
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "SSH connection to %s:%d failed (attempt %d/%d): %s",
                host, port, attempt, SSH_MAX_RETRIES, exc,
            )
            if attempt < SSH_MAX_RETRIES:
                time.sleep(2 ** attempt)  # 2s, 4s back-off

    raise RuntimeError(
        f"Could not SSH to {host}:{port} after {SSH_MAX_RETRIES} attempts: {last_exc}"
    )


def _ssh_exec(client: paramiko.SSHClient, command: str) -> tuple[str, str]:
    """Run a command over SSH and return (stdout, stderr)."""
    logger.debug("SSH exec: %s", command)
    _, stdout, stderr = client.exec_command(command, timeout=30)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if err:
        logger.debug("SSH stderr: %s", err)
    return out, err


def launch_obs(host: str, port: int, user: str, key_pem: str,
               platform: str, obs_path: str) -> None:
    """
    SSH into the remote machine and start OBS in the background.

    After launching, waits OBS_LAUNCH_WAIT_SECONDS to let the OBS WebSocket
    server initialise before the caller attempts a WebSocket connection.

    Args:
        host:      Remote hostname or IP.
        port:      SSH port.
        user:      SSH username.
        key_pem:   PEM private key string.
        platform:  "windows" or "mac".
        obs_path:  Full path to OBS executable on the remote machine.
    """
    client = _make_ssh_client(host, port, user, key_pem)
    try:
        if platform == "windows":
            # Start-Process via an SSH exec channel runs in a non-interactive session
            # (Session 0) and cannot access the active desktop, so GUI apps like OBS
            # never start. Task Scheduler with LogonType Interactive runs the process
            # in the logged-on user's desktop session instead.
            # Derive the directory containing obs64.exe so Task Scheduler sets
            # the working directory correctly. Without this, sched tasks default
            # to C:\Windows\System32 and OBS cannot find its locale files.
            obs_dir = obs_path.rsplit("\\", 1)[0]
            register_cmd = (
                f'Register-ScheduledTask -TaskName "OBSAutoStart" '
                f'-Action (New-ScheduledTaskAction -Execute "{obs_path}" '
                f'-WorkingDirectory "{obs_dir}") '
                f'-Principal (New-ScheduledTaskPrincipal '
                f'-UserId $env:USERNAME -LogonType Interactive) '
                f'-Force | Out-Null'
            )
            run_cmd = 'Start-ScheduledTask -TaskName "OBSAutoStart"'

            _, err = _ssh_exec(client, register_cmd)
            if err:
                logger.warning("Task registration stderr on %s: %s", host, err)
            _, err = _ssh_exec(client, run_cmd)
            if err:
                logger.warning("Task start stderr on %s: %s", host, err)
        else:
            # Mac: run detached via nohup so the SSH session can close cleanly.
            command = f"nohup '{obs_path}' --minimize-to-tray > /dev/null 2>&1 &"
            _ssh_exec(client, command)

        logger.info("OBS launch command sent to %s (%s). Waiting %ds for startup…",
                    host, platform, OBS_LAUNCH_WAIT_SECONDS)
    finally:
        client.close()

    time.sleep(OBS_LAUNCH_WAIT_SECONDS)


def kill_obs(host: str, port: int, user: str, key_pem: str, platform: str) -> None:
    """
    SSH into the remote machine and terminate the OBS process.

    Args:
        host:     Remote hostname or IP.
        port:     SSH port.
        user:     SSH username.
        key_pem:  PEM private key string.
        platform: "windows" or "mac".
    """
    client = _make_ssh_client(host, port, user, key_pem)
    try:
        if platform == "windows":
            command = (
                'powershell -Command '
                '"Stop-Process -Name obs64 -Force -ErrorAction SilentlyContinue"'
            )
        else:
            command = "pkill -x OBS || true"

        _ssh_exec(client, command)
        logger.info("OBS kill command sent to %s (%s).", host, platform)
    finally:
        client.close()


def _forward(local_sock: socket.socket, channel: paramiko.Channel) -> None:
    """Bidirectionally forward data between a local socket and a paramiko channel."""
    channel.settimeout(0.5)

    def _pipe(src_recv, dst_send) -> None:
        try:
            while True:
                data = src_recv(1024)
                if not data:
                    break
                dst_send(data)
        except (OSError, EOFError):
            pass

    t1 = threading.Thread(target=_pipe, args=(local_sock.recv, channel.sendall), daemon=True)
    t2 = threading.Thread(target=_pipe, args=(channel.recv, local_sock.sendall), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    local_sock.close()
    channel.close()


@contextmanager
def obs_tunnel(host: str, ssh_port: int, user: str, key_pem: str, ws_port: int):
    """
    Context manager that opens an SSH tunnel to the remote machine's OBS WebSocket port.

    Uses paramiko.Transport directly — no sshtunnel dependency.

    Usage:
        with obs_tunnel(host, ssh_port, user, key_pem, ws_port) as local_port:
            client = obs.ReqClient(host='localhost', port=local_port, ...)

    Args:
        host:     Remote hostname or IP.
        ssh_port: SSH port on the remote machine.
        user:     SSH username.
        key_pem:  PEM private key string.
        ws_port:  OBS WebSocket port on the remote machine (default 4455).

    Yields:
        int: The local port to connect to (tunnelled to remote ws_port).
    """
    pkey = paramiko.RSAKey.from_private_key(io.StringIO(key_pem))
    transport = paramiko.Transport((host, ssh_port))
    transport.connect(username=user, pkey=pkey)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    local_port = server_sock.getsockname()[1]
    server_sock.listen(5)
    server_sock.settimeout(0.5)

    stop_event = threading.Event()

    def _accept_loop() -> None:
        while not stop_event.is_set():
            try:
                local_conn, _ = server_sock.accept()
                channel = transport.open_channel(
                    "direct-tcpip", ("127.0.0.1", ws_port), ("127.0.0.1", 0)
                )
                threading.Thread(
                    target=_forward, args=(local_conn, channel), daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    accept_thread = threading.Thread(target=_accept_loop, daemon=True)
    accept_thread.start()

    try:
        logger.debug("SSH tunnel open: localhost:%d → %s:%d", local_port, host, ws_port)
        yield local_port
    finally:
        stop_event.set()
        server_sock.close()
        accept_thread.join(timeout=2)
        transport.close()
        logger.debug("SSH tunnel closed to %s.", host)


