"""Einsatz-Monitor Integration for Home Assistant."""
import asyncio
import logging
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

CARD_JS_URL = "/local/einsatz_monitor/einsatz-monitor-card.js"


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
                    if latest.get("id") != self.last_alarm_id:
                        self.last_alarm_id = latest.get("id")
                        
                        alarm_data = {
                            "keyword": latest.get("keyword"),
                            "unit": latest.get("unit"),
                            "vehicles": latest.get("vehicles"),
                            "timestamp": latest.get("timestamp"),
                            "tenant_name": latest.get("tenant_name"),
                        }
                        
                        # Fire event for new alarm
                        self.hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                        _LOGGER.info(f"New alarm: {latest.get('keyword')}")
                        
                        # Execute configured notifications
                        await self._handle_alarm_notifications(alarm_data)
                
                return {
                    "alarms": alarms,
                    "latest": alarms[0] if alarms else None,
                    "count": len(alarms),
                }
                
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
    
    async def _handle_alarm_notifications(self, alarm_data: dict):
        """Handle notifications based on user options."""
        options = self.entry.options
        
        # Alexa notification
        if options.get(CONF_ENABLE_ALEXA) and options.get(CONF_ALEXA_ENTITY):
            await self._send_alexa_notification(alarm_data, options)
        
        # Light alert - now supports multiple lights
        light_entities = options.get(CONF_LIGHT_ENTITIES, [])
        if options.get(CONF_ENABLE_LIGHT) and light_entities:
            await self._activate_light_alert(options)
    
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
        
        try:
            await self.hass.services.async_call(
                "notify",
                "alexa_media",
                {
                    "message": message,
                    "target": options[CONF_ALEXA_ENTITY],
                    "data": {"type": "announce"}
                },
                blocking=False,
            )
            _LOGGER.info(f"Alexa notification sent to {options[CONF_ALEXA_ENTITY]}")
        except Exception as e:
            _LOGGER.error(f"Failed to send Alexa notification: {e}")
    
    async def _activate_light_alert(self, options: dict):
        """Activate light alert for multiple lights with optional auto-off timer."""
        color_map = {
            "red": [255, 0, 0],
            "blue": [0, 0, 255],
            "orange": [255, 165, 0],
            "white": [255, 255, 255]
        }
        color = color_map.get(options.get(CONF_LIGHT_COLOR, "red"), [255, 0, 0])
        
        # Get light entities (can be list or string)
        light_entities = options.get(CONF_LIGHT_ENTITIES, [])
        if isinstance(light_entities, str):
            light_entities = [l.strip() for l in light_entities.split(",") if l.strip()]
        
        if not light_entities:
            return
        
        # Get duration (0 = never turn off)
        duration = options.get(CONF_LIGHT_DURATION, DEFAULT_LIGHT_DURATION)
        
        try:
            # Turn on all lights
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
            _LOGGER.info(f"Light alert activated for {len(light_entities)} lights: {light_entities}")
            
            # Schedule turn off if duration > 0
            if duration > 0:
                async def turn_off_lights():
                    await asyncio.sleep(duration)
                    try:
                        await self.hass.services.async_call(
                            "light",
                            "turn_off",
                            {"entity_id": light_entities},
                            blocking=False,
                        )
                        _LOGGER.info(f"Light alert deactivated after {duration}s")
                    except Exception as e:
                        _LOGGER.error(f"Failed to turn off lights: {e}")
                
                self.hass.async_create_task(turn_off_lights())
                
        except Exception as e:
            _LOGGER.error(f"Failed to activate light alert: {e}")


async def start_websocket(hass: HomeAssistant, entry: ConfigEntry, url: str, token: str):
    """Start WebSocket connection for real-time updates."""
    ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/api/ha/ws/{token}"
    entry_id = entry.entry_id
    
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
                            alarm_data = {
                                "keyword": alarm.get("keyword"),
                                "unit": alarm.get("unit"),
                                "vehicles": alarm.get("vehicles"),
                                "timestamp": alarm.get("timestamp"),
                            }
                            
                            hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                            _LOGGER.info(f"WebSocket alarm: {alarm.get('keyword')}")
                            
                            # Execute configured notifications
                            if entry_id in hass.data.get(DOMAIN, {}):
                                coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
                                await coordinator._handle_alarm_notifications(alarm_data)
                                await coordinator.async_request_refresh()
                        
                        elif data.get("type") == "ping":
                            await ws.send_str("pong")
                    
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                        
        except Exception as err:
            _LOGGER.warning(f"WebSocket error: {err}. Reconnecting in 30s...")
        
        await asyncio.sleep(30)


async def async_register_card(hass: HomeAssistant):
    """Register the custom Lovelace card."""
    # Card should be manually installed to /config/www/einsatz_monitor/
    # or will be copied by HACS automatically
    _LOGGER.info("Card should be available at /local/einsatz_monitor/einsatz-monitor-card.js")

