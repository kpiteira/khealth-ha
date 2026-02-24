"""Tests for the kHealth config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.khealth.config_flow import CannotConnect, InvalidAuth
from custom_components.khealth.const import (
    CONF_API_TOKEN,
    CONF_NOTIFY_DEVICE,
    CONF_URL,
    DOMAIN,
)

VALID_USER_INPUT = {
    CONF_URL: "http://khealth.example.com",
    CONF_API_TOKEN: "test-token-123",
}

ME_RESPONSE = {"id": 1, "email": "karl@example.com", "display_name": "Karl", "external_id": "ext-1", "role": "admin"}


async def _register_mobile_app_services(hass: HomeAssistant, *device_names: str) -> None:
    """Register mock mobile_app notify services on the hass instance."""
    for name in device_names:
        hass.services.async_register("notify", name, AsyncMock())


# --- Step 1: User input (URL + token) ---


async def test_step_user_shows_form(hass: HomeAssistant) -> None:
    """Test that step 1 shows a form for URL + token."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_step_user_valid_credentials_proceeds_to_device(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: valid URL + token → proceeds to step 2 (device selection)."""
    await _register_mobile_app_services(hass, "mobile_app_karls_iphone")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        return_value=ME_RESPONSE,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"


async def test_step_user_invalid_token_shows_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: invalid token → shows 'invalid_auth' error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_step_user_unreachable_url_shows_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: unreachable URL → shows 'cannot_connect' error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


# --- Step 2: Device selection ---


async def test_step_device_lists_mobile_app_services(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: step 2 lists available mobile_app_* services."""
    await _register_mobile_app_services(
        hass, "mobile_app_karls_iphone", "mobile_app_karls_ipad"
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        return_value=ME_RESPONSE,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"
    # Verify both devices are in the schema options
    schema_dict = dict(result["data_schema"].schema)
    device_key = next(k for k in schema_dict if str(k) == CONF_NOTIFY_DEVICE)
    validator = schema_dict[device_key]
    # vol.In stores the container as .container
    assert "mobile_app_karls_iphone" in validator.container
    assert "mobile_app_karls_ipad" in validator.container


async def test_step_device_no_mobile_app_shows_error(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: no mobile_app services → shows 'no_devices' error."""
    # Register only a non-mobile_app service
    hass.services.async_register("notify", "persistent_notification", AsyncMock())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        return_value=ME_RESPONSE,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_devices"}


async def test_step_device_creates_entry(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: selecting device creates config entry with correct data."""
    await _register_mobile_app_services(hass, "mobile_app_karls_iphone")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        return_value=ME_RESPONSE,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NOTIFY_DEVICE: "mobile_app_karls_iphone"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "kHealth"
    assert result["data"] == {
        CONF_URL: "http://khealth.example.com",
        CONF_API_TOKEN: "test-token-123",
        CONF_NOTIFY_DEVICE: "mobile_app_karls_iphone",
    }


async def test_duplicate_account_aborts(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test: same khealth user_id → abort with 'already_configured'."""
    MockConfigEntry(
        domain=DOMAIN,
        title="kHealth",
        data=VALID_USER_INPUT,
        unique_id="khealth_1",
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.khealth.config_flow.KhealthConfigFlow._validate_credentials",
        return_value=ME_RESPONSE,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_USER_INPUT,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
