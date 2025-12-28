"""Einsatz-Monitor Integration for Home Assistant."""
import asyncio
import logging
import json
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
AUTOMATION_ID = "einsatz_monitor_alarm_automation"


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
    
    # Create/Update automation based on options
    await create_or_update_automation(hass, entry)
    
    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    # Update automation when options change
    await create_or_update_automation(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def create_or_update_automation(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create or update Home Assistant automation based on user options."""
    options = entry.options
    
    # Check if any automation is needed
    enable_alexa = options.get(CONF_ENABLE_ALEXA, False)
    enable_light = options.get(CONF_ENABLE_LIGHT, False)
    
    if not enable_alexa and not enable_light:
        _LOGGER.info("No Alexa or Light actions configured - skipping automation creation")
        return
    
    # Build actions list
    actions = []
    
    # Alexa action
    if enable_alexa and options.get(CONF_ALEXA_ENTITY):
        alexa_entity = options[CONF_ALEXA_ENTITY]
        message_template = options.get(CONF_ALEXA_MESSAGE, DEFAULT_ALEXA_MESSAGE)
        
        # Build message with trigger data
        message = message_template.replace("{keyword}", "{{ trigger.event.data.keyword }}")
        message = message.replace("{unit}", "{{ trigger.event.data.unit }}")
        message = message.replace("{vehicles}", "{{ trigger.event.data.vehicles | default('Keine Fahrzeuge') }}")
        message = message.replace("{timestamp}", "{{ trigger.event.data.timestamp }}")
        
        actions.append({
            "service": "notify.alexa_media",
            "data": {
                "message": message,
                "target": alexa_entity,
                "data": {"type": "tts"}
            }
        })
        _LOGGER.debug(f"Added Alexa action for {alexa_entity}")
    
    # Light action
    light_entities = options.get(CONF_LIGHT_ENTITIES, [])
    if enable_light and light_entities:
        if isinstance(light_entities, str):
            light_entities = [l.strip() for l in light_entities.split(",") if l.strip()]
        
        color_map = {
            "red": [255, 0, 0],
            "blue": [0, 0, 255],
            "orange": [255, 165, 0],
            "white": [255, 255, 255]
        }
        color = color_map.get(options.get(CONF_LIGHT_COLOR, "red"), [255, 0, 0])
        duration = options.get(CONF_LIGHT_DURATION, DEFAULT_LIGHT_DURATION)
        
        # Turn on lights
        actions.append({
            "service": "light.turn_on",
            "target": {"entity_id": light_entities},
            "data": {
                "rgb_color": color,
                "brightness": 255
            }
        })
        
        # Add delay and turn off if duration > 0
        if duration > 0:
            actions.append({
                "delay": {"seconds": duration}
            })
            actions.append({
                "service": "light.turn_off",
                "target": {"entity_id": light_entities}
            })
        
        _LOGGER.debug(f"Added Light action for {light_entities}, duration: {duration}s")
    
    if not actions:
        _LOGGER.info("No valid actions configured")
        return
    
    # Build automation config
    automation_config = {
        "id": AUTOMATION_ID,
        "alias": "Einsatz-Monitor Alarm",
        "description": "Automatisch erstellt von der Einsatz-Monitor Integration. Wird bei jedem Speichern der Optionen aktualisiert.",
        "trigger": [
            {
                "platform": "event",
                "event_type": EVENT_NEW_ALARM
            }
        ],
        "condition": [],
        "action": actions,
        "mode": "single"
    }
    
    try:
        # Try to delete existing automation first
        try:
            await hass.services.async_call(
                "automation",
                "delete",
                {"entity_id": f"automation.{AUTOMATION_ID}"},
                blocking=True
            )
            _LOGGER.debug("Deleted existing automation")
        except Exception:
            pass  # Automation may not exist
        
        # Create automation via config file
        automations_path = Path(hass.config.path("automations.yaml"))
        
        # Read existing automations
        existing_automations = []
        if automations_path.exists():
            content = await hass.async_add_executor_job(automations_path.read_text)
            if content.strip():
                import yaml
                try:
                    existing_automations = yaml.safe_load(content) or []
                    if not isinstance(existing_automations, list):
                        existing_automations = [existing_automations]
                except Exception as e:
                    _LOGGER.warning(f"Could not parse automations.yaml: {e}")
                    existing_automations = []
        
        # Remove old einsatz monitor automation
        existing_automations = [a for a in existing_automations if a.get("id") != AUTOMATION_ID]
        
        # Add new automation
        existing_automations.append(automation_config)
        
        # Write back
        import yaml
        yaml_content = yaml.dump(existing_automations, default_flow_style=False, allow_unicode=True)
        await hass.async_add_executor_job(automations_path.write_text, yaml_content)
        
        # Reload automations
        await hass.services.async_call("automation", "reload", blocking=True)
        
        _LOGGER.info(f"Created/Updated automation '{AUTOMATION_ID}' with {len(actions)} actions")
        
    except Exception as e:
        _LOGGER.error(f"Failed to create automation: {e}")


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
        self._notified_alarm_ids = set()  # Track which alarms have been notified
    
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
                        
                        # Fire event for new alarm (automation will handle it)
                        if alarm_id not in self._notified_alarm_ids:
                            self.hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                            self._notified_alarm_ids.add(alarm_id)
                            _LOGGER.info(f"New alarm event fired: {latest.get('keyword')}")
                            
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
                            
                            # Prevent duplicates
                            if alarm_id and alarm_id in notified_ids:
                                continue
                            
                            alarm_data = {
                                "keyword": alarm.get("keyword"),
                                "unit": alarm.get("unit"),
                                "vehicles": alarm.get("vehicles"),
                                "timestamp": alarm.get("timestamp"),
                            }
                            
                            # Fire event (automation will handle it)
                            hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                            _LOGGER.info(f"WebSocket alarm event fired: {alarm.get('keyword')} (ID: {alarm_id})")
                            
                            if alarm_id:
                                notified_ids.add(alarm_id)
                                if len(notified_ids) > 100:
                                    notified_ids = set(list(notified_ids)[-50:])
                            
                            # Refresh coordinator data
                            if entry_id in hass.data.get(DOMAIN, {}):
                                coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
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
    _LOGGER.info("Card should be available at /local/einsatz_monitor/einsatz-monitor-card.js")
