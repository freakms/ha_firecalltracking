"""Einsatz-Monitor Integration for Home Assistant."""
import asyncio
import logging
import os
from datetime import timedelta
from pathlib import Path

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_URL,
    CONF_TOKEN,
    CONF_POLL_INTERVAL,
    CONF_USE_WEBSOCKET,
    CONF_ENABLE_ALEXA,
    CONF_ALEXA_ENTITY,
    CONF_ALEXA_MESSAGE,
    CONF_ENABLE_LIGHT,
    CONF_LIGHT_ENTITIES,
    CONF_LIGHT_COLOR,
    CONF_LIGHT_DURATION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_USE_WEBSOCKET,
    DEFAULT_ALEXA_MESSAGE,
    DEFAULT_LIGHT_DURATION,
    EVENT_NEW_ALARM,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

# Card paths
CARD_DIR = Path(__file__).parent / "www"
CARD_FILENAME = "einsatz-monitor-card.js"
CARD_URL_PATH = f"/einsatz_monitor/{CARD_FILENAME}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Einsatz-Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Register the custom card JS
    await async_register_card(hass)
    
    url = entry.data[CONF_URL].rstrip("/")
    token = entry.data[CONF_TOKEN]
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    use_websocket = entry.data.get(CONF_USE_WEBSOCKET, DEFAULT_USE_WEBSOCKET)
    
    session = async_get_clientsession(hass)
    
    coordinator = EinsatzMonitorCoordinator(
        hass,
        entry=entry,
        session=session,
        url=url,
        token=token,
        poll_interval=poll_interval,
    )
    
    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "url": url,
        "token": token,
    }
    
    # Start WebSocket if enabled
    if use_websocket:
        hass.async_create_task(
            start_websocket(hass, entry, url, token)
        )
    
    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


class EinsatzMonitorCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Einsatz-Monitor."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: aiohttp.ClientSession,
        url: str,
        token: str,
        poll_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.entry = entry
        self.session = session
        self.url = url
        self.token = token
        self.last_alarm_id = None
        self._notified_alarm_ids = set()
    
    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(10):
                response = await self.session.get(
                    f"{self.url}/api/ha/poll",
                    params={"token": self.token},
                )
                response.raise_for_status()
                alarms = await response.json()
                
                # Check for new alarms
                if alarms and len(alarms) > 0:
                    latest = alarms[0]
                    alarm_id = latest.get("id")
                    if alarm_id != self.last_alarm_id:
                        self.last_alarm_id = alarm_id
                        
                        alarm_data = {
                            "keyword": latest.get("keyword"),
                            "unit": latest.get("unit"),
                            "vehicles": latest.get("vehicles"),
                            "timestamp": latest.get("timestamp"),
                            "tenant_name": latest.get("tenant_name"),
                        }
                        
                        # Fire event for new alarm
                        if alarm_id not in self._notified_alarm_ids:
                            self.hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                            self._notified_alarm_ids.add(alarm_id)
                            _LOGGER.info(f"New alarm event fired: {latest.get('keyword')}")
                            
                            # Handle notifications
                            await self._handle_alarm_notifications(alarm_data, alarm_id)
                            
                            # Cleanup old IDs
                            if len(self._notified_alarm_ids) > 100:
                                self._notified_alarm_ids = set(list(self._notified_alarm_ids)[-50:])
                
                return {
                    "alarms": alarms,
                    "latest": alarms[0] if alarms else None,
                    "count": len(alarms),
                }
                
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
    
    async def _handle_alarm_notifications(self, alarm_data: dict, alarm_id: str = None):
        """Handle notifications based on user options."""
        options = self.entry.options
        
        # Alexa notification
        if options.get(CONF_ENABLE_ALEXA) and options.get(CONF_ALEXA_ENTITY):
            await self._send_alexa_notification(alarm_data, options)
        
        # Light alert
        light_entities = options.get(CONF_LIGHT_ENTITIES, [])
        if options.get(CONF_ENABLE_LIGHT) and light_entities:
            await self._activate_light_alert(alarm_data, options)
    
    async def _send_alexa_notification(self, alarm_data: dict, options: dict):
        """Send Alexa voice notification."""
        message_template = options.get(CONF_ALEXA_MESSAGE, DEFAULT_ALEXA_MESSAGE)
        
        try:
            message = message_template.format(
                keyword=alarm_data.get("keyword", "Unbekannt"),
                unit=alarm_data.get("unit", ""),
                vehicles=alarm_data.get("vehicles", "Keine Fahrzeuge"),
                timestamp=alarm_data.get("timestamp", "")
            )
        except KeyError as e:
            _LOGGER.warning(f"Invalid placeholder in message template: {e}")
            message = f"Alarm: {alarm_data.get('keyword', 'Unbekannt')}"
        
        alexa_entity = options[CONF_ALEXA_ENTITY]
        
        try:
            await self.hass.services.async_call(
                "notify",
                "alexa_media",
                {
                    "message": message,
                    "target": alexa_entity,
                    "data": {"type": "tts"}
                },
                blocking=False,
            )
            _LOGGER.info(f"Alexa notification sent to {alexa_entity}")
            
            # Stop Alexa after message
            word_count = len(message.split())
            wait_time = max(3, word_count * 0.75 + 2)
            
            async def stop_alexa():
                await asyncio.sleep(wait_time)
                try:
                    await self.hass.services.async_call(
                        "media_player",
                        "media_stop",
                        {"entity_id": alexa_entity},
                        blocking=False,
                    )
                except Exception:
                    pass
            
            self.hass.async_create_task(stop_alexa())
            
        except Exception as e:
            _LOGGER.error(f"Failed to send Alexa notification: {e}")
    
    async def _activate_light_alert(self, alarm_data: dict, options: dict):
        """Activate light alert - stores previous state and restores it after timer."""
        color_map = {
            "red": [255, 0, 0],
            "blue": [0, 0, 255],
            "orange": [255, 165, 0],
            "white": [255, 255, 255]
        }
        color = color_map.get(options.get(CONF_LIGHT_COLOR, "red"), [255, 0, 0])
        
        light_entities = options.get(CONF_LIGHT_ENTITIES, [])
        if isinstance(light_entities, str):
            light_entities = [l.strip() for l in light_entities.split(",") if l.strip()]
        
        if not light_entities:
            return
        
        duration = options.get(CONF_LIGHT_DURATION, DEFAULT_LIGHT_DURATION)
        
        # Store previous states
        previous_states = {}
        for entity_id in light_entities:
            state = self.hass.states.get(entity_id)
            if state:
                previous_states[entity_id] = {
                    "state": state.state,
                    "attributes": dict(state.attributes)
                }
        
        try:
            # Turn on lights with alarm color
            await self.hass.services.async_call(
                "light",
                "turn_on",
                {
                    "entity_id": light_entities,
                    "rgb_color": color,
                    "brightness": 255,
                },
                blocking=False,
            )
            _LOGGER.info(f"Light alert activated for {len(light_entities)} lights")
            
            # Restore previous state after duration
            if duration > 0:
                async def restore_lights():
                    await asyncio.sleep(duration)
                    try:
                        for entity_id, prev in previous_states.items():
                            if prev["state"] == "on":
                                # Restore previous on state
                                restore_data = {"entity_id": entity_id}
                                if "brightness" in prev["attributes"]:
                                    restore_data["brightness"] = prev["attributes"]["brightness"]
                                if "rgb_color" in prev["attributes"]:
                                    restore_data["rgb_color"] = prev["attributes"]["rgb_color"]
                                elif "color_temp" in prev["attributes"]:
                                    restore_data["color_temp"] = prev["attributes"]["color_temp"]
                                
                                await self.hass.services.async_call(
                                    "light",
                                    "turn_on",
                                    restore_data,
                                    blocking=False,
                                )
                            else:
                                # Was off, turn it off again
                                await self.hass.services.async_call(
                                    "light",
                                    "turn_off",
                                    {"entity_id": entity_id},
                                    blocking=False,
                                )
                        _LOGGER.info(f"Light states restored after {duration}s")
                    except Exception as e:
                        _LOGGER.error(f"Failed to restore lights: {e}")
                
                self.hass.async_create_task(restore_lights())
                
        except Exception as e:
            _LOGGER.error(f"Failed to activate light alert: {e}")


