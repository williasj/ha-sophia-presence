# -*- coding: utf-8 -*-
"""Text entities for SOPHIA Presence - zone name input fields."""
import logging
from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    CONF_PEOPLE,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SOPHIA Presence text entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = []
    for person_config in entry.data.get(CONF_PEOPLE, []):
        person_id = person_config[CONF_PERSON_ID]
        entities.append(SophiaPresenceZoneNameInput(coordinator, entry, person_id))

    async_add_entities(entities)
    _LOGGER.info("Set up %d SOPHIA Presence text entities", len(entities))


class SophiaPresenceZoneNameInput(RestoreEntity, TextEntity):
    """Text input for naming a new zone at a person's current location."""

    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 50
    _attr_pattern = None
    _attr_icon = "mdi:map-marker-plus"

    def __init__(self, coordinator, entry, person_id: str) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._person_id = person_id

        person_config = coordinator.people.get(person_id, {})
        person_name = person_config.get(CONF_PERSON_NAME, person_id.title())

        self._attr_name = f"SOPHIA Presence {person_id} New Zone Name"
        self._attr_unique_id = f"sophia_presence_{person_id}_new_zone_name"
        self._person_display_name = person_name
        self._attr_native_value = ""  # min=0 allows empty

    async def async_added_to_hass(self) -> None:
        """Restore previous value on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unavailable", "unknown"):
            self._attr_native_value = last_state.state

    async def async_set_value(self, value: str) -> None:
        """Set the zone name input value."""
        self._attr_native_value = value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Return helpful attributes."""
        people = (self._coordinator.data or {}).get("people", {})
        person_data = people.get(self._person_id, {})
        location = person_data.get("location", {}) if person_data else {}
        return {
            "person": self._person_display_name,
            "current_latitude": location.get("latitude"),
            "current_longitude": location.get("longitude"),
            "current_zone": location.get("zone", "unknown"),
            "hint": f"Type a name then press Add Zone for {self._person_display_name}",
        }