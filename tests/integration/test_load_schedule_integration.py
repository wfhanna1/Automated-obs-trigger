"""
tests/integration/test_load_schedule_integration.py

Integration tests for the LoadSchedule → Service Bus pipeline against
the live Azure environment.

All tests in this module are skipped automatically when the required
environment variables are not set, so they never block local development.

Required environment variables:
    AZURE_FUNCTION_BASE_URL  — e.g. https://obs-scheduler.azurewebsites.net
    AZURE_FUNCTION_KEY       — Function-level auth key
    SERVICE_BUS_CONNECTION   — Primary connection string for the obs-scheduler namespace
"""

import os
import time

import pytest
import requests
from azure.servicebus import ServiceBusClient

# ---------------------------------------------------------------------------
# Environment variable guards
# ---------------------------------------------------------------------------

AZURE_FUNCTION_BASE_URL = os.environ.get("AZURE_FUNCTION_BASE_URL", "")
AZURE_FUNCTION_KEY = os.environ.get("AZURE_FUNCTION_KEY", "")
SERVICE_BUS_CONNECTION = os.environ.get("SERVICE_BUS_CONNECTION", "")

_MISSING_ENV_VARS = not (
    AZURE_FUNCTION_BASE_URL and AZURE_FUNCTION_KEY and SERVICE_BUS_CONNECTION
)

pytestmark = pytest.mark.integration

skip_without_azure = pytest.mark.skipif(
    _MISSING_ENV_VARS,
    reason=(
        "Integration tests require AZURE_FUNCTION_BASE_URL, "
        "AZURE_FUNCTION_KEY, and SERVICE_BUS_CONNECTION env vars."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOAD_SCHEDULE_URL = (
    f"{AZURE_FUNCTION_BASE_URL}/api/load-schedule?code={AZURE_FUNCTION_KEY}"
)

OBS_JOBS_QUEUE = "obs-jobs"

# How long to wait after POST before checking Service Bus message count.
# The function is synchronous and enqueues messages before returning, so
# a short buffer is enough to account for any propagation delay.
SB_SETTLE_SECONDS = 2


def _peek_queue_count() -> int:
    """Return the number of active messages in the obs-jobs queue via peek."""
    with ServiceBusClient.from_connection_string(SERVICE_BUS_CONNECTION) as sb_client:
        with sb_client.get_queue_receiver(OBS_JOBS_QUEUE) as receiver:
            messages = receiver.peek_messages(max_message_count=1000)
            return len(messages)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@skip_without_azure
def test_load_schedule_returns_200_with_valid_schedule():
    """Smoke test: LoadSchedule responds 200 and body does not contain 'Error'."""
    response = requests.post(LOAD_SCHEDULE_URL, timeout=30)

    assert response.status_code == 200
    assert "Error" not in response.text


@skip_without_azure
def test_load_schedule_response_body_contains_enqueued():
    """LoadSchedule response body reports how many messages were enqueued."""
    response = requests.post(LOAD_SCHEDULE_URL, timeout=30)

    assert response.status_code == 200
    assert "Enqueued" in response.text


@skip_without_azure
def test_load_schedule_enqueued_count_is_positive():
    """The enqueued count in the response body must be greater than zero."""
    response = requests.post(LOAD_SCHEDULE_URL, timeout=30)

    assert response.status_code == 200
    body = response.text
    # Response format: "Enqueued N message(s)."
    # Extract N and verify it is a positive integer.
    assert "Enqueued" in body
    words = body.split()
    enqueued_index = words.index("Enqueued")
    count = int(words[enqueued_index + 1])
    assert count > 0


@skip_without_azure
def test_load_schedule_increases_service_bus_message_count():
    """
    End-to-end pipeline test: calling LoadSchedule must result in more
    messages in the obs-jobs queue than were there before the call.

    This validates that messages are actually delivered to Service Bus,
    not just that the HTTP response claims success.
    """
    count_before = _peek_queue_count()

    response = requests.post(LOAD_SCHEDULE_URL, timeout=30)
    assert response.status_code == 200

    time.sleep(SB_SETTLE_SECONDS)

    count_after = _peek_queue_count()

    assert count_after > count_before, (
        f"Service Bus message count did not increase after LoadSchedule call. "
        f"Before: {count_before}, After: {count_after}. "
        f"Function response: {response.text}"
    )