async def start_websocket(hass: HomeAssistant, entry: ConfigEntry, url: str, token: str):
    """Start WebSocket connection for real-time updates."""
    ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/api/ha/ws/{token}"
    entry_id = entry.entry_id
    notified_ids = set()
    
    while True:
        try:
            session = async_get_clientsession(hass)
            async with session.ws_connect(ws_url) as ws:
                _LOGGER.info("WebSocket connected to Einsatz-Monitor")
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        
                        if data.get("type") == "alarm":
                            alarm = data.get("data", {})
                            alarm_id = alarm.get("id")
                            
                            if alarm_id and alarm_id in notified_ids:
                                continue
                            
                            alarm_data = {
                                "keyword": alarm.get("keyword"),
                                "unit": alarm.get("unit"),
                                "vehicles": alarm.get("vehicles"),
                                "timestamp": alarm.get("timestamp"),
                            }
                            
                            # Fire event
                            hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                            _LOGGER.info(f"WebSocket alarm event fired: {alarm.get('keyword')}")
                            
                            # Handle notifications
                            if entry_id in hass.data.get(DOMAIN, {}):
                                coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
                                await coordinator._handle_alarm_notifications(alarm_data, alarm_id)
                                await coordinator.async_request_refresh()
                            
                            if alarm_id:
                                notified_ids.add(alarm_id)
                                if len(notified_ids) > 100:
                                    notified_ids = set(list(notified_ids)[-50:])
                        
                        elif data.get("type") == "ping":
                            await ws.send_str("pong")
                    
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                        
        except Exception as err:
            _LOGGER.warning(f"WebSocket error: {err}. Reconnecting in 30s...")
        
        await asyncio.sleep(30)


async def async_register_card(hass: HomeAssistant):
    """Register the custom Lovelace card automatically."""
    
    # Register the static path for the card JS file
    card_path = CARD_DIR / CARD_FILENAME
    
    if card_path.exists():
        # Register static path so the file is accessible via HTTP
        hass.http.register_static_path(
            CARD_URL_PATH,
            str(card_path),
            cache_headers=False  # Disable caching during development
        )
        _LOGGER.info(f"Registered card static path at {CARD_URL_PATH}")
        
        # Try to add the resource to Lovelace automatically
        try:
            # Import here to avoid issues if lovelace is not loaded
            from homeassistant.components.lovelace.resources import ResourceStorageCollection
            
            # Check if lovelace resources are available
            if "lovelace" in hass.data:
                resources = hass.data["lovelace"].get("resources")
                if resources and isinstance(resources, ResourceStorageCollection):
                    # Check if resource already exists
                    existing = [
                        r for r in resources.async_items() 
                        if CARD_FILENAME in r.get("url", "")
                    ]
                    
                    if not existing:
                        await resources.async_create_item({
                            "url": CARD_URL_PATH,
                            "res_type": "module"
                        })
                        _LOGGER.info(f"Added Lovelace resource: {CARD_URL_PATH}")
                    else:
                        _LOGGER.debug("Card resource already registered")
                else:
                    _LOGGER.info(f"Add this resource manually in Lovelace: {CARD_URL_PATH}")
            else:
                _LOGGER.info(f"Lovelace not yet loaded. Add resource manually: {CARD_URL_PATH}")
        except ImportError:
            _LOGGER.info(f"Please manually add Lovelace resource: {CARD_URL_PATH}")
        except Exception as e:
            _LOGGER.warning(f"Could not auto-register Lovelace resource: {e}")
            _LOGGER.info(f"Please manually add resource: {CARD_URL_PATH}")
    else:
        _LOGGER.error(f"Card file not found: {card_path}")
