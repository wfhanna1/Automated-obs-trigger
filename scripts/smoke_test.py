#!/usr/bin/env python3
"""
smoke_test.py -- Post-deployment smoke test for the OBS Service Bus pipeline.

Sends one Service Bus message to obs-jobs and confirms the OBSControl function
consumes it without dead-lettering it. If dead-lettered, fetches the exception
from App Insights and prints it so the failure is immediately actionable.

Exit codes:
  0 -- message consumed successfully
  1 -- message dead-lettered (App Insights exception printed to stdout)
  2 -- timeout: message neither consumed nor dead-lettered within the wait window
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.servicebus.management import ServiceBusAdministrationClient

QUEUE_NAME = "obs-jobs"
POLL_INTERVAL_SECONDS = 15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post-deployment smoke test for the OBS Service Bus pipeline."
    )
    parser.add_argument("--sb-connection-string", required=True,
                        help="Azure Service Bus connection string")
    parser.add_argument("--app-insights-name", required=True,
                        help="App Insights component name (e.g. obs-scheduler-ai-xheofbriqbtrw)")
    parser.add_argument("--resource-group", default="obs-scheduler-rg",
                        help="Azure resource group containing the App Insights component")
    parser.add_argument("--server-id", default="win-server-1",
                        help="Server ID matching an entry in servers.yaml")
    parser.add_argument("--action", default="recording",
                        help="OBS action: recording or streaming")
    parser.add_argument("--command", default="start",
                        help="Command to send: start or stop")
    parser.add_argument("--max-wait-seconds", type=int, default=600,
                        help="Maximum seconds to wait for the message to be processed")
    return parser.parse_args()


def build_payload(server_id: str, action: str, command: str) -> str:
    return json.dumps({"command": command, "server_id": server_id, "action": action})


def get_queue_counts(admin_client: ServiceBusAdministrationClient) -> tuple[int, int]:
    """Return (active_message_count, dead_letter_message_count) for obs-jobs."""
    props = admin_client.get_queue_runtime_properties(QUEUE_NAME)
    return props.active_message_count, props.dead_letter_message_count


def send_message(connection_string: str, payload: str) -> None:
    with ServiceBusClient.from_connection_string(connection_string) as client:
        with client.get_queue_sender(QUEUE_NAME) as sender:
            sender.send_messages(ServiceBusMessage(payload))


def fetch_app_insights_exceptions(
    app_insights_name: str,
    resource_group: str,
    since_iso: str,
) -> str:
    """Query App Insights for exceptions since sent_at and return the raw output."""
    kql = (
        "exceptions"
        f" | where timestamp >= datetime('{since_iso}')"
        " | project timestamp, type, outerMessage, innermostMessage"
        " | order by timestamp asc"
    )
    result = subprocess.run(
        [
            "az", "monitor", "app-insights", "query",
            "--app", app_insights_name,
            "--resource-group", resource_group,
            "--analytics-query", kql,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"[App Insights query failed]\nstderr: {result.stderr.strip()}"
    return result.stdout.strip()


def main() -> None:
    args = parse_args()

    admin_client = ServiceBusAdministrationClient.from_connection_string(
        args.sb_connection_string
    )

    print(f"[smoke_test] Recording baseline queue counts for '{QUEUE_NAME}'...")
    baseline_active, baseline_dlq = get_queue_counts(admin_client)
    print(f"[smoke_test]   active={baseline_active}, dlq={baseline_dlq}")

    payload = build_payload(args.server_id, args.action, args.command)
    sent_at = datetime.now(timezone.utc)
    sent_at_iso = sent_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"[smoke_test] Sending message at {sent_at_iso}: {payload}")
    send_message(args.sb_connection_string, payload)
    print(
        f"[smoke_test] Polling every {POLL_INTERVAL_SECONDS}s "
        f"(max {args.max_wait_seconds}s)..."
    )

    deadline = time.monotonic() + args.max_wait_seconds
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)

        active, dlq = get_queue_counts(admin_client)
        print(f"[smoke_test]   active={active}, dlq={dlq}")

        if dlq > baseline_dlq:
            print("[smoke_test] FAIL: Message was dead-lettered.")
            print("[smoke_test] Fetching exceptions from App Insights...")
            output = fetch_app_insights_exceptions(
                args.app_insights_name, args.resource_group, sent_at_iso
            )
            print(output)
            sys.exit(1)

        if active <= baseline_active:
            print("[smoke_test] PASS: Message consumed successfully.")
            sys.exit(0)

    print(
        f"[smoke_test] TIMEOUT: Message not processed within {args.max_wait_seconds}s."
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
