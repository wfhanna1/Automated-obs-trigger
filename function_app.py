"""
function_app.py — Azure Functions v2 entry point

Two functions:

  LoadSchedule  (HTTP POST /api/load-schedule)
      Reads schedules/current_week.csv from GitHub, parses sessions,
      and sends a START and STOP Service Bus message for each session,
      scheduled for delivery at the exact UTC datetime.

  OBSControl  (Service Bus queue trigger on "obs-jobs")
      Fires at the scheduled time, SSHes into the remote machine, and
      either starts or stops OBS recording/streaming via the WebSocket API.
"""

import base64
import json
import logging
import os
import sys

import azure.functions as func
import requests
import yaml
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.servicebus import ServiceBusClient, ServiceBusMessage

# Ensure the src package is importable when running inside the Function App.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from schedule_loader import load_schedule          # noqa: E402
from remote_controller import launch_obs, kill_obs, obs_tunnel, run_close_exe   # noqa: E402
from obs_websocket import start_action, stop_action  # noqa: E402
from event_publisher import publish_stream_started  # noqa: E402
from queue_manager import purge_scheduled_messages  # noqa: E402
from telemetry import configure_telemetry          # noqa: E402
from startup_validator import validate_required_config  # noqa: E402

configure_telemetry()
validate_required_config()

logger = logging.getLogger(__name__)

# Queue name shared between LoadSchedule (purge + send) and the OBSControl
# trigger decorator. The decorator below requires a string literal, so the
# literal is intentionally duplicated there; everywhere else uses this constant.
OBS_JOBS_QUEUE = "obs-jobs"

# Must match obs-jobs maxDeliveryCount in infra/main.bicep. Used to decide
# whether an OBSControl exception is a transient retry (Warning) or the
# final, about-to-dead-letter attempt (Error). The alert rule in main.bicep
# fires on Error severity, so intermediate retries must not log at Error.
OBS_JOBS_MAX_DELIVERY_COUNT = 3

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


