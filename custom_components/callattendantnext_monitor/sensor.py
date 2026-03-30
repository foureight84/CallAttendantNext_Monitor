"""Sensors for CallAttendantNext Monitor."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CallAttendantNext Monitor sensors from a config entry."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities(
        [
            LastCallSensor(coordinator, entry),
            WeeklyCountSensor(
                coordinator, entry, "total", "Total Calls This Week", None, "mdi:phone-log"
            ),
            WeeklyCountSensor(
                coordinator, entry, "permitted", "Permitted Calls This Week", "Permitted", "mdi:phone-check"
            ),
            WeeklyCountSensor(
                coordinator, entry, "screened", "Screened Calls This Week", "Screened", "mdi:phone-alert"
            ),
            WeeklyCountSensor(
                coordinator, entry, "blocked", "Blocked Calls This Week", "Blocked", "mdi:phone-cancel"
            ),
        ]
    )


class LastCallSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the most recent call."""

    _attr_icon = "mdi:phone"

    def __init__(self, coordinator: DataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_call"
        self._attr_name = "CallAttendantNext Monitor Last Call"
        self.entity_id = f"sensor.{DOMAIN}_last_call"

    @property
    def native_value(self) -> str | None:
        """Return the action of the most recent call."""
        calls: list = self.coordinator.data.get("calls", [])
        if not calls:
            return None
        return calls[0].get("action")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes from the most recent call."""
        calls: list = self.coordinator.data.get("calls", [])
        if not calls:
            return {}
        call = calls[0]
        return {
            "name": call.get("name"),
            "number": call.get("number"),
            "timestamp": call.get("timestamp"),
            "reason": call.get("reason"),
            "voicemail": call.get("voicemail"),
        }


class WeeklyCountSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the count of calls in the past 7 days."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "calls"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
        name: str,
        action_filter: str | None,
        icon: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._action_filter = action_filter
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}_calls_week"
        self._attr_name = f"CallAttendantNext Monitor {name}"
        self.entity_id = f"sensor.{DOMAIN}_{sensor_key}_calls_this_week"
        self._attr_icon = icon

    @property
    def native_value(self) -> int:
        """Return the call count for the past 7 days."""
        calls: list = self.coordinator.data.get("calls", [])
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        count = 0
        for call in calls:
            ts_str = call.get("timestamp")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < week_ago:
                # Calls are stored newest-first; once we pass the week boundary we can stop
                break
            if self._action_filter is None or call.get("action") == self._action_filter:
                count += 1
        return count
