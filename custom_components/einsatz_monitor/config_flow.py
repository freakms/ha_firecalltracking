"""Config flow for Einsatz-Monitor integration."""
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

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
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    url = data[CONF_URL].rstrip("/")
    token = data[CONF_TOKEN]
    
    session = async_get_clientsession(hass)
    
    try:
        async with session.get(
            f"{url}/api/ha/poll",
            params={"token": token},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 401:
                raise InvalidAuth
            response.raise_for_status()
            
    except aiohttp.ClientError as err:
        _LOGGER.error(f"Connection error: {err}")
        raise CannotConnect from err
    
    # Extract tenant info from token
    parts = token.split("_")
    tenant_id = parts[1] if len(parts) > 2 else "unknown"
    
    return {"title": f"Einsatz-Monitor ({tenant_id})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Einsatz-Monitor."""
    
    VERSION = 1
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): str,
                    vol.Required(CONF_TOKEN): str,
                    vol.Optional(
                        CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                    vol.Optional(
                        CONF_USE_WEBSOCKET, default=DEFAULT_USE_WEBSOCKET
                    ): bool,
                }
            ),
            errors=errors,
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Einsatz-Monitor."""
    
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage all options in one page."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Convert light entities list to comma-separated string for storage
            if "light_entities_select" in user_input:
                user_input[CONF_LIGHT_ENTITIES] = user_input.pop("light_entities_select")
            return self.async_create_entry(title="", data=user_input)
        
        # Find all media_player entities (Alexa devices)
        media_players = [""]
        for state in self.hass.states.async_all("media_player"):
            media_players.append(state.entity_id)
        media_players.sort()
        
        # Find all light entities
        lights = []
        for state in self.hass.states.async_all("light"):
            lights.append(state.entity_id)
        lights.sort()
        
        # Get current values
        current = self.config_entry.options
        current_lights = current.get(CONF_LIGHT_ENTITIES, [])
        if isinstance(current_lights, str):
            current_lights = [l.strip() for l in current_lights.split(",") if l.strip()]
        
        schema = vol.Schema({
            # Alexa settings
            vol.Optional(
                CONF_ENABLE_ALEXA,
                default=current.get(CONF_ENABLE_ALEXA, False)
            ): bool,
            vol.Optional(
                CONF_ALEXA_ENTITY,
                default=current.get(CONF_ALEXA_ENTITY, "")
            ): vol.In(media_players),
            vol.Optional(
                CONF_ALEXA_MESSAGE,
                default=current.get(CONF_ALEXA_MESSAGE, DEFAULT_ALEXA_MESSAGE)
            ): str,
            # Light settings
            vol.Optional(
                CONF_ENABLE_LIGHT,
                default=current.get(CONF_ENABLE_LIGHT, False)
            ): bool,
            vol.Optional(
                "light_entities_select",
                default=current_lights
            ): cv.multi_select(dict.fromkeys(lights)),
            vol.Optional(
                CONF_LIGHT_COLOR,
                default=current.get(CONF_LIGHT_COLOR, "red")
            ): vol.In(["red", "blue", "orange", "white"]),
            vol.Optional(
                CONF_LIGHT_DURATION,
                default=current.get(CONF_LIGHT_DURATION, DEFAULT_LIGHT_DURATION)
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
        })
        
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