def _fetch_text(url: str) -> str:
    """Fetch plain text from a URL (e.g. GitHub raw content)."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def _load_servers_config(url: str) -> dict:
    """Fetch and parse servers.yaml from the given URL."""
    text = _fetch_text(url)
    config = yaml.safe_load(text)
    return config.get("servers", {})


def _get_kv_secret(kv_uri: str, secret_name: str) -> str:
    """Retrieve a secret from Azure Key Vault using Managed Identity."""
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=kv_uri, credential=credential)
    secret_value = client.get_secret(secret_name).value
    if secret_value is None:
        raise RuntimeError(f"Key Vault secret '{secret_name}' exists but has no value.")
    return secret_value


# ---------------------------------------------------------------------------
# Function 1: LoadSchedule
# ---------------------------------------------------------------------------

@app.route(route="load-schedule", methods=["POST"])
def load_schedule_function(req: func.HttpRequest) -> func.HttpResponse:
    """
    Read the weekly CSV schedule from GitHub and enqueue Service Bus messages
    for each session's start and stop time.

    Triggered automatically by GitHub Actions when current_week.csv is pushed,
    or called manually via HTTP POST.
    """
    logger.info("LoadSchedule triggered.")

    try:
        csv_url = _get_env("GITHUB_RAW_CSV_URL")
        servers_url = _get_env("SERVERS_CONFIG_URL")
        sb_connection = _get_env("SERVICE_BUS_CONNECTION")
    except RuntimeError as exc:
        return func.HttpResponse(str(exc), status_code=500)

    # Fetch and parse the schedule CSV
    try:
        csv_text = _fetch_text(csv_url)
    except Exception as exc:
        msg = f"Failed to fetch schedule CSV from {csv_url}: {exc}"
        logger.error(msg)
        return func.HttpResponse(msg, status_code=502)

    # Fetch servers config for validation
    try:
        servers = _load_servers_config(servers_url)
    except Exception as exc:
        msg = f"Failed to fetch/parse servers.yaml from {servers_url}: {exc}"
        logger.error(msg)
        return func.HttpResponse(msg, status_code=502)

    try:
        entries = load_schedule(csv_text, known_server_ids=set(servers.keys()))
    except ValueError as exc:
        msg = f"Schedule validation error: {exc}"
        logger.error(msg)
        return func.HttpResponse(msg, status_code=400)

    if not entries:
        msg = "No future sessions found in schedule — nothing to enqueue."
        logger.info(msg)
        return func.HttpResponse(msg, status_code=200)

    # Send scheduled Service Bus messages
    queued = 0
    errors = []
    with ServiceBusClient.from_connection_string(sb_connection) as sb_client:
        purge_scheduled_messages(sb_client, OBS_JOBS_QUEUE)
        with sb_client.get_queue_sender(OBS_JOBS_QUEUE) as sender:
            for entry in entries:
                for command, scheduled_time in [
                    ("start", entry.start_dt),
                    ("stop", entry.stop_dt),
                ]:
                    payload = {
                        "command": command,
                        "server_id": entry.server_id,
                        "action": entry.action,
                    }
                    if entry.title is not None:
                        payload["title"] = entry.title
                    try:
                        sb_msg = ServiceBusMessage(json.dumps(payload))
                        sb_msg.scheduled_enqueue_time_utc = scheduled_time.replace(tzinfo=None)
                        sender.send_messages(sb_msg)
                        logger.info(
                            "Enqueued %s/%s for server=%s at %s UTC.",
                            command, entry.action, entry.server_id, scheduled_time,
                        )
                        queued += 1
                    except Exception as exc:
                        errors.append(
                            f"{command}/{entry.server_id}@{scheduled_time}: {exc}"
                        )
                        logger.error("Failed to enqueue message: %s", exc)

    summary = f"Enqueued {queued} message(s)."
    if errors:
        summary += f" Errors ({len(errors)}): {'; '.join(errors)}"
        return func.HttpResponse(summary, status_code=207)

    logger.info(summary)
    return func.HttpResponse(summary, status_code=200)


# ---------------------------------------------------------------------------
# Function 2: OBSControl
# ---------------------------------------------------------------------------

@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="obs-jobs",
    connection="SERVICE_BUS_CONNECTION",
)
def obs_control_function(msg: func.ServiceBusMessage) -> None:
    """
    Triggered by a Service Bus message at the scheduled time.

    Message body (JSON):
        {
          "command":   "start" | "stop",
          "server_id": "<id matching servers.yaml>",
          "action":    "recording" | "streaming"
        }

    On "start": SSH → launch OBS → SSH tunnel → WebSocket → start action.
    On "stop":  SSH tunnel → WebSocket → stop action → SSH → kill OBS.
    """
    body = msg.get_body().decode("utf-8")
    logger.info("OBSControl triggered. Body: %s", body)

    try:
        data = json.loads(body)
        command = data["command"]
        server_id = data["server_id"]
        action = data["action"]
        title = data.get("title")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Malformed Service Bus message: %s — %s", body, exc)
        return  # Dead-letter on persistent errors is handled by Service Bus

    # Load server configuration
    try:
        servers_url = _get_env("SERVERS_CONFIG_URL")
        servers = _load_servers_config(servers_url)
    except Exception as exc:
        logger.error("Cannot load servers config: %s", exc)
        raise  # Re-raise to trigger Service Bus retry / dead-letter

    if server_id not in servers:
        logger.error("Unknown server_id '%s'. Check servers.yaml.", server_id)
        return

    server = servers[server_id]
    host = server["host"]
    ssh_port = server["ssh"]["port"]
    ssh_user = server["ssh"]["user"]
    platform = server["platform"]
    obs_path = server["obs"].get("path", "")
    ws_port = server["obs"]["websocket_port"]
    close_exe_path = server["obs"].get("close_exe")

    # Fetch secrets from Key Vault at runtime
    try:
        kv_uri = _get_env("KEY_VAULT_URI")
        # Key Vault secret names use hyphens; server IDs may use underscores.
        kv_id = server_id.replace("_", "-")
        ssh_key_pem = base64.b64decode(_get_kv_secret(kv_uri, f"ssh-key-{kv_id}")).decode("utf-8")
        obs_password = _get_kv_secret(kv_uri, f"obs-ws-password-{kv_id}")
    except Exception as exc:
        logger.error("Failed to retrieve secrets from Key Vault: %s", exc)
        raise

    try:
        if command == "start":
            logger.info("Starting OBS on %s (%s) — action: %s", server_id, host, action)
            scene = server["obs"].get("scene")
            use_cli_flags = scene is not None
            launch_obs(
                host, ssh_port, ssh_user, ssh_key_pem, platform, obs_path,
                scene=scene, launch_action=action if use_cli_flags else None,
            )
            with obs_tunnel(host, ssh_port, ssh_user, ssh_key_pem, ws_port) as local_port:
                if not use_cli_flags:
                    # CLI flags not used — use WebSocket to switch scene and start action.
                    start_action(local_port, obs_password, action)
            logger.info("OBS %s started successfully on %s.", action, server_id)

            # Publish StreamStarted event for streaming actions (fire-and-forget)
            if action == "streaming":
                try:
                    platform_sb_conn = os.environ.get("PLATFORM_SERVICE_BUS_CONNECTION", "")
                    platform_sb_topic = os.environ.get("PLATFORM_SERVICE_BUS_TOPIC", "")
                    location = server.get("location", "")
                    if platform_sb_conn and platform_sb_topic:
                        publish_stream_started(
                            platform_sb_conn, platform_sb_topic, location, title=title,
                        )
                except Exception as exc:
                    logger.error(
                        "StreamStarted event publish failed: %s", exc,
                    )

        elif command == "stop":
            logger.info("Stopping OBS on %s (%s) — action: %s", server_id, host, action)
            with obs_tunnel(host, ssh_port, ssh_user, ssh_key_pem, ws_port) as local_port:
                stop_action(local_port, obs_password, action)
            if platform == "windows" and close_exe_path:
                run_close_exe(host, ssh_port, ssh_user, ssh_key_pem, close_exe_path)
            else:
                kill_obs(host, ssh_port, ssh_user, ssh_key_pem, platform)
            logger.info("OBS %s stopped successfully on %s.", action, server_id)

        else:
            logger.error("Unknown command '%s'. Expected 'start' or 'stop'.", command)

    except Exception as exc:
        delivery_count = getattr(msg, "delivery_count", OBS_JOBS_MAX_DELIVERY_COUNT)
        is_final_attempt = delivery_count >= OBS_JOBS_MAX_DELIVERY_COUNT
        log = logger.error if is_final_attempt else logger.warning
        log(
            "OBSControl failed for %s/%s on %s (attempt %d/%d): %s",
            command, action, server_id,
            delivery_count, OBS_JOBS_MAX_DELIVERY_COUNT, exc,
        )
        raise  # Re-raise so Service Bus can retry / dead-letter the message


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

from health import check_health  # noqa: E402


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Deep health check against all backing services."""
    sb_conn = os.environ.get("SERVICE_BUS_CONNECTION", "")
    platform_sb_conn = os.environ.get("PLATFORM_SERVICE_BUS_CONNECTION", "")
    platform_sb_topic = os.environ.get("PLATFORM_SERVICE_BUS_TOPIC", "")
    kv_uri = os.environ.get("KEY_VAULT_URI", "")

    result = check_health(
        sb_connection=sb_conn,
        platform_sb_connection=platform_sb_conn,
        platform_sb_topic=platform_sb_topic,
        kv_uri=kv_uri,
    )

    status_code = 200 if result["status"] == "healthy" else 503

    return func.HttpResponse(
        body=json.dumps(result, indent=2),
        status_code=status_code,
        mimetype="application/json",
    )
