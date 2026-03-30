"""Logbook support for CallAttendantNext Monitor."""
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_describe_events(hass: HomeAssistant, async_describe_event) -> None:
    """Describe logbook events for CallAttendantNext Monitor."""

    @callback
    def describe_event(event):
        data = event.data
        action = data.get("action", "Unknown")
        name = data.get("name", "Unknown")
        number = data.get("number", "")
        reason = data.get("reason", "")
        return {
            "name": "CallAttendantNext Monitor",
            "message": f"{action}: {name} ({number}) — {reason}",
        }

    async_describe_event(DOMAIN, f"{DOMAIN}_call", describe_event)
