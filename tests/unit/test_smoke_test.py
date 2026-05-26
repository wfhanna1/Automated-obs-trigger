"""Tests for scripts/smoke_test.py cleanup behavior.

The smoke test exercises the obs-jobs Service Bus queue against a live OBS
host. When the command under test is "start", the script must also enqueue
a matching "stop" so the remote OBS does not keep recording after the run.
The stop must be enqueued even if the start phase fails verification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# scripts/smoke_test.py is not a package, so add scripts/ to sys.path.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import smoke_test  # noqa: E402


@pytest.fixture
def args_start():
    """Argparse-like namespace targeting a start command."""
    import argparse
    return argparse.Namespace(
        sb_connection_string="Endpoint=sb://fake.servicebus.windows.net/;SharedAccessKeyName=x;SharedAccessKey=y",
        app_insights_name="fake-ai",
        resource_group="fake-rg",
        server_id="win-server-1",
        action="recording",
        command="start",
        max_wait_seconds=1,
    )


def _payloads(sent: list[str]) -> list[dict]:
    return [json.loads(p) for p in sent]


def test_start_command_enqueues_matching_stop_after_success(monkeypatch, args_start):
    """When start verification passes, a stop must also be enqueued for cleanup."""
    sent: list[str] = []

    def fake_send(_conn: str, payload: str) -> None:
        sent.append(payload)

    def fake_counts(_admin):  # Active drops immediately -> "consumed".
        return 0, 0

    monkeypatch.setattr(smoke_test, "send_message", fake_send)
    monkeypatch.setattr(smoke_test, "get_queue_counts", fake_counts)
    monkeypatch.setattr(smoke_test.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        smoke_test.ServiceBusAdministrationClient,
        "from_connection_string",
        classmethod(lambda cls, _c: object()),
    )

    smoke_test.run(args_start)

    payloads = _payloads(sent)
    assert len(payloads) == 2, f"expected start+stop, got {payloads}"
    assert payloads[0]["command"] == "start"
    assert payloads[1] == {
        "command": "stop",
        "server_id": "win-server-1",
        "action": "recording",
    }


def test_start_command_enqueues_stop_even_when_start_phase_dead_letters(
    monkeypatch, args_start
):
    """Cleanup stop must run even when the start phase dead-letters."""
    sent: list[str] = []
    state = {"calls": 0}

    def fake_send(_conn: str, payload: str) -> None:
        sent.append(payload)

    def fake_counts(_admin):
        # Start baseline: 0,0. Start poll: dlq jumps to 1 -> fail.
        # Stop baseline: snapshot post-fail. Stop poll: queue drains -> success.
        state["calls"] += 1
        if state["calls"] == 1:
            return 0, 0
        if state["calls"] == 2:
            return 1, 1
        return 1, 1  # baseline for stop phase, then equal -> consumed

    monkeypatch.setattr(smoke_test, "send_message", fake_send)
    monkeypatch.setattr(smoke_test, "get_queue_counts", fake_counts)
    monkeypatch.setattr(smoke_test, "fetch_app_insights_exceptions",
                        lambda *_a, **_kw: "fake exception output")
    monkeypatch.setattr(smoke_test.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        smoke_test.ServiceBusAdministrationClient,
        "from_connection_string",
        classmethod(lambda cls, _c: object()),
    )

    rc = smoke_test.run(args_start)

    assert rc != 0, "primary failure must surface as non-zero exit"
    payloads = _payloads(sent)
    assert len(payloads) == 2, (
        f"cleanup stop must be enqueued even on start failure, got {payloads}"
    )
    assert payloads[0]["command"] == "start"
    assert payloads[1]["command"] == "stop"


