"""Tests for HA offline/reconnect resilience (M4 Task 4.3).

Verifies behavior when HA loses connectivity to khealth and reconnects,
including outage handling, recovery notifications, and HA restart scenarios.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import aiohttp
from aioresponses import aioresponses

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.khealth.const import DOMAIN

POLL_URL = "http://khealth.example.com/api/v1/ha/poll"

MOVEMENT_42 = {
    "id": 42,
    "type": "movement",
    "message": "Air squats x 10",
    "exercise": "air_squats",
    "exercise_label": "air squats",
    "suggested_count": 10,
    "sent_at": "2026-02-23T14:30:00Z",
    "refired_at": None,
}

MOVEMENT_43 = {
    "id": 43,
    "type": "movement",
    "message": "Push-ups x 10",
    "exercise": "push_ups",
    "exercise_label": "push-ups",
    "suggested_count": 10,
    "sent_at": "2026-02-23T15:30:00Z",
    "refired_at": None,
}

POLL_NO_REMINDERS = {
    "active_reminders": {"movement": None, "hydration": None},
    "today": {"movement": {"done": 0, "total": 8}, "hydration": {"done": 0, "total": 6}},
    "streaks": {"movement": 0, "hydration": 0},
    "schedule": {
        "in_window": True,
        "window_start": "08:00",
        "window_end": "17:00",
        "timezone": "Europe/Berlin",
    },
}

POLL_WITH_42 = {
    **POLL_NO_REMINDERS,
    "active_reminders": {"movement": MOVEMENT_42, "hydration": None},
}

POLL_WITH_43 = {
    **POLL_NO_REMINDERS,
    "active_reminders": {"movement": MOVEMENT_43, "hydration": None},
}


async def _setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    poll_response: dict,
) -> None:
    """Set up the integration with a mocked poll response."""
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=poll_response)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED


# Scenario 1: First poll with pending reminder → notification sent


async def test_first_poll_with_pending_reminder_sends_notification(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """First poll sees active reminder → sends notification."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)

    assert notify_mock.call_count == 1
    service_data = notify_mock.call_args[0][0].data
    assert service_data["message"] == "Air squats x 10"


# Scenario 2: Coordinator failure → no notifications sent


async def test_coordinator_failure_no_notification_sent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Coordinator failure on subsequent poll → no notifications sent, entities unavailable."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    # Simulate khealth unreachable
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # No new notifications sent during outage
    assert notify_mock.call_count == 0
    # Coordinator marked as failed
    assert coordinator.last_update_success is False


# Scenario 3: Reconnect after outage — same reminder still pending → no duplicate


async def test_reconnect_same_reminder_no_duplicate(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconnect: same reminder still pending → no duplicate notification."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

    # Outage
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.last_update_success is False

    # Reconnect — same reminder #42 still pending
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_42)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    # No duplicate notification (same ID still in _last_seen)
    assert notify_mock.call_count == 0


# Scenario 3b: Reconnect — NEW reminder appeared during outage → send notification


async def test_reconnect_new_reminder_sends_notification(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconnect: new reminder appeared during outage → sends notification."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

    # Outage
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Reconnect — different reminder #43
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_43)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # New notification sent for #43
    assert notify_mock.call_count == 1
    service_data = notify_mock.call_args[0][0].data
    assert service_data["message"] == "Push-ups x 10"


# Scenario 4: Reconnect — reminder changed during outage


async def test_reconnect_reminder_changed_during_outage(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconnect: reminder changed during outage → send new (old replaced via tag)."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    # Start with reminder #42
    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

    # Outage
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Reconnect with different reminder #43
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_43)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Sends new notification (replaces old via same tag, no dismiss race)
    assert notify_mock.call_count == 1
    # Verify it's the new reminder
    service_data = notify_mock.call_args[0][0].data
    assert "KHEALTH_DONE_43" in service_data["data"]["actions"][0]["action"]


# Scenario 4b: Reconnect — reminder gone during outage → dismiss


async def test_reconnect_reminder_gone_during_outage_dismisses(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconnect: reminder gone during outage → dismiss notification."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

    # Outage
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Reconnect — no reminders
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_NO_REMINDERS)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Should dismiss the old notification
    assert notify_mock.call_count == 1
    service_data = notify_mock.call_args[0][0].data
    assert service_data["message"] == "clear_notification"
    assert service_data["data"]["tag"] == "khealth-movement"


# Scenario 5: Coordinator recovery restores entities


async def test_coordinator_recovery_restores_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Coordinator recovery after outage → entities restore with fresh data."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_42)
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

    # Verify entities are available
    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state is not None
    assert state.state != "unavailable"

    # Outage
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, exception=aiohttp.ClientError("Connection refused"))
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Entities become unavailable
    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state.state == "unavailable"

    # Recovery
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_42)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Entities restore
    state = hass.states.get("sensor.khealth_wellness_movement_today")
    assert state.state != "unavailable"
