import pytest
from unittest.mock import patch


class TestStartupValidation:
    """Verify that missing required env vars cause a hard failure at startup."""

    REQUIRED_VARS = {
        "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
        "PLATFORM_SERVICE_BUS_CONNECTION": "Endpoint=sb://test.servicebus.windows.net/",
        "PLATFORM_SERVICE_BUS_TOPIC": "stream-title",
    }

    @pytest.mark.parametrize("missing_var", [
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "PLATFORM_SERVICE_BUS_CONNECTION",
        "PLATFORM_SERVICE_BUS_TOPIC",
    ])
    def test_raises_when_required_var_missing(self, missing_var: str) -> None:
        from src.startup_validator import validate_required_config

        config = dict(self.REQUIRED_VARS)
        del config[missing_var]

        with pytest.raises(RuntimeError, match=missing_var):
            validate_required_config(config)

    def test_passes_when_all_present(self) -> None:
        from src.startup_validator import validate_required_config

        validate_required_config(dict(self.REQUIRED_VARS))
