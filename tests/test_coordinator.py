"""Tests for the kHealth DataUpdateCoordinator."""

from __future__ import annotations

from datetime import timedelta

from aioresponses import aioresponses

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.khealth.const import DOMAIN

POLL_URL = "http://khealth.example.com/api/v1/ha/poll"

POLL_RESPONSE = {
    "active_reminders": {
        "movement": {
            "id": 42,
            "type": "movement",
            "message": "Air squats x 10",
            "exercise": "air_squats",
            "exercise_label": "air squats",
            "suggested_count": 10,
            "sent_at": "2026-02-23T14:30:00Z",
            "refired_at": None,
        },
        "hydration": None,
    },
    "today": {
        "movement": {"done": 6, "total": 8},
        "hydration": {"done": 4, "total": 6},
    },
    "streaks": {"movement": 5, "hydration": 3},
    "schedule": {
        "in_window": True,
        "window_start": "08:00",
        "window_end": "17:00",
        "timezone": "Europe/Berlin",
    },
}


async def test_coordinator_first_refresh_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator fetches data successfully on first refresh."""
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    assert coordinator.data is not None
    assert coordinator.last_update_success is True


async def test_coordinator_data_matches_poll_response(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator data matches the poll response shape."""
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    data = coordinator.data
    assert data["active_reminders"]["movement"]["id"] == 42
    assert data["active_reminders"]["hydration"] is None
    assert data["today"]["movement"]["done"] == 6
    assert data["streaks"]["movement"] == 5
    assert data["schedule"]["in_window"] is True


async def test_coordinator_raises_update_failed_on_401(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator raises UpdateFailed on HTTP 401."""
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, status=401)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # First refresh fails → HA sets SETUP_RETRY (will retry later)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    # Data cleaned up on failure
    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_coordinator_raises_update_failed_on_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator raises UpdateFailed on connection error."""
    import aiohttp

    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_coordinator_polls_at_60_second_interval(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator polls at 60-second interval."""
    from custom_components.khealth.coordinator import KhealthCoordinator

    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    assert isinstance(coordinator, KhealthCoordinator)
    assert coordinator.update_interval == timedelta(seconds=60)


async def test_coordinator_session_cleanup_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test session is created and cleaned up properly on unload."""
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    session = hass.data[DOMAIN][mock_config_entry.entry_id]["session"]
    assert not session.closed

    result = await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert result is True
    assert session.closed
