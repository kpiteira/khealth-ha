"""Constants for the kHealth integration."""

from __future__ import annotations

import hashlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

DOMAIN = "khealth"
CONF_URL = "url"
CONF_API_TOKEN = "api_token"
CONF_NOTIFY_DEVICE = "notify_device"
DEFAULT_SCAN_INTERVAL = 60


def unique_id_prefix(entry: ConfigEntry) -> str:
    """Build a stable unique_id prefix from URL + user_id.

    Uses SHA-256 hash of url + user_id so unique_id survives integration
    re-installs (entry.entry_id changes, but url + user_id don't).
    """
    url = entry.data[CONF_URL]
    user_id = entry.unique_id.removeprefix("khealth_")
    return hashlib.sha256(f"{url}_{user_id}".encode()).hexdigest()[:16]


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return shared device info for all kHealth entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="kHealth Wellness",
        manufacturer="kHealth",
        model="Wellness Tracker",
        entry_type=DeviceEntryType.SERVICE,
    )
