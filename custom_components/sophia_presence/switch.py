# -*- coding: utf-8 -*-
"""Switches for SOPHIA Presence"""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity

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
    """Set up SOPHIA Presence switches"""
    
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # System-wide switches
    entities = [
        SophiaPresenceSystemSwitch(coordinator, entry),
        SophiaPresenceCrashDetectionSwitch(coordinator, entry),
        SophiaPresenceSpeedAlertsSwitch(coordinator, entry),
        SophiaPresenceLowBatteryAlertsSwitch(coordinator, entry),
        SophiaPresenceQuietHoursSwitch(coordinator, entry),
    ]
    
    # Per-person switches
    for person_config in entry.data.get("people", []):
        person_id = person_config[CONF_PERSON_ID]
        
        entities.extend([
            SophiaPresencePersonTrackingSwitch(coordinator, entry, person_id),
            SophiaPresencePersonPrivacySwitch(coordinator, entry, person_id),
            SophiaPresencePersonNotificationsSwitch(coordinator, entry, person_id),
        ])
    
    async_add_entities(entities)
    
    _LOGGER.info("Set up %d SOPHIA Presence switches", len(entities))


# =============================================================================
# SYSTEM-WIDE SWITCHES
# =============================================================================

class SophiaPresenceSystemSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Master switch to enable/disable SOPHIA Presence tracking"""
    
    def __init__(self, coordinator, entry):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence System"
        self._attr_unique_id = f"{DOMAIN}_system"
        self._attr_icon = "mdi:map-marker-multiple"
        self._is_on = True
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info("SOPHIA Presence system enabled")
        
        # Resume coordinator updates
        await self.coordinator.async_request_refresh()
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info("SOPHIA Presence system disabled")


class SophiaPresenceCrashDetectionSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable crash detection"""
    
    def __init__(self, coordinator, entry):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Crash Detection"
        self._attr_unique_id = f"{DOMAIN}_crash_detection"
        self._attr_icon = "mdi:car-emergency"
        self._is_on = coordinator.crash_detection_enabled
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
            self.coordinator.crash_detection_enabled = self._is_on
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.coordinator.crash_detection_enabled = True
        self.async_write_ha_state()
        _LOGGER.info("Crash detection enabled")
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.coordinator.crash_detection_enabled = False
        self.async_write_ha_state()
        _LOGGER.info("Crash detection disabled")


class SophiaPresenceSpeedAlertsSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable speed alerts"""
    
    def __init__(self, coordinator, entry):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Speed Alerts"
        self._attr_unique_id = f"{DOMAIN}_speed_alerts"
        self._attr_icon = "mdi:speedometer-slow"
        self._is_on = coordinator.speed_alerts_enabled
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
            self.coordinator.speed_alerts_enabled = self._is_on
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.coordinator.speed_alerts_enabled = True
        self.async_write_ha_state()
        _LOGGER.info("Speed alerts enabled")
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.coordinator.speed_alerts_enabled = False
        self.async_write_ha_state()
        _LOGGER.info("Speed alerts disabled")


class SophiaPresenceLowBatteryAlertsSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable low battery alerts"""
    
    def __init__(self, coordinator, entry):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Low Battery Alerts"
        self._attr_unique_id = f"{DOMAIN}_low_battery_alerts"
        self._attr_icon = "mdi:battery-alert"
        self._is_on = coordinator.low_battery_alerts_enabled
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
            self.coordinator.low_battery_alerts_enabled = self._is_on
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.coordinator.low_battery_alerts_enabled = True
        self.async_write_ha_state()
        _LOGGER.info("Low battery alerts enabled")
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.coordinator.low_battery_alerts_enabled = False
        self.async_write_ha_state()
        _LOGGER.info("Low battery alerts disabled")


class SophiaPresenceQuietHoursSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable quiet hours mode"""
    
    def __init__(self, coordinator, entry):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SOPHIA Presence Quiet Hours"
        self._attr_unique_id = f"{DOMAIN}_quiet_hours"
        self._attr_icon = "mdi:sleep"
        self._is_on = False
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info("Quiet hours enabled - notifications suppressed")
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info("Quiet hours disabled")


# =============================================================================
# PER-PERSON SWITCHES
# =============================================================================

class SophiaPresencePersonTrackingSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable tracking for a specific person"""
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Tracking"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_tracking"
        self._attr_icon = "mdi:map-marker"
        self._is_on = True
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.async_write_ha_state()
        
        person_config = self.coordinator.people.get(self._person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, self._person_id)
        
        _LOGGER.info("Enabled tracking for %s", person_name)
        
        # Trigger update
        await self.coordinator.async_request_refresh()
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.async_write_ha_state()
        
        person_config = self.coordinator.people.get(self._person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, self._person_id)
        
        _LOGGER.info("Disabled tracking for %s", person_name)


class SophiaPresencePersonPrivacySwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable privacy mode for a specific person"""
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Privacy Mode"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_privacy_mode"
        self._attr_icon = "mdi:shield-account"
        self._is_on = person_config.get("privacy_mode", False)
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.async_write_ha_state()
        
        person_config = self.coordinator.people.get(self._person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, self._person_id)
        
        _LOGGER.info("Enabled privacy mode for %s - location will be blurred to zone only", person_name)
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.async_write_ha_state()
        
        person_config = self.coordinator.people.get(self._person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, self._person_id)
        
        _LOGGER.info("Disabled privacy mode for %s", person_name)
    
    @property
    def extra_state_attributes(self):
        """Return extra attributes"""
        return {
            "description": "When enabled, precise location is hidden and only zone name is shown",
            "affects": "Location sensors and device tracker precision"
        }


class SophiaPresencePersonNotificationsSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable notifications for a specific person"""
    
    def __init__(self, coordinator, entry, person_id: str):
        """Initialize switch"""
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        
        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())
        
        self._attr_name = f"SOPHIA Presence {person_id} Notifications"
        self._attr_unique_id = f"{DOMAIN}_{person_id}_notifications"
        self._attr_icon = "mdi:bell-ring"
        self._is_on = person_config.get("enable_notifications", True)
    
    async def async_added_to_hass(self) -> None:
        """Restore last state"""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on"""
        return self._is_on
    
    async def async_turn_on(self, **kwargs):
        """Turn the switch on"""
        self._is_on = True
        self.async_write_ha_state()
        
        person_config = self.coordinator.people.get(self._person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, self._person_id)
        
        _LOGGER.info("Enabled notifications for %s", person_name)
    
    async def async_turn_off(self, **kwargs):
        """Turn the switch off"""
        self._is_on = False
        self.async_write_ha_state()
        
        person_config = self.coordinator.people.get(self._person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, self._person_id)
        
        _LOGGER.info("Disabled notifications for %s", person_name)
    
    @property
    def extra_state_attributes(self):
        """Return extra attributes"""
        return {
            "description": "Controls zone arrival/departure notifications and alerts",
            "affects": "Speed alerts, battery alerts, check-in requests"
        }