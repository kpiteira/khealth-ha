"""The kHealth Wellness integration."""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_API_TOKEN, CONF_NOTIFY_DEVICE, CONF_URL, DOMAIN
from .coordinator import KhealthCoordinator
from .notify import KhealthNotificationManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up kHealth from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = aiohttp.ClientSession()
    coordinator = KhealthCoordinator(hass, entry, session)

    notify_mgr = KhealthNotificationManager(
        hass=hass,
        notify_device=entry.data[CONF_NOTIFY_DEVICE],
        api_url=entry.data[CONF_URL],
        api_token=entry.data[CONF_API_TOKEN],
        session=session,
    )

    # Store before first refresh so unload can clean up on failure
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
        "notify_mgr": notify_mgr,
    }

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # On failure, close the session — HA will retry via SETUP_RETRY
        await session.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    # Start notification listeners after successful first refresh
    notify_mgr.start(coordinator)

    # Forward to sensor and binary_sensor platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a kHealth config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data[DOMAIN].pop(entry.entry_id, {})

    notify_mgr = data.get("notify_mgr")
    if notify_mgr:
        notify_mgr.stop()

    session = data.get("session")
    if session and not session.closed:
        await session.close()

    return unload_ok
