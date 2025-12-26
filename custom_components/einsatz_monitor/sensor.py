"""Sensor platform for Einsatz-Monitor."""
from __future__ import annotations

import logging
import json
from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_KEYWORD,
    ATTR_UNIT,
    ATTR_VEHICLES,
    ATTR_TIMESTAMP,
    ATTR_TENANT_NAME,
    ATTR_ALARM_COUNT,
    ATTR_LAST_ALARM,
)

_LOGGER = logging.getLogger(__name__)


def get_einsatz_type(keyword: str) -> str:
    """Determine incident type from keyword."""
    if not keyword:
        return "unknown"
    
    keyword_upper = keyword.upper()
    
    # Brand-Einsätze (Fire)
    if any(k in keyword_upper for k in ["BRAND", "FEUER", "B1", "B2", "B3", "B4", "B5", "B ", "GMA", "BMA"]):
        return "fire"
    
    # Technische Hilfe / Verkehrsunfall (Technical Help / Traffic Accident)
    if any(k in keyword_upper for k in ["TH", "VU", "VERKEHR", "UNFALL", "H1", "H2", "H3", "H4", "H5", "HILFE", "THL", "PERSON"]):
        return "technical"
    
    # Gefahrgut (Hazmat)
    if any(k in keyword_upper for k in ["GEFAHRGUT", "ABC", "GSG", "GAS", "ÖL", "CHEMIE"]):
        return "hazmat"
    
    return "other"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = [
        EinsatzCountSensor(coordinator, entry),
        EinsatzKeywordSensor(coordinator, entry),
        EinsatzVehiclesSensor(coordinator, entry),
        EinsatzTimestampSensor(coordinator, entry),
        EinsatzListSensor(coordinator, entry),  # NEW: Last 5 incidents
    ]
    
    async_add_entities(entities)


class EinsatzBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Einsatz-Monitor sensors."""
    
    def __init__(self, coordinator, entry: ConfigEntry, suffix: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
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


class EinsatzCountSensor(EinsatzBaseSensor):
    """Sensor showing the number of alarms in the last 24h."""
    
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "alarm_count")
        self._attr_name = "Einsätze (24h)"
        self._attr_icon = "mdi:fire-truck"
        self._attr_state_class = SensorStateClass.TOTAL
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("count", 0)
        return 0
    
    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            latest = self.coordinator.data["latest"]
            return {
                ATTR_LAST_ALARM: latest.get("keyword"),
                ATTR_TENANT_NAME: latest.get("tenant_name"),
            }
        return {}


class EinsatzKeywordSensor(EinsatzBaseSensor):
    """Sensor showing the keyword of the latest alarm."""
    
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "latest_keyword")
        self._attr_name = "Letzter Einsatz - Stichwort"
        self._attr_icon = "mdi:alert"
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            return self.coordinator.data["latest"].get("keyword")
        return "Kein Einsatz"
    
    @property
    def icon(self):
        """Return dynamic icon based on incident type."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            keyword = self.coordinator.data["latest"].get("keyword", "")
            einsatz_type = get_einsatz_type(keyword)
            if einsatz_type == "fire":
                return "mdi:fire"
            elif einsatz_type == "technical":
                return "mdi:car-emergency"
            elif einsatz_type == "hazmat":
                return "mdi:hazard-lights"
        return "mdi:alert"
    
    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            latest = self.coordinator.data["latest"]
            return {
                ATTR_UNIT: latest.get("unit"),
                ATTR_VEHICLES: latest.get("vehicles"),
                ATTR_TIMESTAMP: latest.get("timestamp"),
                "einsatz_type": get_einsatz_type(latest.get("keyword", "")),
            }
        return {}


class EinsatzVehiclesSensor(EinsatzBaseSensor):
    """Sensor showing the vehicles of the latest alarm."""
    
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "latest_vehicles")
        self._attr_name = "Letzter Einsatz - Fahrzeuge"
        self._attr_icon = "mdi:truck"
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            return self.coordinator.data["latest"].get("vehicles") or "Keine"
        return "Keine"


class EinsatzTimestampSensor(EinsatzBaseSensor):
    """Sensor showing the timestamp of the latest alarm."""
    
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "latest_timestamp")
        self._attr_name = "Letzter Einsatz - Zeit"
        self._attr_icon = "mdi:clock"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data and self.coordinator.data.get("latest"):
            ts = self.coordinator.data["latest"].get("timestamp")
            if ts:
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except:
                    pass
        return None


class EinsatzListSensor(EinsatzBaseSensor):
    """Sensor showing the last 5 incidents with full details."""
    
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "einsatz_liste")
        self._attr_name = "Letzte Einsätze"
        self._attr_icon = "mdi:format-list-bulleted"
    
    @property
    def native_value(self):
        """Return the number of recent incidents."""
        if self.coordinator.data and self.coordinator.data.get("alarms"):
            return min(len(self.coordinator.data["alarms"]), 5)
        return 0
    
    @property
    def extra_state_attributes(self):
        """Return the last 5 incidents as attributes."""
        if self.coordinator.data and self.coordinator.data.get("alarms"):
            alarms = self.coordinator.data["alarms"][:5]  # Last 5
            
            einsatz_list = []
            for alarm in alarms:
                keyword = alarm.get("keyword", "")
                einsatz_type = get_einsatz_type(keyword)
                
                einsatz_list.append({
                    "id": alarm.get("id"),
                    "keyword": keyword,
                    "unit": alarm.get("unit"),
                    "vehicles": alarm.get("vehicles"),
                    "timestamp": alarm.get("timestamp"),
                    "type": einsatz_type,
                })
            
            return {
                "einsaetze": einsatz_list,
                "einsaetze_json": json.dumps(einsatz_list, ensure_ascii=False),
                "count": len(einsatz_list),
            }
        return {"einsaetze": [], "einsaetze_json": "[]", "count": 0}
