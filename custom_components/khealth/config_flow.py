"""Config flow for kHealth integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_TOKEN, CONF_NOTIFY_DEVICE, CONF_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_TOKEN): str,
    }
)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""


class KhealthConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for kHealth."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._url: str | None = None
        self._api_token: str | None = None
        self._user_id: int | None = None

    async def _validate_credentials(self, url: str, token: str) -> dict[str, Any]:
        """Validate credentials by calling the kHealth API.

        Calls GET /api/v1/ha/poll to check connectivity and auth,
        then GET /api/v1/me to get the user ID for unique_id.

        Returns the /api/v1/me response dict.
        Raises CannotConnect or InvalidAuth on failure.
        """
        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(
                f"{url.rstrip('/')}/api/v1/ha/poll",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status != 200:
                    raise CannotConnect(f"Unexpected status {resp.status}")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err

        try:
            async with session.get(
                f"{url.rstrip('/')}/api/v1/me",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise CannotConnect(f"Failed to get user info: {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err

    def _discover_mobile_devices(self) -> list[str]:
        """Discover available mobile_app notification services."""
        services = self.hass.services.async_services()
        notify_services = services.get("notify", {})
        return [
            name
            for name in notify_services
            if name.startswith("mobile_app_")
        ]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 1: URL + API token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL]
            token = user_input[CONF_API_TOKEN]

            try:
                me = await self._validate_credentials(url, token)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during validation")
                errors["base"] = "unknown"
            else:
                # Set unique_id to prevent duplicate entries for the same user
                user_id = me["id"]
                await self.async_set_unique_id(f"khealth_{user_id}")
                self._abort_if_unique_id_configured()

                # Check for mobile devices before proceeding
                devices = self._discover_mobile_devices()
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    self._url = url
                    self._api_token = token
                    self._user_id = user_id
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 2: notification device selection."""
        if user_input is not None:
            return self.async_create_entry(
                title="kHealth",
                data={
                    CONF_URL: self._url,
                    CONF_API_TOKEN: self._api_token,
                    CONF_NOTIFY_DEVICE: user_input[CONF_NOTIFY_DEVICE],
                },
            )

        devices = self._discover_mobile_devices()
        device_schema = vol.Schema(
            {
                vol.Required(CONF_NOTIFY_DEVICE): vol.In(devices),
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=device_schema,
        )
