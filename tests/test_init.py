"""Tests for kHealth integration setup and unload."""

from __future__ import annotations

from aioresponses import aioresponses

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.khealth.const import CONF_URL, DOMAIN

POLL_RESPONSE = {
    "active_reminders": {"movement": None, "hydration": None},
    "today": {"movement": {"done": 0, "total": 8}, "hydration": {"done": 0, "total": 6}},
    "streaks": {"movement": 0, "hydration": 0},
    "schedule": {"in_window": True, "window_start": "08:00", "window_end": "17:00", "timezone": "Europe/Berlin"},
}


def _poll_url(entry: MockConfigEntry) -> str:
    return f"{entry.data[CONF_URL].rstrip('/')}/api/v1/ha/poll"


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test integration loads without errors."""
    with aioresponses() as mock_api:
        mock_api.get(_poll_url(mock_config_entry), payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test integration unloads cleanly."""
    with aioresponses() as mock_api:
        mock_api.get(_poll_url(mock_config_entry), payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    result = await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert result is True
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]
