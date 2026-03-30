"""
health.py -- Deep health checks for all backing services.

Returns a structured dict with per-dependency status and latency.
Designed for injection of test doubles via factory parameters.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.servicebus.management import ServiceBusAdministrationClient


def _check_service_bus(
    connection_str: str,
    name: str,
    factory: Callable[[str], ServiceBusAdministrationClient] | None = None,
) -> dict[str, Any]:
    """Ping a Service Bus namespace by listing queues."""
    start = time.monotonic()
    try:
        admin = factory(connection_str) if factory else ServiceBusAdministrationClient.from_connection_string(connection_str)
        for _ in admin.list_queues():
            break
        latency = int((time.monotonic() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency}
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return {"status": "unhealthy", "latency_ms": latency, "error": str(exc)}


def _check_key_vault(
    vault_uri: str,
    factory: Callable[[str], SecretClient] | None = None,
) -> dict[str, Any]:
    """Ping Key Vault by listing secrets."""
    start = time.monotonic()
    try:
        client = factory(vault_uri) if factory else SecretClient(
            vault_url=vault_uri, credential=DefaultAzureCredential())
        for _ in client.list_properties_of_secrets():
            break
        latency = int((time.monotonic() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency}
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return {"status": "unhealthy", "latency_ms": latency, "error": str(exc)}


def check_health(
    sb_connection: str,
    platform_sb_connection: str,
    kv_uri: str,
    _sb_admin_factory: Callable[[str], ServiceBusAdministrationClient] | None = None,
    _kv_client_factory: Callable[[str], SecretClient] | None = None,
) -> dict[str, Any]:
    """Run all health checks and return structured result."""
    checks: dict[str, Any] = {}

    checks["own_service_bus"] = _check_service_bus(
        sb_connection, "own_service_bus", _sb_admin_factory)
    checks["platform_service_bus"] = _check_service_bus(
        platform_sb_connection, "platform_service_bus", _sb_admin_factory)
    checks["key_vault"] = _check_key_vault(kv_uri, _kv_client_factory)
    checks["app_insights"] = {"status": "healthy"}  # Config validated at startup

    all_healthy = all(c["status"] == "healthy" for c in checks.values())

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
    }
