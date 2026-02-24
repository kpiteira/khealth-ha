"""Global fixtures for kHealth HA integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.khealth.const import (
    CONF_API_TOKEN,
    CONF_NOTIFY_DEVICE,
    CONF_URL,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="kHealth",
        data={
            CONF_URL: "http://khealth.example.com",
            CONF_API_TOKEN: "test-token-123",
            CONF_NOTIFY_DEVICE: "mobile_app_karls_iphone",
        },
        unique_id="khealth_1",
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry to avoid full setup during config flow tests."""
    with patch(
        "custom_components.khealth.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup
