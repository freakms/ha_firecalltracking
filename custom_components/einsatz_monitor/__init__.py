"""Einsatz-Monitor Integration for Home Assistant.

by freakms - ich schwöre feierlich ich bin ein tunichtgut
"""
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
    CONF_ENABLE_SPEAKER,
    CONF_SPEAKER_ENTITY,
    CONF_SPEAKER_TYPE,
    CONF_SPEAKER_MESSAGE,
    CONF_ENABLE_LIGHT,
    CONF_LIGHT_ENTITIES,
    CONF_LIGHT_COLOR,
    CONF_LIGHT_DURATION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_USE_WEBSOCKET,
    DEFAULT_SPEAKER_MESSAGE,
    DEFAULT_LIGHT_DURATION,
    EVENT_NEW_ALARM,
    PLATFORMS,
    SPEAKER_TYPE_ALEXA,
    SPEAKER_TYPE_SONOS,
    SPEAKER_TYPE_GOOGLE,
    SPEAKER_TYPE_GENERIC_TTS,
)

_LOGGER = logging.getLogger(__name__)

CARD_DIR = Path(__file__).parent / "www"
CARD_FILENAME = "einsatz-monitor-card.js"
CARD_URL_PATH = f"/einsatz_monitor/{CARD_FILENAME}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Einsatz-Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

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

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "url": url,
        "token": token,
    }

    if use_websocket:
        entry.async_create_background_task(
            hass,
            _start_websocket_background(hass, entry, url, token),
            f"einsatz_monitor_websocket_{entry.entry_id}"
        )

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

                if alarms and len(alarms) > 0:
                    latest = alarms[0]
                    alarm_id = latest.get("id")

                    # Nur feuern wenn diese ID noch nicht verarbeitet wurde
                    # (WebSocket könnte sie schon eingetragen haben)
                    if alarm_id and alarm_id not in self._notified_alarm_ids:
                        self.last_alarm_id = alarm_id
                        self._notified_alarm_ids.add(alarm_id)

                        alarm_data = {
                            "keyword": latest.get("keyword"),
                            "unit": latest.get("unit"),
                            "vehicles": latest.get("vehicles"),
                            "timestamp": latest.get("timestamp"),
                            "tenant_name": latest.get("tenant_name"),
                        }

                        self.hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                        _LOGGER.info(f"New alarm event fired (polling): {latest.get('keyword')}")

                        await self._handle_alarm_notifications(alarm_data, alarm_id)

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

        # Speaker-Benachrichtigung (Alexa / Sonos / Google / TTS)
        # Unterstützt neues Format (enable_speaker) und Legacy (enable_alexa)
        enable_speaker = options.get(CONF_ENABLE_SPEAKER, options.get("enable_alexa", False))
        speaker_entity = options.get(CONF_SPEAKER_ENTITY, options.get("alexa_entity", ""))

        if enable_speaker and speaker_entity:
            try:
                await self._send_speaker_notification(alarm_data, options)
            except Exception as e:
                _LOGGER.error(f"Speaker-Notification fehlgeschlagen: {e} — Integration läuft weiter.")

        # Licht-Alarm
        light_entities = options.get(CONF_LIGHT_ENTITIES, [])
        if options.get(CONF_ENABLE_LIGHT) and light_entities:
            try:
                await self._activate_light_alert(alarm_data, options)
            except Exception as e:
                _LOGGER.error(f"Licht-Alarm fehlgeschlagen: {e} — Integration läuft weiter.")

    async def _send_speaker_notification(self, alarm_data: dict, options: dict):
        """
        Send voice notification via speaker.
        Unterstützt: Alexa (alexa_media_player), Sonos, Google Home, generisches TTS.
        """
        speaker_type = options.get(CONF_SPEAKER_TYPE, SPEAKER_TYPE_ALEXA)
        speaker_entity = options.get(CONF_SPEAKER_ENTITY, options.get("alexa_entity", ""))
        message_template = options.get(
            CONF_SPEAKER_MESSAGE,
            options.get("alexa_message", DEFAULT_SPEAKER_MESSAGE)
        )

        if not speaker_entity:
            _LOGGER.warning("Kein Speaker-Entity konfiguriert")
            return

        try:
            message = message_template.format(
                keyword=alarm_data.get("keyword", "Unbekannt"),
                unit=alarm_data.get("unit", ""),
                vehicles=alarm_data.get("vehicles", "Keine Fahrzeuge"),
                timestamp=alarm_data.get("timestamp", "")
            )
        except KeyError as e:
            _LOGGER.warning(f"Ungültiger Platzhalter in Nachrichtenvorlage: {e}")
            message = f"Alarm: {alarm_data.get('keyword', 'Unbekannt')}"

        # Wortanzahl für Wartezeit berechnen
        word_count = len(message.split())
        wait_time = max(5, word_count * 0.75 + 3)

        try:
            if speaker_type == SPEAKER_TYPE_ALEXA:
                # Alexa Media Player (HACS: alexa_media_player)
                # Service-Name dynamisch ermitteln:
                # Neuere alexa_media_player Versionen nutzen notify.alexa_media,
                # ältere oder gerätespezifische nutzen notify.alexa_media_{gerätename}
                alexa_service = None

                if self.hass.services.has_service("notify", "alexa_media"):
                    alexa_service = "alexa_media"
                else:
                    # Alle notify-Services durchsuchen die mit alexa beginnen
                    all_notify = self.hass.services.async_services().get("notify", {})
                    alexa_services = [s for s in all_notify if s.startswith("alexa")]
                    if alexa_services:
                        # Ersten verfügbaren nehmen
                        alexa_service = alexa_services[0]
                        _LOGGER.debug(f"Alexa Service gefunden: notify.{alexa_service}")

                if not alexa_service:
                    _LOGGER.error(
                        "Alexa-Sprachausgabe: Kein Alexa notify-Service gefunden. "
                        "Bitte die HACS-Integration 'alexa_media_player' installieren und "
                        "einrichten: https://github.com/alandtse/alexa_media_player. "
                        "Verfügbare notify-Services: "
                        + str(list(self.hass.services.async_services().get("notify", {}).keys()))
                    )
                    return

                await self.hass.services.async_call(
                    "notify",
                    alexa_service,
                    {
                        "message": message,
                        "target": speaker_entity,
                        "data": {"type": "tts"}
                    },
                    blocking=False,
                )
                _LOGGER.info(f"Alexa TTS gesendet via notify.{alexa_service} an {speaker_entity}")

            elif speaker_type == SPEAKER_TYPE_SONOS:
                # Sonos über media_player.play_media
                await self.hass.services.async_call(
                    "tts",
                    "google_translate_say",
                    {
                        "entity_id": speaker_entity,
                        "message": message,
                        "language": "de",
                    },
                    blocking=False,
                )
                _LOGGER.info(f"Sonos TTS gesendet an {speaker_entity}")

            elif speaker_type == SPEAKER_TYPE_GOOGLE:
                # Google Home / Nest über tts.google_translate_say
                await self.hass.services.async_call(
                    "tts",
                    "google_translate_say",
                    {
                        "entity_id": speaker_entity,
                        "message": message,
                        "language": "de",
                    },
                    blocking=False,
                )
                _LOGGER.info(f"Google TTS gesendet an {speaker_entity}")

            elif speaker_type == SPEAKER_TYPE_GENERIC_TTS:
                # Generisches TTS — funktioniert mit fast allen Speakern
                await self.hass.services.async_call(
                    "tts",
                    "speak",
                    {
                        "media_player_entity_id": speaker_entity,
                        "message": message,
                        "language": "de-DE",
                    },
                    blocking=False,
                )
                _LOGGER.info(f"Generisches TTS gesendet an {speaker_entity}")

            # Nach Ansage stoppen (verhindert Endlos-Loop)
            async def stop_speaker():
                await asyncio.sleep(wait_time)
                for attempt in range(3):
                    try:
                        await self.hass.services.async_call(
                            "media_player",
                            "media_stop",
                            {"entity_id": speaker_entity},
                            blocking=False,
                        )
                        _LOGGER.debug(f"Speaker stop Versuch {attempt + 1}")
                    except Exception:
                        pass
                    await asyncio.sleep(2)

            self.hass.async_create_task(stop_speaker())

        except Exception as e:
            _LOGGER.error(
                f"Fehler bei Speaker-Benachrichtigung ({speaker_type}): {e} — "
                f"Sprachausgabe wird übersprungen, Integration läuft weiter."
            )
            # Exception NICHT weiterwerfen — Coordinator darf nicht crashen

    async def _activate_light_alert(self, alarm_data: dict, options: dict):
        """Activate light alert — speichert vorherigen Zustand und stellt ihn danach wieder her."""
        color_map = {
            "red": [255, 0, 0],
            "blue": [0, 0, 255],
            "orange": [255, 165, 0],
            "white": [255, 255, 255],
        }
        color = color_map.get(options.get(CONF_LIGHT_COLOR, "red"), [255, 0, 0])

        light_entities = options.get(CONF_LIGHT_ENTITIES, [])
        if isinstance(light_entities, str):
            light_entities = [l.strip() for l in light_entities.split(",") if l.strip()]

        if not light_entities:
            return

        duration = options.get(CONF_LIGHT_DURATION, DEFAULT_LIGHT_DURATION)

        # Vorherige Zustände speichern
        previous_states = {}
        for entity_id in light_entities:
            state = self.hass.states.get(entity_id)
            if state:
                previous_states[entity_id] = {
                    "state": state.state,
                    "attributes": dict(state.attributes),
                }

        try:
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
            _LOGGER.info(f"Licht-Alarm aktiviert für {len(light_entities)} Lampen")

            if duration > 0:
                async def restore_lights():
                    await asyncio.sleep(duration)
                    try:
                        for entity_id, prev in previous_states.items():
                            if prev["state"] == "on":
                                restore_data = {"entity_id": entity_id}
                                if "brightness" in prev["attributes"]:
                                    restore_data["brightness"] = prev["attributes"]["brightness"]
                                if "rgb_color" in prev["attributes"]:
                                    restore_data["rgb_color"] = prev["attributes"]["rgb_color"]
                                elif "color_temp" in prev["attributes"]:
                                    restore_data["color_temp"] = prev["attributes"]["color_temp"]
                                await self.hass.services.async_call(
                                    "light", "turn_on", restore_data, blocking=False
                                )
                            else:
                                await self.hass.services.async_call(
                                    "light", "turn_off",
                                    {"entity_id": entity_id}, blocking=False
                                )
                        _LOGGER.info(f"Lichtzustand wiederhergestellt nach {duration}s")
                    except Exception as e:
                        _LOGGER.error(f"Fehler beim Wiederherstellen der Lichter: {e}")

                self.hass.async_create_task(restore_lights())

        except Exception as e:
            _LOGGER.error(f"Fehler beim Licht-Alarm: {e}")


async def _start_websocket_background(
    hass: HomeAssistant, entry: ConfigEntry, url: str, token: str
):
    """Wrapper to start WebSocket in background without blocking."""
    await asyncio.sleep(10)
    await start_websocket(hass, entry, url, token)


async def start_websocket(
    hass: HomeAssistant, entry: ConfigEntry, url: str, token: str
):
    """
    Start WebSocket connection for real-time updates.

    Fix v2: WebSocket und Polling teilen coordinator._notified_alarm_ids.
    Jede alarm_id wird sofort in BEIDEN Sets eingetragen damit keine
    Doppelauslösung (Speaker/Licht) stattfinden kann.
    """
    ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/api/ha/ws/{token}"
    entry_id = entry.entry_id
    notified_ids = set()
    retry_count = 0
    max_retries = 5

    while retry_count < max_retries:
        try:
            session = async_get_clientsession(hass)

            async with async_timeout.timeout(10):
                ws = await session.ws_connect(ws_url)

            _LOGGER.info("WebSocket verbunden mit Einsatz-Monitor")
            retry_count = 0

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.json()

                    if data.get("type") == "alarm":
                        alarm = data.get("data", {})
                        alarm_id = alarm.get("id")

                        # Coordinator holen
                        coordinator = None
                        if entry_id in hass.data.get(DOMAIN, {}):
                            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]

                        # Bereits verarbeitet? (von WebSocket ODER Polling)
                        if alarm_id:
                            already_done = alarm_id in notified_ids
                            if coordinator:
                                already_done = already_done or (
                                    alarm_id in coordinator._notified_alarm_ids
                                )
                            if already_done:
                                _LOGGER.debug(
                                    f"WebSocket: Alarm {alarm_id} bereits verarbeitet, übersprungen"
                                )
                                continue

                        # Sofort in BEIDE Sets eintragen bevor Notifications
                        if alarm_id:
                            notified_ids.add(alarm_id)
                            if coordinator:
                                coordinator._notified_alarm_ids.add(alarm_id)
                                if len(coordinator._notified_alarm_ids) > 100:
                                    coordinator._notified_alarm_ids = set(
                                        list(coordinator._notified_alarm_ids)[-50:]
                                    )
                            if len(notified_ids) > 100:
                                notified_ids = set(list(notified_ids)[-50:])

                        alarm_data = {
                            "keyword": alarm.get("keyword"),
                            "unit": alarm.get("unit"),
                            "vehicles": alarm.get("vehicles"),
                            "timestamp": alarm.get("timestamp"),
                        }

                        # Event feuern und Notifications senden
                        hass.bus.async_fire(EVENT_NEW_ALARM, alarm_data)
                        _LOGGER.info(
                            f"WebSocket alarm event: {alarm.get('keyword')}"
                        )

                        if coordinator:
                            await coordinator._handle_alarm_notifications(
                                alarm_data, alarm_id
                            )
                            await coordinator.async_request_refresh()
                        else:
                            _LOGGER.warning(
                                "WebSocket: Kein Coordinator verfügbar für Notifications"
                            )

                    elif data.get("type") == "ping":
                        await ws.send_str("pong")

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break

        except asyncio.TimeoutError:
            retry_count += 1
            _LOGGER.warning(
                f"WebSocket Timeout ({retry_count}/{max_retries}). Nächster Versuch in 60s..."
            )
        except aiohttp.ClientResponseError as err:
            if err.status == 404:
                _LOGGER.warning(
                    f"WebSocket Endpoint nicht erreichbar (404). Polling läuft weiter. "
                    f"URL: {ws_url}"
                )
                return
            retry_count += 1
            _LOGGER.warning(
                f"WebSocket HTTP-Fehler {err.status} ({retry_count}/{max_retries}). "
                f"Nächster Versuch in 60s..."
            )
        except aiohttp.ClientError as err:
            retry_count += 1
            if "404" in str(err):
                _LOGGER.warning("WebSocket 404. Polling läuft weiter.")
                return
            _LOGGER.warning(
                f"WebSocket Verbindungsfehler ({retry_count}/{max_retries}): {err}. "
                f"Nächster Versuch in 60s..."
            )
        except Exception as err:
            retry_count += 1
            _LOGGER.warning(
                f"WebSocket Fehler ({retry_count}/{max_retries}): {err}. "
                f"Nächster Versuch in 60s..."
            )

        if retry_count >= max_retries:
            _LOGGER.warning(
                f"WebSocket nach {max_retries} Versuchen deaktiviert. Polling läuft weiter."
            )
            return

        await asyncio.sleep(60)


