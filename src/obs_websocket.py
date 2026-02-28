"""
obs_websocket.py

Controls OBS Studio via the OBS WebSocket v5 API (built into OBS 28+).

All connections are made to localhost on a tunnelled port provided by the
obs_tunnel() context manager in remote_controller.py — OBS WebSocket is
never exposed directly to the internet.
"""

import logging
import time

import obsws_python as obs

logger = logging.getLogger(__name__)

# How long to wait between WebSocket connection retries
WS_RETRY_INTERVAL = 3

# Maximum number of connection attempts before giving up
WS_MAX_RETRIES = 10

# obsws-python connection timeout in seconds
WS_TIMEOUT = 10


def _connect(local_port: int, password: str) -> obs.ReqClient:
    """
    Attempt to connect to OBS WebSocket on localhost:<local_port>.
    Retries up to WS_MAX_RETRIES times to allow OBS time to fully start.

    Args:
        local_port: Local port forwarded to the remote OBS WebSocket port via SSH tunnel.
        password:   OBS WebSocket server password.

    Returns:
        Connected obs.ReqClient.

    Raises:
        RuntimeError: If connection cannot be established within the retry limit.
    """
    last_exc: Exception | None = None
    for attempt in range(1, WS_MAX_RETRIES + 1):
        try:
            client = obs.ReqClient(
                host="localhost",
                port=local_port,
                password=password,
                timeout=WS_TIMEOUT,
            )
            logger.debug(
                "OBS WebSocket connected on localhost:%d (attempt %d).", local_port, attempt
            )
            return client
        except Exception as exc:
            last_exc = exc
            logger.debug(
                "OBS WebSocket not ready on localhost:%d (attempt %d/%d): %s",
                local_port, attempt, WS_MAX_RETRIES, exc,
            )
            if attempt < WS_MAX_RETRIES:
                time.sleep(WS_RETRY_INTERVAL)

    raise RuntimeError(
        f"Could not connect to OBS WebSocket on localhost:{local_port} "
        f"after {WS_MAX_RETRIES} attempts: {last_exc}"
    )


def start_action(local_port: int, password: str, action: str) -> None:
    """
    Connect to OBS WebSocket and start recording or streaming.

    Args:
        local_port: Tunnelled local port for OBS WebSocket.
        password:   OBS WebSocket password.
        action:     "recording" or "streaming".

    Raises:
        ValueError: If action is not "recording" or "streaming".
        RuntimeError: If WebSocket connection fails.
    """
    client = _connect(local_port, password)
    try:
        if action == "recording":
            client.start_record()
            logger.info("OBS recording started (localhost:%d).", local_port)
        elif action == "streaming":
            client.start_stream()
            logger.info("OBS streaming started (localhost:%d).", local_port)
        else:
            raise ValueError(f"Unknown action '{action}'. Must be 'recording' or 'streaming'.")
    finally:
        client.disconnect()


def stop_action(local_port: int, password: str, action: str) -> None:
    """
    Connect to OBS WebSocket and stop recording or streaming.

    Args:
        local_port: Tunnelled local port for OBS WebSocket.
        password:   OBS WebSocket password.
        action:     "recording" or "streaming".

    Raises:
        ValueError: If action is not "recording" or "streaming".
        RuntimeError: If WebSocket connection fails.
    """
    client = _connect(local_port, password)
    try:
        if action == "recording":
            client.stop_record()
            logger.info("OBS recording stopped (localhost:%d).", local_port)
        elif action == "streaming":
            client.stop_stream()
            logger.info("OBS streaming stopped (localhost:%d).", local_port)
        else:
            raise ValueError(f"Unknown action '{action}'. Must be 'recording' or 'streaming'.")
    finally:
        client.disconnect()
