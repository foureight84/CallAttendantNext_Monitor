"""Config flow for CallAttendantNext Monitor."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HISTORY_LIMIT,
    CONF_MQTT_TOPIC,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_TOPIC,
    DOMAIN,
)

HISTORY_LIMIT_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=10, max=5000))


class CallAttendantNextMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CallAttendantNext Monitor."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="CallAttendantNext Monitor",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MQTT_TOPIC, default=DEFAULT_TOPIC): str,
                    vol.Required(
                        CONF_HISTORY_LIMIT, default=DEFAULT_HISTORY_LIMIT
                    ): HISTORY_LIMIT_SCHEMA,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return CallAttendantNextMonitorOptionsFlow()


class CallAttendantNextMonitorOptionsFlow(OptionsFlow):
    """Handle options flow for CallAttendantNext Monitor."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_topic = self.config_entry.options.get(
            CONF_MQTT_TOPIC,
            self.config_entry.data.get(CONF_MQTT_TOPIC, DEFAULT_TOPIC),
        )
        current_limit = self.config_entry.options.get(
            CONF_HISTORY_LIMIT,
            self.config_entry.data.get(CONF_HISTORY_LIMIT, DEFAULT_HISTORY_LIMIT),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MQTT_TOPIC, default=current_topic): str,
                    vol.Required(
                        CONF_HISTORY_LIMIT, default=current_limit
                    ): HISTORY_LIMIT_SCHEMA,
                }
            ),
        )
