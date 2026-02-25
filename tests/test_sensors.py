"""Tests for kHealth sensor and binary_sensor entities."""

from __future__ import annotations

import hashlib

from aioresponses import aioresponses

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

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


def _expected_unique_id_prefix(entry: MockConfigEntry) -> str:
    """Build the expected unique_id prefix from entry data."""
    url = entry.data["url"]
    # user_id extracted from entry.unique_id "khealth_{user_id}"
    user_id = entry.unique_id.removeprefix("khealth_")
    return hashlib.sha256(f"{url}_{user_id}".encode()).hexdigest()[:16]


async def _setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    poll_response: dict | None = None,
) -> None:
    """Set up the integration with a mocked API response."""
    response = poll_response or POLL_RESPONSE
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=response)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED


# --- Movement Today Sensor ---


async def test_movement_today_sensor_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test movement_today sensor shows correct done/total."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state is not None
    assert state.state == "6/8"
    assert state.attributes["done"] == 6
    assert state.attributes["total"] == 8


# --- Hydration Today Sensor ---


async def test_hydration_today_sensor_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test hydration_today sensor shows correct done/total."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.khealth_wellness_hydration_today")
    assert state is not None
    assert state.state == "4/6"
    assert state.attributes["done"] == 4
    assert state.attributes["total"] == 6


# --- Movement Streak Sensor ---


async def test_movement_streak_sensor_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test movement_streak sensor shows correct integer value."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.khealth_wellness_movement_streak")
    assert state is not None
    assert state.state == "5"


# --- Hydration Streak Sensor ---


async def test_hydration_streak_sensor_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test hydration_streak sensor shows correct value."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.khealth_wellness_hydration_streak")
    assert state is not None
    assert state.state == "3"


# --- Schedule Sensor ---


async def test_schedule_sensor_active(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test schedule sensor shows 'active' when in_window is true."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.khealth_wellness_schedule")
    assert state is not None
    assert state.state == "active"
    assert state.attributes["window_start"] == "08:00"
    assert state.attributes["window_end"] == "17:00"
    assert state.attributes["timezone"] == "Europe/Berlin"


async def test_schedule_sensor_inactive(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test schedule sensor shows 'inactive' when in_window is false."""
    response = {**POLL_RESPONSE, "schedule": {**POLL_RESPONSE["schedule"], "in_window": False}}
    await _setup_integration(hass, mock_config_entry, poll_response=response)

    state = hass.states.get("sensor.khealth_wellness_schedule")
    assert state is not None
    assert state.state == "inactive"


# --- Reminder Pending Binary Sensor ---


async def test_reminder_pending_on_when_active(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reminder_pending binary sensor is on when any reminder is active."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("binary_sensor.khealth_wellness_reminder_pending")
    assert state is not None
    assert state.state == "on"


async def test_reminder_pending_off_when_none(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reminder_pending is off when no reminders are active."""
    response = {**POLL_RESPONSE, "active_reminders": {"movement": None, "hydration": None}}
    await _setup_integration(hass, mock_config_entry, poll_response=response)

    state = hass.states.get("binary_sensor.khealth_wellness_reminder_pending")
    assert state is not None
    assert state.state == "off"


async def test_reminder_pending_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reminder_pending attributes include type, exercise, message."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("binary_sensor.khealth_wellness_reminder_pending")
    assert state is not None
    assert state.attributes["type"] == "movement"
    assert state.attributes["exercise"] == "air squats"
    assert state.attributes["message"] == "Air squats x 10"
    assert state.attributes["sent_at"] == "2026-02-23T14:30:00Z"


# --- Unique ID and Device ---


async def test_all_entities_have_unique_id_and_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test all 6 entities exist in the registry and share the kHealth Wellness device."""
    await _setup_integration(hass, mock_config_entry)

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    prefix = _expected_unique_id_prefix(mock_config_entry)

    expected_suffixes = [
        "movement_today",
        "hydration_today",
        "movement_streak",
        "hydration_streak",
        "schedule",
        "reminder_pending",
    ]

    device_ids = set()
    for suffix in expected_suffixes:
        platform = "binary_sensor" if suffix == "reminder_pending" else "sensor"
        entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, f"{prefix}_{suffix}")
        assert entity_id is not None, f"Entity with unique_id {prefix}_{suffix} not found"

        entry = ent_reg.async_get(entity_id)
        assert entry is not None
        if entry.device_id:
            device_ids.add(entry.device_id)

    # All entities belong to the same device
    assert len(device_ids) == 1, f"Expected 1 device, found {len(device_ids)}"

    # Verify the device name
    device = dev_reg.async_get(device_ids.pop())
    assert device is not None
    assert device.name == "kHealth Wellness"
    assert device.manufacturer == "kHealth"


# --- Data Update ---


async def test_sensor_updates_when_coordinator_refreshes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor state updates when coordinator fetches new data."""
    await _setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state.state == "6/8"

    # Coordinator refreshes with updated data (movement done 6→7)
    updated_response = {
        **POLL_RESPONSE,
        "today": {
            **POLL_RESPONSE["today"],
            "movement": {"done": 7, "total": 8},
        },
    }
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=updated_response)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state.state == "7/8"
    assert state.attributes["done"] == 7


# --- Unavailable / Recovery ---


async def test_entities_unavailable_when_coordinator_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test entities become unavailable when coordinator fails."""
    import aiohttp
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    with aioresponses() as mock_api:
        # First refresh: success
        mock_api.get(POLL_URL, payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state is not None
    assert state.state == "6/8"

    # Simulate coordinator failure
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state is not None
    assert state.state == "unavailable"


async def test_entities_restore_after_coordinator_reconnects(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test entities restore after coordinator reconnects."""
    import aiohttp
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_RESPONSE)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

    # Fail
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state.state == "unavailable"

    # Recover with updated data
    updated_response = {
        **POLL_RESPONSE,
        "today": {
            **POLL_RESPONSE["today"],
            "movement": {"done": 7, "total": 8},
        },
    }
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=updated_response)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state.state == "7/8"
