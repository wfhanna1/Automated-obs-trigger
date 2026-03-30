import json
from unittest.mock import AsyncMock, MagicMock, patch

import azure.functions as func
import pytest


class TestHealthEndpoint:
    """Verify the /health endpoint returns correct status and structure."""

    def test_returns_200_when_all_healthy(self) -> None:
        from src.health import check_health

        mock_sb_admin = MagicMock()
        mock_kv_client = MagicMock()
        mock_sb_admin.get_queue_runtime_properties = AsyncMock()
        mock_kv_client.list_properties_of_secrets = MagicMock(return_value=iter([]))

        result = check_health(
            sb_connection="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_connection="Endpoint=sb://platform.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            kv_uri="https://test-vault.vault.azure.net/",
            _sb_admin_factory=lambda conn: mock_sb_admin,
            _kv_client_factory=lambda uri: mock_kv_client,
        )

        assert result["status"] == "healthy"
        assert "checks" in result
        assert result["checks"]["own_service_bus"]["status"] == "healthy"
        assert result["checks"]["platform_service_bus"]["status"] == "healthy"
        assert result["checks"]["key_vault"]["status"] == "healthy"
        assert result["checks"]["app_insights"]["status"] == "healthy"

    def test_returns_unhealthy_when_service_bus_fails(self) -> None:
        from src.health import check_health

        mock_sb_admin = MagicMock()
        mock_sb_admin.list_queues = MagicMock(
            side_effect=Exception("Connection refused"))
        mock_kv_client = MagicMock()
        mock_kv_client.list_properties_of_secrets = MagicMock(return_value=iter([]))

        result = check_health(
            sb_connection="Endpoint=sb://bad.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_connection="Endpoint=sb://platform.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            kv_uri="https://test-vault.vault.azure.net/",
            _sb_admin_factory=lambda conn: mock_sb_admin,
            _kv_client_factory=lambda uri: mock_kv_client,
        )

        assert result["status"] == "unhealthy"
        assert result["checks"]["own_service_bus"]["status"] == "unhealthy"

    def test_response_includes_timestamp(self) -> None:
        from src.health import check_health

        mock_sb_admin = MagicMock()
        mock_sb_admin.get_queue_runtime_properties = AsyncMock()
        mock_kv_client = MagicMock()
        mock_kv_client.list_properties_of_secrets = MagicMock(return_value=iter([]))

        result = check_health(
            sb_connection="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_connection="Endpoint=sb://platform.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            kv_uri="https://test-vault.vault.azure.net/",
            _sb_admin_factory=lambda conn: mock_sb_admin,
            _kv_client_factory=lambda uri: mock_kv_client,
        )

        assert "timestamp" in result
