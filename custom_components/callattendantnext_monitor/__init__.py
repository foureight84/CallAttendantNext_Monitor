"""CallAttendantNext Monitor — Home Assistant integration.

Subscribes to MQTT call events from CallAttendantNext, persists history,
exposes sensors, fires logbook events, and serves a Lovelace history card.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import voluptuous as vol
from homeassistant.components import mqtt, websocket_api
from homeassistant.components.persistent_notification import (
    async_create as pn_create,
    async_dismiss as pn_dismiss,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import EVENT_HOMEASSISTANT_STARTED, HomeAssistant, callback
from homeassistant.helpers import storage
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_HISTORY_LIMIT,
    CONF_MQTT_TOPIC,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_TOPIC,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

_CARD_SRC = Path(__file__).parent / "callattendantnext-monitor-card.js"
_CARD_DEST_NAME = "callattendantnext-monitor-card.js"
_MANIFEST = json.loads((Path(__file__).parent / "manifest.json").read_text())
_VERSION = _MANIFEST.get("version", "0").replace(".", "")
_CARD_LOCAL_URL = f"/local/{_CARD_DEST_NAME}"

_NOTIFICATION_ID = "callattendantnext_monitor_resource"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Copy the card JS to www/ and auto-register it as a Lovelace resource."""
    await hass.async_add_executor_job(_copy_card_to_www, hass)

    async def _register_on_start(_event=None) -> None:
        await _async_register_lovelace_resource(hass, _CARD_LOCAL_URL)

    if hass.is_running:
        await _register_on_start()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_on_start)

    return True


def _copy_card_to_www(hass: HomeAssistant) -> None:
    """Copy card JS to config/www/ so it is served at /local/."""
    www_dir = Path(hass.config.path("www"))
    www_dir.mkdir(exist_ok=True)
    dest = www_dir / _CARD_DEST_NAME
    shutil.copy2(_CARD_SRC, dest)
    _LOGGER.debug("Copied CallAttendantNext Monitor card to %s", dest)


