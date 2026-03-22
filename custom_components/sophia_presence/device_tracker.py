# -*- coding: utf-8 -*-
"""Device trackers for SOPHIA Presence"""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SOPHIA Presence device trackers"""
    
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # Create a device tracker for each person
    entities = []
    
    for person_config in entry.data.get("people", []):
        person_id = person_config[CONF_PERSON_ID]
        entities.append(SophiaPresenceDeviceTracker(coordinator, entry, person_id))
    
    async_add_entities(entities)
    
    _LOGGER.info("Set up %d SOPHIA Presence device trackers", len(entities))


class SophiaPresenceDeviceTracker(CoordinatorEntity, TrackerEntity):
    """Device tracker for a person tracked by SOPHIA Presence"""
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize the device tracker"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        # Get person configuration
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        # Use person_id for entity_id generation (not person_name with parentheses)
        self._attr_name = person_id
        self._attr_unique_id = f"{DOMAIN}_{person_id}"
        
        # Device tracker specific attributes
        self._attr_icon = "mdi:account"
    
    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker"""
        return SourceType.GPS
    
    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of the device"""
        if not self.coordinator.data:
            return None
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return None
        
        location = person_data.get("location", {})
        return location.get("latitude")
    
    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of the device"""
        if not self.coordinator.data:
            return None
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return None
        
        location = person_data.get("location", {})
        return location.get("longitude")
    
    @property
    def location_accuracy(self) -> int:
        """Return the location accuracy of the device in meters"""
        # Default GPS accuracy
        return 50
    
    @property
    def location_name(self) -> Optional[str]:
        """Return the location name of the device"""
        if not self.coordinator.data:
            return None
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return None
        
        location = person_data.get("location", {})
        zone = location.get("zone", "not_home")
        
        # Return zone name for Home Assistant
        if zone == "home":
            return "home"
        elif zone == "not_home":
            return None  # Let HA show "Away"
        else:
            return zone
    
    @property
    def battery_level(self) -> Optional[int]:
        """Return the battery level of the device"""
        if not self.coordinator.data:
            return None
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return None
        
        battery = person_data.get("battery")
        return int(battery) if battery is not None else None
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes"""
        if not self.coordinator.data:
            return {}
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id, {})
        
        if not person_data.get("available"):
            return {
                "available": False,
                "reason": person_data.get("reason", "Unknown")
            }
        
        location = person_data.get("location", {})
        
        attributes = {
            "person_id": self._person_id,
            "zone": location.get("zone"),
            "address": location.get("address"),
            "activity": person_data.get("activity"),
            "speed": person_data.get("speed"),
            "distance_from_home": person_data.get("distance_from_home"),
            "privacy_mode": person_data.get("privacy_mode"),
            "tracking_paused": person_data.get("tracking_paused"),
            "last_update": person_data.get("last_update"),
        }
        
        # Add battery if available
        battery = person_data.get("battery")
        if battery is not None:
            attributes["battery"] = battery
        
        return attributes
    
    @property
    def icon(self) -> str:
        """Return icon based on person's state"""
        if not self.coordinator.data:
            return "mdi:account"
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id, {})
        
        if not person_data.get("available"):
            return "mdi:account-off"
        
        # Check privacy mode
        if person_data.get("privacy_mode"):
            return "mdi:account-lock"
        
        # Check if tracking paused
        if person_data.get("tracking_paused"):
            return "mdi:account-clock"
        
        # Check activity
        activity = person_data.get("activity", "")
        if "vehicle" in activity.lower():
            return "mdi:account-arrow-right"
        
        # Check location
        location = person_data.get("location", {})
        zone = location.get("zone", "")
        
        if zone == "home":
            return "mdi:account-home"
        else:
            return "mdi:account"
    
    @property
    def available(self) -> bool:
        """Return if entity is available"""
        if not self.coordinator.last_update_success:
            return False
        
        if not self.coordinator.data:
            return False
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data:
            return False
        
        return person_data.get("available", False)