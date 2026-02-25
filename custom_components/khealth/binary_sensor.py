"""Binary sensor entities for kHealth integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, device_info, unique_id_prefix
from .coordinator import KhealthCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up kHealth binary sensor entities from a config entry."""
    coordinator: KhealthCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    prefix = unique_id_prefix(entry)
    device = device_info(entry)

    async_add_entities([KhealthReminderPendingSensor(coordinator, prefix, device)])


class KhealthReminderPendingSensor(CoordinatorEntity[KhealthCoordinator], BinarySensorEntity):
    """Binary sensor indicating whether any reminder is pending."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KhealthCoordinator,
        prefix: str,
        device: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{prefix}_reminder_pending"
        self._attr_translation_key = "reminder_pending"
        self._attr_name = "Reminder Pending"
        self._attr_device_info = device

    @property
    def is_on(self) -> bool | None:
        """Return True if any reminder is active."""
        if self.coordinator.data is None:
            return None
        active = self.coordinator.data.get("active_reminders", {})
        return any(r is not None for r in active.values())

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return "mdi:bell-ring" if self.is_on else "mdi:bell-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the first pending reminder."""
        if self.coordinator.data is None:
            return {}
        active = self.coordinator.data.get("active_reminders", {})
        # Find the first non-null reminder
        for reminder in active.values():
            if reminder is not None:
                return {
                    "type": reminder.get("type", ""),
                    "exercise": reminder.get("exercise_label", ""),
                    "message": reminder.get("message", ""),
                    "sent_at": reminder.get("sent_at", ""),
                }
        return {}
