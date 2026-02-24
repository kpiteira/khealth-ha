"""Full-flow integration tests for the kHealth HA integration.

These tests exercise the complete notification lifecycle using the HA test
framework with mocked khealth API responses. They are integration tests
(not E2E) because they mock the khealth backend — real E2E requires a live
HA instance with the Companion App (manual validation).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from aioresponses import aioresponses

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.khealth.const import DOMAIN

POLL_URL = "http://khealth.example.com/api/v1/ha/poll"
ACK_URL = "http://khealth.example.com/api/v1/ha/acknowledge"

MOVEMENT_REMINDER = {
    "id": 42,
    "type": "movement",
    "message": "Air squats x 10",
    "exercise": "air_squats",
    "exercise_label": "air squats",
    "suggested_count": 10,
    "sent_at": "2026-02-23T14:30:00Z",
    "refired_at": None,
}

POLL_EMPTY = {
    "active_reminders": {"movement": None, "hydration": None},
    "today": {"movement": {"done": 6, "total": 8}, "hydration": {"done": 4, "total": 6}},
    "streaks": {"movement": 5, "hydration": 3},
    "schedule": {"in_window": True, "window_start": "08:00", "window_end": "17:00", "timezone": "Europe/Berlin"},
}

POLL_WITH_MOVEMENT = {
    **POLL_EMPTY,
    "active_reminders": {"movement": MOVEMENT_REMINDER, "hydration": None},
}


async def test_full_flow_coordinator_polls_and_receives_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Scenario 1: Coordinator polls and receives data with active reminder."""
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_MOVEMENT)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    assert coordinator.data["active_reminders"]["movement"] is not None
    assert coordinator.data["active_reminders"]["movement"]["id"] == 42
    assert coordinator.data["active_reminders"]["movement"]["message"] == "Air squats x 10"


async def test_full_flow_new_reminder_triggers_notification(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Scenario 2: New reminder triggers notification with correct action buttons."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_MOVEMENT)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert notify_mock.call_count == 1
    service_call = notify_mock.call_args[0][0]
    assert service_call.data["message"] == "Air squats x 10"
    assert service_call.data["title"] == "kHealth"

    actions = service_call.data["data"]["actions"]
    assert len(actions) == 4
    assert actions[0] == {"action": "KHEALTH_DONE_42", "title": "Done"}
    assert actions[1] == {"action": "KHEALTH_SKIP_42", "title": "Skip"}
    assert actions[2] == {"action": "KHEALTH_SNOOZE_42", "title": "Snooze"}
    assert actions[3]["action"] == "KHEALTH_ALT_42"
    assert actions[3]["behavior"] == "textInput"


async def test_full_flow_reminder_disappears_triggers_dismiss(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Scenario 3: Reminder disappearing (acked on Telegram) triggers HA dismiss."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    # Initial poll: movement reminder active
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_MOVEMENT)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    notify_mock.reset_mock()

    # Next poll: reminder gone (acknowledged via Telegram)
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_EMPTY)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Should dismiss the HA notification
    assert notify_mock.call_count == 1
    service_call = notify_mock.call_args[0][0]
    assert service_call.data["message"] == "clear_notification"
    assert service_call.data["data"]["tag"] == "khealth-movement"


async def test_full_flow_action_event_triggers_acknowledge(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Scenario 4: Tapping Done fires action event → calls acknowledge API → dismisses."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_MOVEMENT)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    notify_mock.reset_mock()

    # User taps Done on the HA notification
    with aioresponses() as mock_api:
        mock_api.post(ACK_URL, payload={"status": "acknowledged"})
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "KHEALTH_DONE_42"},
        )
        await hass.async_block_till_done()

    # Should dismiss the notification after successful ack
    dismiss_calls = [
        c for c in notify_mock.call_args_list
        if c[0][0].data.get("message") == "clear_notification"
    ]
    assert len(dismiss_calls) == 1
    assert dismiss_calls[0][0][0].data["data"]["tag"] == "khealth-movement"


async def test_full_flow_alternative_with_text_input(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Scenario 5: Alternative with text input → sends notes to acknowledge API."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_MOVEMENT)
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    notify_mock.reset_mock()

    # User taps Alternative, types "walked the dog"
    with aioresponses() as mock_api:
        mock_api.post(ACK_URL, payload={"status": "acknowledged"})
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "KHEALTH_ALT_42", "reply_text": "walked the dog"},
        )
        await hass.async_block_till_done()

    # Should dismiss after successful ack
    dismiss_calls = [
        c for c in notify_mock.call_args_list
        if c[0][0].data.get("message") == "clear_notification"
    ]
    assert len(dismiss_calls) == 1
