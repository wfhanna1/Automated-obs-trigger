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
import os
import tempfile
import time
from contextlib import contextmanager

import paramiko
from sshtunnel import SSHTunnelForwarder

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
            # Start-Process launches OBS detached; -WindowStyle Hidden keeps it background.
            command = (
                f'powershell -Command "Start-Process \'{obs_path}\' -WindowStyle Hidden"'
            )
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


@contextmanager
def obs_tunnel(host: str, ssh_port: int, user: str, key_pem: str, ws_port: int):
    """
    Context manager that opens an SSH tunnel to the remote machine's OBS WebSocket port.

    Usage:
        with obs_tunnel(host, ssh_port, user, key_pem, ws_port) as local_port:
            client = obs.ReqClient(host='localhost', port=local_port, ...)

    The SSH private key is written to a temporary file (sshtunnel requires a file
    path), used for the duration of the context, then securely deleted.

    Args:
        host:     Remote hostname or IP.
        ssh_port: SSH port on the remote machine.
        user:     SSH username.
        key_pem:  PEM private key string.
        ws_port:  OBS WebSocket port on the remote machine (default 4455).

    Yields:
        int: The local port to connect to (tunnelled to remote ws_port).
    """
    # Write PEM key to a temp file; sshtunnel/paramiko require a file path.
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    try:
        tmp.write(key_pem)
        tmp.flush()
        tmp.close()
        os.chmod(tmp.name, 0o600)

        tunnel = SSHTunnelForwarder(
            (host, ssh_port),
            ssh_username=user,
            ssh_pkey=tmp.name,
            remote_bind_address=("127.0.0.1", ws_port),
        )
        tunnel.start()
        logger.debug(
            "SSH tunnel open: localhost:%d → %s:%d", tunnel.local_bind_port, host, ws_port
        )
        try:
            yield tunnel.local_bind_port
        finally:
            tunnel.stop()
            logger.debug("SSH tunnel closed to %s.", host)
    finally:
        os.unlink(tmp.name)


