"""Constants for Einsatz-Monitor integration.

by freakms - ich schwöre feierlich ich bin ein tunichtgut
"""

DOMAIN = "einsatz_monitor"

# Configuration keys
CONF_URL = "url"
CONF_TOKEN = "token"
CONF_POLL_INTERVAL = "poll_interval"
CONF_USE_WEBSOCKET = "use_websocket"

# Options keys
CONF_ENABLE_SPEAKER = "enable_speaker"
CONF_SPEAKER_ENTITY = "speaker_entity"
CONF_SPEAKER_TYPE = "speaker_type"       # alexa | sonos | google | generic_tts
CONF_SPEAKER_MESSAGE = "speaker_message"
CONF_ENABLE_LIGHT = "enable_light"
CONF_LIGHT_ENTITIES = "light_entities"
CONF_LIGHT_COLOR = "light_color"
CONF_LIGHT_DURATION = "light_duration"
CONF_ENABLE_PUSH = "enable_push"
CONF_PUSH_SERVICE = "push_service"

# Legacy keys (keep for backwards compat)
CONF_ENABLE_ALEXA = "enable_alexa"
CONF_ALEXA_ENTITY = "alexa_entity"
CONF_ALEXA_MESSAGE = "alexa_message"

# Speaker types
SPEAKER_TYPE_ALEXA = "alexa"
SPEAKER_TYPE_SONOS = "sonos"
SPEAKER_TYPE_GOOGLE = "google"
SPEAKER_TYPE_GENERIC_TTS = "generic_tts"

SPEAKER_TYPE_OPTIONS = [
    SPEAKER_TYPE_ALEXA,
    SPEAKER_TYPE_SONOS,
    SPEAKER_TYPE_GOOGLE,
    SPEAKER_TYPE_GENERIC_TTS,
]

SPEAKER_TYPE_LABELS = {
    SPEAKER_TYPE_ALEXA: "Amazon Alexa (alexa_media_player HACS)",
    SPEAKER_TYPE_SONOS: "Sonos",
    SPEAKER_TYPE_GOOGLE: "Google Home / Nest",
    SPEAKER_TYPE_GENERIC_TTS: "Generisches TTS (tts.speak)",
}

# Defaults
DEFAULT_POLL_INTERVAL = 30
DEFAULT_USE_WEBSOCKET = True
DEFAULT_SPEAKER_MESSAGE = "Achtung Alarm! {keyword}. Fahrzeuge: {vehicles}"
DEFAULT_LIGHT_DURATION = 60

# Legacy default
DEFAULT_ALEXA_MESSAGE = DEFAULT_SPEAKER_MESSAGE

# Platforms
PLATFORMS = ["sensor", "binary_sensor"]

# Attributes
ATTR_KEYWORD = "keyword"
ATTR_UNIT = "unit"
ATTR_VEHICLES = "vehicles"
ATTR_TIMESTAMP = "timestamp"
ATTR_TENANT_ID = "tenant_id"
ATTR_TENANT_NAME = "tenant_name"
ATTR_ALARM_COUNT = "alarm_count"
ATTR_LAST_ALARM = "last_alarm"

# Events
EVENT_NEW_ALARM = f"{DOMAIN}_new_alarm"
