from unittest.mock import MagicMock


class TestHealthEndpoint:
    """Verify the /health endpoint returns correct status and structure."""

    def test_returns_healthy_when_all_checks_pass(self) -> None:
        from src.health import check_health

        mock_sb_client = MagicMock()
        mock_sender = MagicMock()
        mock_sb_client.get_topic_sender.return_value = mock_sender
        mock_sb_client.get_queue_sender.return_value = mock_sender
        mock_sender.create_message_batch.return_value = MagicMock()
        mock_sender.__enter__ = MagicMock(return_value=mock_sender)
        mock_sender.__exit__ = MagicMock(return_value=False)
        mock_sb_client.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_client.__exit__ = MagicMock(return_value=False)

        mock_kv_client = MagicMock()
        mock_kv_client.list_properties_of_secrets = MagicMock(return_value=iter([]))

        result = check_health(
            sb_connection="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_connection="Endpoint=sb://platform.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_topic="stream-title",
            kv_uri="https://test-vault.vault.azure.net/",
            _sb_client_factory=lambda conn: mock_sb_client,
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

        mock_sb_client = MagicMock()
        mock_sb_client.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_client.__exit__ = MagicMock(return_value=False)
        mock_sb_client.get_queue_sender.side_effect = Exception("Connection refused")
        mock_sb_client.get_topic_sender.side_effect = Exception("Connection refused")

        mock_kv_client = MagicMock()
        mock_kv_client.list_properties_of_secrets = MagicMock(return_value=iter([]))

        result = check_health(
            sb_connection="Endpoint=sb://bad.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_connection="Endpoint=sb://platform.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_topic="stream-title",
            kv_uri="https://test-vault.vault.azure.net/",
            _sb_client_factory=lambda conn: mock_sb_client,
            _kv_client_factory=lambda uri: mock_kv_client,
        )

        assert result["status"] == "unhealthy"
        assert result["checks"]["own_service_bus"]["status"] == "unhealthy"

    def test_response_includes_timestamp(self) -> None:
        from src.health import check_health

        mock_sb_client = MagicMock()
        mock_sender = MagicMock()
        mock_sb_client.get_topic_sender.return_value = mock_sender
        mock_sb_client.get_queue_sender.return_value = mock_sender
        mock_sender.create_message_batch.return_value = MagicMock()
        mock_sender.__enter__ = MagicMock(return_value=mock_sender)
        mock_sender.__exit__ = MagicMock(return_value=False)
        mock_sb_client.__enter__ = MagicMock(return_value=mock_sb_client)
        mock_sb_client.__exit__ = MagicMock(return_value=False)

        mock_kv_client = MagicMock()
        mock_kv_client.list_properties_of_secrets = MagicMock(return_value=iter([]))

        result = check_health(
            sb_connection="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_connection="Endpoint=sb://platform.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=dGVzdA==",
            platform_sb_topic="stream-title",
            kv_uri="https://test-vault.vault.azure.net/",
            _sb_client_factory=lambda conn: mock_sb_client,
            _kv_client_factory=lambda uri: mock_kv_client,
        )

        assert "timestamp" in result
