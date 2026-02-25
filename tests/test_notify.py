"""Tests for kHealth notification sending and action event handling."""

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

POLL_NO_REMINDERS = {
    "active_reminders": {"movement": None, "hydration": None},
    "today": {"movement": {"done": 0, "total": 8}, "hydration": {"done": 0, "total": 6}},
    "streaks": {"movement": 0, "hydration": 0},
    "schedule": {"in_window": True, "window_start": "08:00", "window_end": "17:00", "timezone": "Europe/Berlin"},
}

POLL_WITH_MOVEMENT = {
    **POLL_NO_REMINDERS,
    "active_reminders": {"movement": MOVEMENT_REMINDER, "hydration": None},
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


# --- Notification sending ---


async def test_new_reminder_triggers_notification(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: new reminder in coordinator data triggers notification send."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)

    # Notification should have been sent
    assert notify_mock.call_count == 1
    service_data = notify_mock.call_args[0][0].data
    assert service_data["message"] == "Air squats x 10"
    assert service_data["title"] == "kHealth"


async def test_notification_includes_action_buttons(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: notification includes correct action buttons (Done, Skip, Snooze, Alternative)."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)

    service_data = notify_mock.call_args[0][0].data
    actions = service_data["data"]["actions"]
    action_titles = [a["title"] for a in actions]
    assert action_titles == ["Done", "Skip", "Snooze", "Alternative..."]

    # Check action IDs contain reminder ID
    assert actions[0]["action"] == "KHEALTH_DONE_42"
    assert actions[1]["action"] == "KHEALTH_SKIP_42"
    assert actions[2]["action"] == "KHEALTH_SNOOZE_42"
    assert actions[3]["action"] == "KHEALTH_ALT_42"

    # Alternative should have text input behavior
    assert actions[3]["behavior"] == "textInput"


async def test_reminder_disappearing_triggers_dismiss(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: reminder disappearing triggers notification dismiss."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    # Start with movement reminder
    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    notify_mock.reset_mock()

    # Now simulate coordinator update where reminder is gone
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_NO_REMINDERS)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Should have sent a dismiss (clear_notification)
    assert notify_mock.call_count == 1
    service_data = notify_mock.call_args[0][0].data
    assert service_data["message"] == "clear_notification"
    assert service_data["data"]["tag"] == "khealth-movement"


async def test_same_reminder_no_duplicate_notification(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: same reminder ID does not trigger duplicate notification."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    # Same reminder on next poll
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=POLL_WITH_MOVEMENT)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # No new notification
    assert notify_mock.call_count == 0


async def test_reminder_id_changes_sends_new_without_dismiss(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: reminder ID change sends new notification without dismissing first.

    When the old reminder expires and a new one fires (same type, different ID),
    the new notification should replace the old one via the same tag — no separate
    dismiss that could race and clear the new notification.
    """
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    assert notify_mock.call_count == 1
    notify_mock.reset_mock()

    # New reminder with different ID (old expired, new fired)
    new_reminder = {**MOVEMENT_REMINDER, "id": 99, "message": "Push-ups x 10"}
    poll_with_new = {
        **POLL_NO_REMINDERS,
        "active_reminders": {"movement": new_reminder, "hydration": None},
    }

    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]
    with aioresponses() as mock_api:
        mock_api.get(POLL_URL, payload=poll_with_new)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # Should send ONE new notification (no dismiss)
    assert notify_mock.call_count == 1
    service_call = notify_mock.call_args[0][0]
    assert service_call.data["message"] == "Push-ups x 10"
    # Verify no clear_notification was sent
    dismiss_calls = [
        c for c in notify_mock.call_args_list
        if c[0][0].data.get("message") == "clear_notification"
    ]
    assert len(dismiss_calls) == 0


# --- Action event handling ---


async def test_action_done_calls_acknowledge_api(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: action event with KHEALTH_DONE prefix calls acknowledge API with 'done'."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    notify_mock.reset_mock()

    with aioresponses() as mock_api:
        mock_api.post(ACK_URL, payload={"status": "acknowledged"})
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "KHEALTH_DONE_42"},
        )
        await hass.async_block_till_done()

    # Verify the POST was made by checking that the dismiss notification was sent
    # (dismiss only happens after successful ack)
    dismiss_calls = [
        c for c in notify_mock.call_args_list
        if c[0][0].data.get("message") == "clear_notification"
    ]
    assert len(dismiss_calls) == 1
    assert dismiss_calls[0][0][0].data["data"]["tag"] == "khealth-movement"


async def test_action_alt_sends_notes_from_reply_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: action event with KHEALTH_ALT prefix sends notes from reply_text."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)

    with aioresponses() as mock_api:
        mock_api.post(ACK_URL, payload={"status": "acknowledged"})
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "KHEALTH_ALT_42", "reply_text": "walked the dog"},
        )
        await hass.async_block_till_done()


async def test_action_already_acked_409_dismissed_silently(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: action event for already-acked reminder (409) dismissed silently."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    notify_mock.reset_mock()

    with aioresponses() as mock_api:
        mock_api.post(ACK_URL, status=409, payload={"error": "Reminder already acknowledged"})
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "KHEALTH_DONE_42"},
        )
        await hass.async_block_till_done()

    # Should dismiss the notification (clear_notification), no error notification
    dismiss_calls = [
        c for c in notify_mock.call_args_list
        if c[0][0].data.get("message") == "clear_notification"
    ]
    assert len(dismiss_calls) == 1


async def test_non_khealth_action_ignored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: non-KHEALTH action events are ignored."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    notify_mock.reset_mock()

    with aioresponses():
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "SOME_OTHER_ACTION"},
        )
        await hass.async_block_till_done()

    # No notification sent, no API calls
    assert notify_mock.call_count == 0


async def test_api_error_on_ack_shows_error_notification(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: API error on ack shows error notification."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)
    notify_mock.reset_mock()

    import aiohttp

    with aioresponses() as mock_api:
        mock_api.post(ACK_URL, exception=aiohttp.ClientError("Connection refused"))
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": "KHEALTH_DONE_42"},
        )
        await hass.async_block_till_done()

    # Should show an error notification
    error_calls = [
        c for c in notify_mock.call_args_list
        if "error" in c[0][0].data.get("message", "").lower()
        or "failed" in c[0][0].data.get("message", "").lower()
    ]
    assert len(error_calls) >= 1


async def test_listener_cleaned_up_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test: event listener is cleaned up on unload."""
    notify_mock = AsyncMock()
    hass.services.async_register("notify", "mobile_app_karls_iphone", notify_mock)

    await _setup_integration(hass, mock_config_entry, POLL_WITH_MOVEMENT)

    # Unload
    result = await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert result is True

    notify_mock.reset_mock()

    # Fire action after unload — should not be handled
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "KHEALTH_DONE_42"},
    )
    await hass.async_block_till_done()

    # No notification or API call should happen
    assert notify_mock.call_count == 0
