# -*- coding: utf-8 -*-
"""Sensors for SOPHIA Presence"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    ACTIVITY_IN_VEHICLE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SOPHIA Presence sensors"""
    
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # System-wide sensors
    entities = [
        SophiaPresenceStatusSensor(coordinator, entry),
        SophiaPresencePeopleHomeSensor(coordinator, entry),
        SophiaPresencePeopleAwaySensor(coordinator, entry),
        SophiaPresenceTotalPeopleSensor(coordinator, entry),
        SophiaPresenceEventLogSensor(coordinator, entry),
    ]
    
    # Per-person sensors
    for person_config in entry.data.get("people", []):
        person_id = person_config[CONF_PERSON_ID]
        
        entities.extend([
            SophiaPresencePersonLocationSensor(coordinator, entry, person_id),
            SophiaPresencePersonActivitySensor(coordinator, entry, person_id),
            SophiaPresencePersonBatterySensor(coordinator, entry, person_id),
            SophiaPresencePersonSpeedSensor(coordinator, entry, person_id),
            SophiaPresencePersonDistanceSensor(coordinator, entry, person_id),
            SophiaPresencePersonHighAccuracySensor(coordinator, entry, person_id),
        ])
    
    async_add_entities(entities)
    
    _LOGGER.info("Set up %d SOPHIA Presence sensors", len(entities))


# =============================================================================
# SYSTEM-WIDE SENSORS
# =============================================================================

class SophiaPresenceStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for SOPHIA Presence overall status"""
    
    def __init__(self, coordinator, entry):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Status"
        self._attr_unique_id = f"{DOMAIN}_status"
        self._attr_icon = "mdi:map-marker-multiple"
    
    @property
    def state(self) -> str:
        """Return the state"""
        if not self.coordinator.data:
            return "initializing"
        
        statistics = self.coordinator.data.get("statistics", {})
        people_away = statistics.get("people_away", 0)
        people_home = statistics.get("people_home", 0)
        
        if people_away > 0 and people_home > 0:
            return "mixed"
        elif people_home > 0:
            return "home"
        elif people_away > 0:
            return "away"
        else:
            return "unknown"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        statistics = self.coordinator.data.get("statistics", {})
        
        return {
            "total_people": statistics.get("total_people", 0),
            "people_home": statistics.get("people_home", 0),
            "people_away": statistics.get("people_away", 0),
            "people_driving": statistics.get("people_driving", 0),
            "tracking_method": self.coordinator.tracking_method,
            "update_interval": self.coordinator.update_interval.total_seconds(),
            "ai_features_enabled": self.coordinator.ai_features_enabled,
            "crash_detection": self.coordinator.crash_detection_enabled,
            "speed_alerts": self.coordinator.speed_alerts_enabled,
            "startup_time": self.coordinator.startup_time.isoformat(),
        }


class SophiaPresencePeopleHomeSensor(CoordinatorEntity, SensorEntity):
    """Sensor for count of people at home"""
    
    def __init__(self, coordinator, entry):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence People Home"
        self._attr_unique_id = f"{DOMAIN}_people_home"
        self._attr_icon = "mdi:home-account"
        self._attr_native_unit_of_measurement = "people"
    
    @property
    def state(self) -> int:
        """Return the state"""
        if not self.coordinator.data:
            return 0
        
        statistics = self.coordinator.data.get("statistics", {})
        return statistics.get("people_home", 0)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        # Get list of people at home
        people_data = self.coordinator.data.get("people", {})
        people_home = []
        
        for person_id, person_data in people_data.items():
            if person_data.get("available") and person_data["location"]["zone"] == "home":
                people_home.append(person_data.get("name"))
        
        return {
            "people": people_home,
            "count": len(people_home)
        }


class SophiaPresencePeopleAwaySensor(CoordinatorEntity, SensorEntity):
    """Sensor for count of people away from home"""
    
    def __init__(self, coordinator, entry):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence People Away"
        self._attr_unique_id = f"{DOMAIN}_people_away"
        self._attr_icon = "mdi:home-export-outline"
        self._attr_native_unit_of_measurement = "people"
    
    @property
    def state(self) -> int:
        """Return the state"""
        if not self.coordinator.data:
            return 0
        
        statistics = self.coordinator.data.get("statistics", {})
        return statistics.get("people_away", 0)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        # Get list of people away
        people_data = self.coordinator.data.get("people", {})
        people_away = []
        
        for person_id, person_data in people_data.items():
            if person_data.get("available") and person_data["location"]["zone"] != "home":
                people_away.append(person_data.get("name"))
        
        return {
            "people": people_away,
            "count": len(people_away)
        }


class SophiaPresenceTotalPeopleSensor(CoordinatorEntity, SensorEntity):
    """Sensor for total number of tracked people"""
    
    def __init__(self, coordinator, entry):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Total People"
        self._attr_unique_id = f"{DOMAIN}_total_people"
        self._attr_icon = "mdi:account-multiple"
        self._attr_native_unit_of_measurement = "people"
    
    @property
    def state(self) -> int:
        """Return the state"""
        if not self.coordinator.data:
            return 0
        
        statistics = self.coordinator.data.get("statistics", {})
        return statistics.get("total_people", 0)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        # Get list of all tracked people
        people_data = self.coordinator.data.get("people", {})
        all_people = []
        
        for person_id, person_data in people_data.items():
            if person_data.get("available"):
                all_people.append({
                    "id": person_id,
                    "name": person_data.get("name"),
                    "zone": person_data["location"]["zone"]
                })
        
        return {
            "people": all_people,
            "configured": len(self.coordinator.people)
        }


class SophiaPresenceEventLogSensor(CoordinatorEntity, SensorEntity):
    """Sensor for SOPHIA Presence event log"""
    
    def __init__(self, coordinator, entry):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Event Log"
        self._attr_unique_id = f"{DOMAIN}_event_log"
        self._attr_icon = "mdi:text-box-multiple"
        self._events = []
        self._max_events = 20
    
    @property
    def state(self) -> int:
        """Return the number of logged events"""
        return len(self._events)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        return {
            "event_count": len(self._events),
            "events": self._events,
            "events_formatted": self._format_events_for_display()
        }
    
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator"""
        # Log significant events from coordinator
        if self.coordinator.data:
            timestamp = self.coordinator.data.get("timestamp")
            
            # Add zone change events
            zones = self.coordinator.data.get("zones", {})
            for zone_id, zone_data in zones.items():
                # Check if occupancy changed
                pass  # Events are logged by coordinator
        
        super()._handle_coordinator_update()
    
    def _format_events_for_display(self) -> str:
        """Format events as markdown for dashboard"""
        if not self._events:
            return "No events logged yet."
        
        lines = []
        for event in self._events[:10]:  # Show last 10
            timestamp = event.get("timestamp", "")
            event_type = event.get("type", "unknown")
            data = event.get("data", {})
            
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
            except:
                time_str = timestamp
            
            # Format based on event type
            if event_type == "zone_change":
                person = data.get("person_name", "Unknown")
                from_zone = data.get("from_zone", "unknown")
                to_zone = data.get("to_zone", "unknown")
                lines.append(f"- **{time_str}** ?? {person} moved from {from_zone} to {to_zone}")
            
            elif event_type == "speed_alert":
                person = data.get("person_name", "Unknown")
                speed = data.get("speed", 0)
                lines.append(f"- **{time_str}** ?? Speed alert: {person} ({speed} mph)")
            
            elif event_type == "low_battery":
                person = data.get("person_name", "Unknown")
                battery = data.get("battery_level", 0)
                lines.append(f"- **{time_str}** ?? Low battery: {person} ({battery}%)")
            
            else:
                lines.append(f"- **{time_str}** {event_type}")
        
        return "\n".join(lines)


