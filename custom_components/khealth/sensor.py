"""Sensor entities for kHealth integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
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
    """Set up kHealth sensor entities from a config entry."""
    coordinator: KhealthCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    prefix = unique_id_prefix(entry)
    device = device_info(entry)

    entities: list[SensorEntity] = [
        KhealthTodaySensor(coordinator, prefix, device, "movement"),
        KhealthTodaySensor(coordinator, prefix, device, "hydration"),
        KhealthStreakSensor(coordinator, prefix, device, "movement"),
        KhealthStreakSensor(coordinator, prefix, device, "hydration"),
        KhealthScheduleSensor(coordinator, prefix, device),
    ]
    async_add_entities(entities)


class KhealthTodaySensor(CoordinatorEntity[KhealthCoordinator], SensorEntity):
    """Sensor showing today's done/total for a reminder type."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KhealthCoordinator,
        prefix: str,
        device: DeviceInfo,
        reminder_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._reminder_type = reminder_type
        self._attr_unique_id = f"{prefix}_{reminder_type}_today"
        self._attr_translation_key = f"{reminder_type}_today"
        self._attr_name = f"{reminder_type.title()} Today"
        self._attr_device_info = device

    @property
    def native_value(self) -> str | None:
        """Return done/total as a string."""
        if self.coordinator.data is None:
            return None
        today = self.coordinator.data.get("today", {}).get(self._reminder_type)
        if today is None:
            return None
        return f"{today['done']}/{today['total']}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return done and total as separate attributes."""
        if self.coordinator.data is None:
            return {}
        today = self.coordinator.data.get("today", {}).get(self._reminder_type)
        if today is None:
            return {}
        return {"done": today["done"], "total": today["total"]}


class KhealthStreakSensor(CoordinatorEntity[KhealthCoordinator], SensorEntity):
    """Sensor showing the current streak for a reminder type."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: KhealthCoordinator,
        prefix: str,
        device: DeviceInfo,
        reminder_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._reminder_type = reminder_type
        self._attr_unique_id = f"{prefix}_{reminder_type}_streak"
        self._attr_translation_key = f"{reminder_type}_streak"
        self._attr_name = f"{reminder_type.title()} Streak"
        self._attr_device_info = device

    @property
    def native_value(self) -> int | None:
        """Return the streak count."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("streaks", {}).get(self._reminder_type)


class KhealthScheduleSensor(CoordinatorEntity[KhealthCoordinator], SensorEntity):
    """Sensor showing whether the schedule is active or inactive."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["active", "inactive"]

    def __init__(
        self,
        coordinator: KhealthCoordinator,
        prefix: str,
        device: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{prefix}_schedule"
        self._attr_translation_key = "schedule"
        self._attr_name = "Schedule"
        self._attr_device_info = device

    @property
    def native_value(self) -> str | None:
        """Return 'active' or 'inactive' based on in_window."""
        if self.coordinator.data is None:
            return None
        schedule = self.coordinator.data.get("schedule")
        if schedule is None:
            return None
        return "active" if schedule.get("in_window") else "inactive"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return schedule details as attributes."""
        if self.coordinator.data is None:
            return {}
        schedule = self.coordinator.data.get("schedule")
        if schedule is None:
            return {}
        return {
            "window_start": schedule.get("window_start"),
            "window_end": schedule.get("window_end"),
            "timezone": schedule.get("timezone"),
        }
