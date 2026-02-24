"""DataUpdateCoordinator for kHealth integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_API_TOKEN, CONF_URL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class KhealthCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the kHealth API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._session = session
        self._url = config_entry.data[CONF_URL].rstrip("/")
        self._token = config_entry.data[CONF_API_TOKEN]

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll GET /api/v1/ha/poll."""
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with self._session.get(
                f"{self._url}/api/v1/ha/poll",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    raise UpdateFailed("Invalid API token (401)")
                if resp.status == 403:
                    raise UpdateFailed("Forbidden (403)")
                if resp.status != 200:
                    raise UpdateFailed(f"Unexpected status {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with kHealth API: {err}") from err