# =============================================================================
# PER-PERSON SENSORS
# =============================================================================

class SophiaPresencePersonLocationSensor(CoordinatorEntity, SensorEntity):
    """Sensor for person's current location/zone"""
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        # Get person name from coordinator
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        # Use person_id in name for consistent entity_id generation
        self._attr_name = f"SOPHIA Presence {person_id} Location"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_location"
        self._attr_icon = "mdi:map-marker"
        
        # Store person_name for friendly display in attributes
        self._person_display_name = person_name
    
    @property
    def state(self) -> str:
        """Return the state"""
        if not self.coordinator.data:
            return "unknown"
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return "unavailable"
        
        zone = person_data["location"]["zone"]
        return zone.replace("_", " ").title()
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id, {})
        
        if not person_data.get("available"):
            return {}
        
        location = person_data.get("location", {})
        
        return {
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "zone": location.get("zone"),
            "address": location.get("address"),
            "last_update": person_data.get("last_update"),
        }


class SophiaPresencePersonActivitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for person's current activity"""
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Activity"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_activity"
    
    @property
    def state(self) -> str:
        """Return the state"""
        if not self.coordinator.data:
            return "unknown"
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return "unavailable"
        
        activity = person_data.get("activity", "unknown")
        return activity.replace("_", " ").title()
    
    @property
    def icon(self) -> str:
        """Return icon based on activity"""
        activity = self.state.lower()
        
        if "vehicle" in activity:
            return "mdi:car"
        elif "walking" in activity:
            return "mdi:walk"
        elif "running" in activity:
            return "mdi:run"
        elif "bicycle" in activity:
            return "mdi:bike"
        elif "stationary" in activity or "still" in activity:
            return "mdi:seat"
        else:
            return "mdi:help-circle"


