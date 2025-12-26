"""Binary sensor platform for Einsatz-Monitor."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_KEYWORD,
    ATTR_VEHICLES,
    ATTR_TIMESTAMP,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = [
        EinsatzActiveBinarySensor(coordinator, entry),
    ]
    
    async_add_entities(entities)


class EinsatzActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if there's an active/recent alarm."""
    
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active"
        self._attr_name = "Einsatz Status"
        self._attr_icon = "mdi:fire-alert"
        # No device_class for custom state text
        self._entry = entry
    
    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Einsatz-Monitor",
            "manufacturer": "FireCall Tracker",
            "model": "Cloud API",
        }
    
    @property
    def is_on(self):
        """Return true if there was an alarm in the last 30 minutes."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            ts_str = self.coordinator.data["latest"].get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    # Consider alarm "active" if within last 30 minutes
                    if datetime.now(timezone.utc) - ts < timedelta(minutes=30):
                        return True
                except:
                    pass
        return False
    
    @property
    def state(self):
        """Return the state of the sensor."""
        return "Einsatz aktiv" if self.is_on else "Kein Einsatz"
    
    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            latest = self.coordinator.data["latest"]
            return {
                ATTR_KEYWORD: latest.get("keyword"),
                ATTR_VEHICLES: latest.get("vehicles"),
                ATTR_TIMESTAMP: latest.get("timestamp"),
            }
        return {}
