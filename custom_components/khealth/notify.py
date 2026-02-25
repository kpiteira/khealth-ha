"""Notification sending and action event handling for kHealth."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

from homeassistant.core import Event, HomeAssistant, callback


_LOGGER = logging.getLogger(__name__)

ACTION_PATTERN = re.compile(r"^KHEALTH_(DONE|SKIP|SNOOZE|ALT)_(\d+)$")

RESPONSE_MAP = {
    "DONE": "done",
    "SKIP": "skipped",
    "SNOOZE": "snoozed",
    "ALT": "alternative",
}


class KhealthNotificationManager:
    """Manages sending and dismissing kHealth notifications."""

    def __init__(
        self,
        hass: HomeAssistant,
        notify_device: str,
        api_url: str,
        api_token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the notification manager."""
        self._hass = hass
        self._notify_device = notify_device
        self._api_url = api_url.rstrip("/")
        self._api_token = api_token
        self._session = session
        self._last_seen: dict[str, int | None] = {}
        self._unsub_action: Any = None
        self._unsub_coordinator: Any = None

    def start(self, coordinator: Any) -> None:
        """Start listening for coordinator updates and action events."""
        self._coordinator = coordinator
        self._unsub_coordinator = coordinator.async_add_listener(
            self._on_coordinator_update
        )
        self._unsub_action = self._hass.bus.async_listen(
            "mobile_app_notification_action", self._handle_action
        )
        # Process initial data from the first refresh
        if coordinator.data is not None:
            self._on_coordinator_update()

    def stop(self) -> None:
        """Stop all listeners."""
        if self._unsub_coordinator:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        if self._unsub_action:
            self._unsub_action()
            self._unsub_action = None

    @callback
    def _on_coordinator_update(self) -> None:
        """Handle coordinator data update — send or dismiss notifications."""
        if self._coordinator is None or self._coordinator.data is None:
            return

        active = self._coordinator.data.get("active_reminders", {})

        for rtype in ("movement", "hydration"):
            new_reminder = active.get(rtype)
            old_id = self._last_seen.get(rtype)
            new_id = new_reminder["id"] if new_reminder else None

            if new_id is not None and new_id != old_id:
                # New reminder — send notification (replaces old one via same tag)
                self._hass.async_create_task(
                    self._send_notification(new_reminder, rtype)
                )
            elif new_id is None and old_id is not None:
                # Reminder gone with no replacement — dismiss
                self._hass.async_create_task(
                    self._dismiss_notification(rtype)
                )

            self._last_seen[rtype] = new_id

    async def _send_notification(self, reminder: dict, rtype: str) -> None:
        """Send an actionable notification via the Companion App."""
        rid = reminder["id"]
        try:
            await self._hass.services.async_call(
                "notify",
                self._notify_device,
                {
                    "message": reminder["message"],
                    "title": "kHealth",
                    "data": {
                        "tag": f"khealth-{rtype}",
                        "group": "khealth",
                        "actions": [
                            {"action": f"KHEALTH_DONE_{rid}", "title": "Done"},
                            {"action": f"KHEALTH_SKIP_{rid}", "title": "Skip"},
                            {"action": f"KHEALTH_SNOOZE_{rid}", "title": "Snooze"},
                            {
                                "action": f"KHEALTH_ALT_{rid}",
                                "title": "Alternative...",
                                "behavior": "textInput",
                                "textInputButtonTitle": "Send",
                                "textInputPlaceholder": "What did you do instead?",
                            },
                        ],
                    },
                },
            )
        except Exception:
            _LOGGER.exception("Failed to send kHealth notification for %s", rtype)

    async def _dismiss_notification(self, rtype: str) -> None:
        """Dismiss a notification by tag."""
        try:
            await self._hass.services.async_call(
                "notify",
                self._notify_device,
                {
                    "message": "clear_notification",
                    "data": {"tag": f"khealth-{rtype}"},
                },
            )
        except Exception:
            _LOGGER.exception("Failed to dismiss kHealth notification for %s", rtype)

    async def _handle_action(self, event: Event) -> None:
        """Handle mobile_app_notification_action events."""
        action = event.data.get("action", "")
        match = ACTION_PATTERN.match(action)
        if not match:
            return  # Not a kHealth action

        response_key = match.group(1)
        reminder_id = int(match.group(2))
        response = RESPONSE_MAP[response_key]

        notes = ""
        if response_key == "ALT":
            notes = event.data.get("reply_text", "")

        headers = {"Authorization": f"Bearer {self._api_token}"}
        body: dict[str, Any] = {
            "reminder_id": reminder_id,
            "response": response,
        }
        if notes:
            body["notes"] = notes

        try:
            async with self._session.post(
                f"{self._api_url}/api/v1/ha/acknowledge",
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 409:
                    # Already acknowledged — dismiss silently
                    _LOGGER.debug("Reminder %d already acknowledged", reminder_id)
                elif resp.status != 200:
                    raise aiohttp.ClientError(f"Unexpected status {resp.status}")
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Failed to acknowledge reminder %d: %s", reminder_id, err)
            # Send error notification
            await self._hass.services.async_call(
                "notify",
                self._notify_device,
                {
                    "message": "Failed to record response. Please try again.",
                    "title": "kHealth Error",
                },
            )
            return

        # Dismiss the notification on success or 409
        # Find the reminder type from the action (we need to find which tag to clear)
        for rtype in ("movement", "hydration"):
            if self._last_seen.get(rtype) == reminder_id:
                await self._dismiss_notification(rtype)
                break