class SophiaPresencePersonBatterySensor(CoordinatorEntity, SensorEntity):
    """Sensor for person's device battery level"""
    
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Battery"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_battery"
    
    @property
    def state(self) -> Optional[int]:
        """Return the state"""
        if not self.coordinator.data:
            return None
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return None
        
        battery = person_data.get("battery")
        return int(battery) if battery is not None else None
    
    @property
    def icon(self) -> str:
        """Return icon based on battery level"""
        battery = self.state
        
        if battery is None:
            return "mdi:battery-unknown"
        elif battery >= 90:
            return "mdi:battery"
        elif battery >= 80:
            return "mdi:battery-90"
        elif battery >= 70:
            return "mdi:battery-80"
        elif battery >= 60:
            return "mdi:battery-70"
        elif battery >= 50:
            return "mdi:battery-60"
        elif battery >= 40:
            return "mdi:battery-50"
        elif battery >= 30:
            return "mdi:battery-40"
        elif battery >= 20:
            return "mdi:battery-30"
        elif battery >= 10:
            return "mdi:battery-20"
        else:
            return "mdi:battery-10"


class SophiaPresencePersonSpeedSensor(CoordinatorEntity, SensorEntity):
    """Sensor for person's current speed"""
    
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_native_unit_of_measurement = "mph"
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Speed"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_speed"
        self._attr_icon = "mdi:speedometer"
    
    @property
    def state(self) -> Optional[float]:
        """Return the state"""
        if not self.coordinator.data:
            return 0.0
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return 0.0
        
        return person_data.get("speed", 0.0)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id, {})
        
        speed = person_data.get("speed", 0)
        activity = person_data.get("activity", "unknown")
        
        return {
            "in_vehicle": activity == ACTIVITY_IN_VEHICLE,
            "activity": activity,
            "speed_warning_threshold": self.coordinator.speed_warning_threshold,
            "speed_excessive_threshold": self.coordinator.speed_excessive_threshold,
        }


class SophiaPresencePersonDistanceSensor(CoordinatorEntity, SensorEntity):
    """Sensor for person's distance from home"""
    
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = "mi"
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize sensor"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Distance from Home"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_distance_from_home"
        self._attr_icon = "mdi:map-marker-distance"
    
    @property
    def state(self) -> Optional[float]:
        """Return the state"""
        if not self.coordinator.data:
            return 0.0
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id)
        
        if not person_data or not person_data.get("available"):
            return 0.0
        
        return person_data.get("distance_from_home", 0.0)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes"""
        if not self.coordinator.data:
            return {}
        
        people = self.coordinator.data.get("people", {})
        person_data = people.get(self._person_id, {})
        
        distance = person_data.get("distance_from_home", 0.0)
        
        # Categorize distance
        if distance == 0:
            category = "home"
        elif distance < 0.5:
            category = "very close"
        elif distance < 1.0:
            category = "close"
        elif distance < 5.0:
            category = "nearby"
        else:
            category = "far"
        
        return {
            "category": category,
            "zone": person_data.get("location", {}).get("zone", "unknown"),
        }

class SophiaPresencePersonHighAccuracySensor(CoordinatorEntity, SensorEntity):
    """Sensor showing whether high accuracy GPS is currently enabled for a person."""

    def __init__(self, coordinator, entry, person_id: str):
        """Initialize sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id

        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())

        self._attr_name = f"SOPHIA Presence {person_id} High Accuracy GPS"
        self._attr_unique_id = f"sophia_presence_{person_id}_high_accuracy"
        self._person_display_name = person_name

    @property
    def state(self) -> str:
        """Return on or off based on coordinator's last high accuracy decision."""
        enabled = self.coordinator.last_high_accuracy_state.get(self._person_id)
        if enabled is None:
            return "unknown"
        return "on" if enabled else "off"

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        state = self.state
        if state == "on":
            return "mdi:crosshairs-gps"
        elif state == "off":
            return "mdi:crosshairs"
        return "mdi:crosshairs-question"

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        enabled = self.coordinator.last_high_accuracy_state.get(self._person_id)
        people = (self.coordinator.data or {}).get("people", {})
        person_data = people.get(self._person_id, {})
        zone = person_data.get("location", {}).get("zone", "unknown") if person_data else "unknown"

        # Check if AI made this decision
        ai_decision = None
        if self.coordinator.ai:
            cached = self.coordinator.ai._last_ha_decision.get(self._person_id)
            if cached:
                ai_decision = cached[0]

        return {
            "enabled": enabled,
            "zone": zone,
            "ai_controlled": self.coordinator.ai is not None and self.coordinator.ai_features_enabled,
            "ai_last_decision": ai_decision,
            "person": self._person_display_name,
        }