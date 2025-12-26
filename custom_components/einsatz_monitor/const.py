"""Constants for Einsatz-Monitor integration."""

DOMAIN = "einsatz_monitor"

# Configuration keys
CONF_URL = "url"
CONF_TOKEN = "token"
CONF_POLL_INTERVAL = "poll_interval"
CONF_USE_WEBSOCKET = "use_websocket"

# Options keys (for Alexa/notifications)
CONF_ENABLE_ALEXA = "enable_alexa"
CONF_ALEXA_ENTITY = "alexa_entity"
CONF_ALEXA_MESSAGE = "alexa_message"
CONF_ENABLE_LIGHT = "enable_light"
CONF_LIGHT_ENTITIES = "light_entities"  # Changed to support multiple lights
CONF_LIGHT_COLOR = "light_color"
CONF_LIGHT_DURATION = "light_duration"  # New: duration in seconds
CONF_ENABLE_PUSH = "enable_push"
CONF_PUSH_SERVICE = "push_service"

# Defaults
DEFAULT_POLL_INTERVAL = 30  # seconds
DEFAULT_USE_WEBSOCKET = True
DEFAULT_ALEXA_MESSAGE = "Achtung Alarm! {keyword}. Fahrzeuge: {vehicles}"
DEFAULT_LIGHT_DURATION = 60  # seconds (0 = never turn off)

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
