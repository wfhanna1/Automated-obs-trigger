"""
tests/unit/test_telemetry.py

Unit tests for src/telemetry.py :: configure_telemetry()

These tests are written against the expected contract of the module.
They WILL FAIL until src/telemetry.py is implemented.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from unittest.mock import patch
import pytest


# ---------------------------------------------------------------------------
# Happy path: env var is set
# ---------------------------------------------------------------------------

class TestConfigureTelemetryHappyPath:

    @patch("telemetry.configure_azure_monitor")
    def test_telemetry_calls_configure_azure_monitor_when_connection_string_is_set(
        self, mock_configure, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "InstrumentationKey=fake-key-1234",
        )
        from telemetry import configure_telemetry

        # Act
        configure_telemetry()

        # Assert
        mock_configure.assert_called_once()

    @patch("telemetry.configure_azure_monitor")
    def test_telemetry_passes_connection_string_to_configure_azure_monitor(
        self, mock_configure, monkeypatch
    ):
        # Arrange
        connection_string = "InstrumentationKey=fake-key-1234"
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", connection_string)
        from telemetry import configure_telemetry

        # Act
        configure_telemetry()

        # Assert
        _call_kwargs = mock_configure.call_args
        assert connection_string in (
            _call_kwargs.args + tuple(_call_kwargs.kwargs.values())
        )


# ---------------------------------------------------------------------------
# Missing env var: no connection string
# ---------------------------------------------------------------------------

class TestConfigureTelemetryMissingEnvVar:

    @patch("telemetry.configure_azure_monitor")
    def test_telemetry_does_not_call_configure_azure_monitor_when_connection_string_is_missing(
        self, mock_configure, monkeypatch
    ):
        # Arrange
        monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
        from telemetry import configure_telemetry

        # Act
        configure_telemetry()

        # Assert
        mock_configure.assert_not_called()

    @patch("telemetry.configure_azure_monitor")
    def test_telemetry_logs_warning_when_connection_string_is_missing(
        self, mock_configure, monkeypatch, caplog
    ):
        # Arrange
        monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
        from telemetry import configure_telemetry

        # Act
        with caplog.at_level(logging.WARNING, logger="telemetry"):
            configure_telemetry()

        # Assert
        assert len(caplog.records) >= 1
        assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# SDK error handling: configure_azure_monitor raises
# ---------------------------------------------------------------------------

class TestConfigureTelemetryImportFailure:

    def test_telemetry_does_not_crash_when_azure_monitor_package_is_missing(
        self, monkeypatch, caplog
    ):
        """configure_telemetry() must not crash if azure-monitor-opentelemetry
        is not installed. It should log a warning and return gracefully."""
        # Arrange
        monkeypatch.setenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "InstrumentationKey=fake-key-1234",
        )
        import telemetry as tel_module
        # Simulate the package being absent by setting the module-level ref to None
        monkeypatch.setattr(tel_module, "configure_azure_monitor", None)

        # Act & Assert: must not crash
        with caplog.at_level(logging.WARNING, logger="telemetry"):
            try:
                tel_module.configure_telemetry()
            except (ImportError, TypeError):
                pytest.fail(
                    "configure_telemetry() crashed when azure-monitor-opentelemetry "
                    "is not available. It should handle this gracefully."
                )

        # Assert — a warning must be logged about the missing package
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, (
            "Expected a WARNING-level log when azure-monitor-opentelemetry is not "
            "installed, but none were emitted."
        )


class TestConfigureTelemetrySdkError:

    @patch("telemetry.configure_azure_monitor", side_effect=RuntimeError("SDK init failed"))
    def test_telemetry_does_not_crash_when_configure_azure_monitor_raises(
        self, mock_configure, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "InstrumentationKey=fake-key-1234",
        )
        from telemetry import configure_telemetry

        # Act & Assert: must not propagate the exception
        try:
            configure_telemetry()
        except Exception as exc:
            pytest.fail(
                f"configure_telemetry() raised an exception when it should not have: {exc}"
            )

    @patch("telemetry.configure_azure_monitor", side_effect=Exception("unexpected SDK error"))
    def test_telemetry_logs_error_when_configure_azure_monitor_raises(
        self, mock_configure, monkeypatch, caplog
    ):
        # Arrange
        monkeypatch.setenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "InstrumentationKey=fake-key-1234",
        )
        from telemetry import configure_telemetry

        # Act
        with caplog.at_level(logging.ERROR, logger="telemetry"):
            configure_telemetry()

        # Assert
        assert len(caplog.records) >= 1
        assert any(r.levelno == logging.ERROR for r in caplog.records)
