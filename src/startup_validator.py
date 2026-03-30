"""
startup_validator.py -- Validate required environment variables at startup.

Raises RuntimeError listing all missing vars so the function app fails to start
instead of silently degrading.
"""

from __future__ import annotations

import os

REQUIRED_VARS = [
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "PLATFORM_SERVICE_BUS_CONNECTION",
    "PLATFORM_SERVICE_BUS_TOPIC",
]


def validate_required_config(config: dict[str, str] | None = None) -> None:
    """Validate all required env vars are present.

    Args:
        config: Optional dict to validate. If None, reads from os.environ.

    Raises:
        RuntimeError: If any required vars are missing.
    """
    source = config if config is not None else dict(os.environ)
    missing = [v for v in REQUIRED_VARS if not source.get(v)]

    if missing:
        raise RuntimeError(
            f"Missing required configuration: {', '.join(missing)}. "
            "The function app cannot start without these environment variables."
        )