async def async_register_card(hass: HomeAssistant):
    """Register the custom Lovelace card automatically."""
    card_path = CARD_DIR / CARD_FILENAME

    if not card_path.exists():
        _LOGGER.error(f"Card-Datei nicht gefunden: {card_path}")
        return

    try:
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths([
            StaticPathConfig(CARD_URL_PATH, str(card_path), cache_headers=False)
        ])
        _LOGGER.info(f"Card-Pfad registriert: {CARD_URL_PATH}")
    except ImportError:
        try:
            hass.http.register_static_path(
                CARD_URL_PATH, str(card_path), cache_headers=False
            )
        except AttributeError:
            _LOGGER.warning(f"Statischer Pfad konnte nicht registriert werden. "
                            f"Manuell hinzufügen: {CARD_URL_PATH}")
            return
    except Exception as e:
        if "already registered" in str(e).lower():
            _LOGGER.debug(f"Statischer Pfad bereits registriert: {CARD_URL_PATH}")
        else:
            _LOGGER.warning(f"Fehler beim Registrieren des statischen Pfads: {e}")

    async def _async_register_lovelace_resource(_event=None):
        try:
            from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
            from homeassistant.components.lovelace.resources import ResourceStorageCollection

            await asyncio.sleep(5)

            if LOVELACE_DOMAIN not in hass.data:
                _LOGGER.warning(
                    f"Lovelace nicht verfügbar. Ressource manuell hinzufügen: {CARD_URL_PATH}"
                )
                return

            lovelace_data = hass.data[LOVELACE_DOMAIN]
            resources = getattr(lovelace_data, "resources", None)
            if resources is None:
                resources = lovelace_data.get("resources") if isinstance(lovelace_data, dict) else None

            if not resources or not isinstance(resources, ResourceStorageCollection):
                _LOGGER.info(f"Lovelace-Ressourcen nicht verfügbar. Manuell hinzufügen: {CARD_URL_PATH}")
                return

            existing = [
                r for r in resources.async_items()
                if CARD_FILENAME in r.get("url", "")
            ]

            if existing:
                correct = [r for r in existing if r.get("url", "").startswith("/einsatz_monitor/")]
                if correct:
                    _LOGGER.debug("Card-Ressource bereits korrekt registriert")
                    return
                else:
                    _LOGGER.warning(f"Card-Ressource hat falsche URL. "
                                    f"Bitte auf {CARD_URL_PATH} aktualisieren.")
                    return

            await resources.async_create_item({
                "url": CARD_URL_PATH,
                "res_type": "module"
            })
            _LOGGER.info(f"Lovelace-Ressource hinzugefügt: {CARD_URL_PATH}")

        except ImportError as e:
            _LOGGER.info(f"Bitte Lovelace-Ressource manuell hinzufügen: {CARD_URL_PATH}")
        except Exception as e:
            _LOGGER.warning(f"Konnte Lovelace-Ressource nicht registrieren: {e}. "
                            f"Bitte manuell hinzufügen: {CARD_URL_PATH}")

    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

    if hass.is_running:
        hass.async_create_task(_async_register_lovelace_resource())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_register_lovelace_resource)