async def _async_register_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Auto-register the card JS as a Lovelace resource, replacing stale versions."""
    try:
        from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN

        lovelace_data = hass.data.get(LOVELACE_DOMAIN)
        _LOGGER.debug("Lovelace data type: %s, keys: %s",
            type(lovelace_data).__name__,
            list(lovelace_data.keys()) if isinstance(lovelace_data, dict) else "n/a",
        )

        # Try multiple access paths for different HA versions.
        resources = None
        if isinstance(lovelace_data, dict):
            resources = lovelace_data.get("resources")
        if resources is None:
            # Fallback: some HA versions store resources at a top-level key.
            resources = hass.data.get("lovelace_resources")
        if resources is None:
            # Fallback: try accessing as an attribute.
            resources = getattr(lovelace_data, "resources", None)

        _LOGGER.debug("Lovelace resources: %s", type(resources).__name__ if resources else "None")

        if resources is None:
            _LOGGER.warning("Lovelace resources collection not found — showing manual registration notice")
            _show_manual_registration_notice(hass, url)
            return

        # Remove stale registrations for this card (e.g. old versioned URLs).
        for item in list(resources.async_items()):
            item_url = item.get("url", "")
            if item_url != url and _CARD_DEST_NAME in item_url:
                _LOGGER.info("Removing stale Lovelace resource: %s", item_url)
                await resources.async_delete_item(item["id"])

        # Skip if already registered at the current version URL.
        for item in resources.async_items():
            if item.get("url") == url:
                _LOGGER.debug("Lovelace resource already registered: %s", url)
                pn_dismiss(hass, _NOTIFICATION_ID)
                return

        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered Lovelace resource: %s", url)
        pn_dismiss(hass, _NOTIFICATION_ID)

    except Exception as exc:
        _LOGGER.warning(
            "Could not auto-register Lovelace resource %s: %s", url, exc, exc_info=True
        )
        _show_manual_registration_notice(hass, url)


@callback
def _show_manual_registration_notice(hass: HomeAssistant, url: str) -> None:
    """Show a persistent notification guiding the user to register the card resource."""
    pn_create(
        hass,
        (
            "The CallAttendantNext Monitor card could not be registered automatically.\n\n"
            "To add it manually:\n"
            "1. Go to **Settings → Dashboards**\n"
            "2. Click ⋮ (top right) → **Resources**\n"
            "3. Click **+ Add Resource**\n"
            f"4. Set **URL** to `{url}` and **Resource type** to `JavaScript Module`\n"
            "5. Click **Create**, then hard-refresh your browser (`Cmd+Shift+R` / `Ctrl+Shift+R`)\n\n"
            "This only needs to be done once."
        ),
        title="CallAttendantNext Monitor — Action Required",
        notification_id=_NOTIFICATION_ID,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CallAttendantNext Monitor from a config entry."""
    # Initialise domain data store
    hass.data.setdefault(DOMAIN, {})

    # Load persisted call history
    store = storage.Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load()
    calls: list[dict] = (stored or {}).get("calls", [])

    # Create a coordinator; updates are pushed (no polling)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
    )
    coordinator.async_set_updated_data({"calls": calls})

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "store": store,
        "calls": calls,
    }

    # Resolve effective config (options override initial data after reconfiguration)
    def _cfg(key: str, default):
        return entry.options.get(key, entry.data.get(key, default))

    topic: str = _cfg(CONF_MQTT_TOPIC, DEFAULT_TOPIC)
    history_limit: int = _cfg(CONF_HISTORY_LIMIT, DEFAULT_HISTORY_LIMIT)

    @callback
    def message_received(msg) -> None:
        """Handle an incoming MQTT call event."""
        try:
            payload: dict = json.loads(msg.payload)
        except (json.JSONDecodeError, ValueError) as exc:
            _LOGGER.warning("Failed to parse MQTT payload: %s", exc)
            return

        entry_data = hass.data[DOMAIN][entry.entry_id]
        entry_data["calls"].insert(0, payload)
        entry_data["calls"] = entry_data["calls"][:history_limit]

        # Debounced persist (30 s delay to batch rapid messages)
        entry_data["store"].async_delay_save(
            lambda: {"calls": entry_data["calls"]}, 30
        )

        # Fire event so it appears in the logbook
        hass.bus.async_fire(f"{DOMAIN}_call", payload)

        # Notify coordinator listeners (sensors)
        entry_data["coordinator"].async_set_updated_data(
            {"calls": entry_data["calls"]}
        )

    # Subscribe to MQTT; the returned unsubscribe callable is auto-called on unload
    entry.async_on_unload(
        await mqtt.async_subscribe(hass, topic, message_received)
    )

    # Register WebSocket command once (guard against duplicate registration)
    if not hass.data[DOMAIN].get("_ws_registered"):
        websocket_api.async_register_command(hass, websocket_get_history)
        hass.data[DOMAIN]["_ws_registered"] = True

    # Forward to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entry when options change
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


# ---------------------------------------------------------------------------
# WebSocket command: callattendantnext_monitor/history
# ---------------------------------------------------------------------------

@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Optional("page", default=0): vol.All(int, vol.Range(min=0)),
        vol.Optional("page_size", default=10): vol.All(
            int, vol.Range(min=1, max=100)
        ),
    }
)
@websocket_api.async_response
async def websocket_get_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return a page of call history."""
    calls: list[dict] = []
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "calls" in entry_data:
            calls = entry_data["calls"]
            break

    page: int = msg["page"]
    page_size: int = msg["page_size"]
    start = page * page_size
    end = start + page_size

    connection.send_result(
        msg["id"],
        {
            "calls": calls[start:end],
            "total": len(calls),
            "page": page,
            "page_size": page_size,
        },
    )
