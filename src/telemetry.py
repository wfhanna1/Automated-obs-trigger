"""
telemetry.py — Azure Monitor OpenTelemetry configuration.

Call configure_telemetry() once at app startup to enable Application Insights
log/trace/exception collection for the Azure Functions host.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

ENV_VAR = "APPLICATIONINSIGHTS_CONNECTION_STRING"

try:
    from azure.monitor.opentelemetry import configure_azure_monitor
except ImportError:
    configure_azure_monitor: Any = None  # type: ignore[no-redef]


def configure_telemetry() -> None:
    """Set up Azure Monitor OpenTelemetry if a connection string is available."""
    if configure_azure_monitor is None:
        logger.warning(
            "azure-monitor-opentelemetry is not installed -- "
            "Application Insights telemetry is disabled."
        )
        return

    connection_string = os.environ.get(ENV_VAR)

    if not connection_string:
        logger.warning(
            "%s is not set -- Application Insights telemetry is disabled.", ENV_VAR
        )
        return

    try:
        configure_azure_monitor(connection_string=connection_string)
    except Exception as exc:
        logger.error("Failed to configure Azure Monitor telemetry: %s", exc)
