"""The kHealth Wellness integration."""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import KhealthCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up kHealth from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = aiohttp.ClientSession()
    coordinator = KhealthCoordinator(hass, entry, session)

    # Store before first refresh so unload can clean up on failure
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
    }

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # On failure, close the session — HA will retry via SETUP_RETRY
        await session.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a kHealth config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    session = data.get("session")
    if session and not session.closed:
        await session.close()
    return True
