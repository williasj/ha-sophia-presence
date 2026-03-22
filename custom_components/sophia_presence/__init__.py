# -*- coding: utf-8 -*-
"""
SOPHIA Presence - Family location tracking with AI intelligence
Integrates with SOPHIA Core for LLM access, event bus, and dashboard generation
"""
import asyncio
import logging
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import math

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.location import distance as distance_calc

from .const import (
    DOMAIN,
    VERSION,
    PLATFORMS,
    SERVICES,
    CONF_PEOPLE,
    CONF_UPDATE_INTERVAL,
    CONF_TRACKING_METHOD,
    CONF_CRASH_DETECTION,
    CONF_SPEED_ALERTS,
    CONF_LOW_BATTERY_ALERTS,
    CONF_HOME_ZONE,
    CONF_USE_HA_ZONES,
    CONF_ZONE_NOTIFICATIONS,
    CONF_ZONE_AUTO_SUGGEST,
    CONF_AI_FEATURES,
    CONF_AI_FEATURES_LIST,
    CONF_FIRE_EVENTS,
    CONF_SPEED_WARNING_THRESHOLD,
    CONF_SPEED_EXCESSIVE_THRESHOLD,
    CONF_BATTERY_ALERT_THRESHOLD,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_DEVICE_TRACKER,
    CONF_ACTIVITY_SENSOR,
    CONF_BATTERY_SENSOR,
    CONF_PRIVACY_MODE,
    CONF_NOTIFY_SERVICE,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_ZONE_RADIUS,
    EVENT_PERSON_ENTERED_ZONE,
    EVENT_PERSON_EXITED_ZONE,
    EVENT_EVERYONE_AWAY,
    EVENT_FIRST_PERSON_HOME,
    EVENT_SPEED_ALERT,
    EVENT_CRASH_DETECTED,
    EVENT_LOW_BATTERY,
    EVENT_SOS_TRIGGERED,
    EVENT_ZONE_SUGGESTED,
    EVENT_LOCATION_UPDATED,
    ACTIVITY_IN_VEHICLE,
    SPEED_STOPPED,
    ZONE_HYSTERESIS_FACTOR,
    MIN_ZONE_DWELL_TIME,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    SEVERITY_CRITICAL,
)

from .ai import PresenceAI

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up SOPHIA Presence from configuration.yaml (legacy)"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SOPHIA Presence from a config entry"""
    
    _LOGGER.info("Setting up SOPHIA Presence v%s...", VERSION)
    
    # Wait for SOPHIA Core to be ready
    if "sophia_core" not in hass.data:
        _LOGGER.error("SOPHIA Core not found! Presence module requires Core.")
        return False
    
    # Get references to Core services
    core_data = hass.data["sophia_core"]
    registry = core_data["registry"]
    llm_client = core_data["llm_client"]
    event_logger = core_data["event_logger"]
    
    # Store module data
    hass.data.setdefault(DOMAIN, {})
    
    # Create coordinator for presence tracking
    coordinator = SophiaPresenceCoordinator(hass, entry, llm_client, event_logger)
    await coordinator.async_config_entry_first_refresh()

    # Wire up AI if enabled
    if coordinator.ai_features_enabled:
        coordinator.ai = PresenceAI(llm_client, coordinator)
        hass.async_create_task(coordinator.ai.ensure_collections())
        _LOGGER.info("SOPHIA Presence AI features enabled, RAG collections initializing")
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "llm_client": llm_client,
        "event_logger": event_logger,
        "config": entry.data
    }
    
    # Build capabilities dict with dashboard configuration
    capabilities = {
        "name": "SOPHIA Presence",
        "version": VERSION,
        "services": SERVICES,
        "sensors": _build_sensor_list(entry),
        "device_trackers": _build_device_tracker_list(entry),
        "switches": _build_switch_list(entry),
        "requires_llm": entry.data.get(CONF_AI_FEATURES, False),
        "metadata": {
            "people_count": len(entry.data.get(CONF_PEOPLE, [])),
            "people": [p[CONF_PERSON_NAME] for p in entry.data.get(CONF_PEOPLE, [])],
            "update_interval": entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            "tracking_method": entry.data.get(CONF_TRACKING_METHOD),
            "description": "AI-powered family location tracking with geofencing and safety features"
        },
        
        # Dashboard configuration (defined in Python!)
        "dashboard_config": _build_dashboard_config(entry)
    }
    
    # Register with SOPHIA Core
    success = registry.register_module(DOMAIN, capabilities)
    
    if success:
        _LOGGER.info("Successfully registered with SOPHIA Core")
        _LOGGER.info("Tracking %d people: %s",
                    len(entry.data.get(CONF_PEOPLE, [])),
                    ", ".join(p[CONF_PERSON_NAME] for p in entry.data.get(CONF_PEOPLE, [])))
    else:
        _LOGGER.error("Failed to register with SOPHIA Core!")
        return False
    
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await _register_services(hass, entry, coordinator)

    # Schedule anomaly detection every 30 minutes (runs in background, needs trip history)
    if coordinator.ai_features_enabled:
        async def _run_anomaly_checks(now):
            if not coordinator.data or not coordinator.ai:
                return
            people = coordinator.data.get("people", {})
            for person_id, person_data in people.items():
                if not person_data.get("available"):
                    # Person unavailable - clear any active anomaly so it re-fires if they return odd
                    coordinator._active_anomalies.pop(person_id, None)
                    continue

                # Pass work_location from person config so SOPHIA doesn't flag the workplace
                person_cfg = coordinator.people.get(person_id, {})
                work_location = person_cfg.get("work_location", "")

                anomalies = await coordinator.ai.check_for_anomalies(
                    person_id, person_data, coordinator.trip_history,
                    work_location=work_location,
                )

                if not anomalies:
                    # Situation resolved - clear active anomaly so next one fires fresh
                    coordinator._active_anomalies.pop(person_id, None)
                    continue

                for anomaly in anomalies:
                    fingerprint = anomaly.get("fingerprint", "")
                    last_fingerprint = coordinator._active_anomalies.get(person_id)

                    # Skip if this is the same anomaly we already notified about
                    if fingerprint and fingerprint == last_fingerprint:
                        _LOGGER.debug(
                            "Anomaly suppressed (duplicate) for %s: %s",
                            anomaly.get("person", person_id), fingerprint
                        )
                        continue

                    sev = anomaly.get("severity", "low")
                    desc = anomaly.get("description", "Unusual activity detected")
                    person_name = anomaly.get("person", person_id)
                    _LOGGER.warning("Anomaly detected for %s: %s", person_name, desc)

                    # Store fingerprint to suppress repeats
                    coordinator._active_anomalies[person_id] = fingerprint

                    # Anomalies are silent - informational banner only, no alarm sound
                    await coordinator._notify_all_family(
                        title=f"Anomaly: {person_name}",
                        message=desc,
                        notification_id=f"anomaly_{person_id}",
                        priority="silent",
                    )

        async_track_time_interval(hass, _run_anomaly_checks, timedelta(minutes=30))
    
    # Listen for zone suggestion events (person stationary in unknown location)
    if coordinator.ai_features_enabled:
        async def handle_zone_suggested(event):
            """Handle EVENT_ZONE_SUGGESTED - ask AI to name an unknown dwell location."""
            data = event.data
            lat = data.get("latitude")
            lon = data.get("longitude")
            dwell_minutes = data.get("dwell_time_minutes", 30)
            person_name = data.get("person_name", "Unknown")

            if not lat or not lon or not coordinator.ai:
                return

            suggestion = await coordinator.ai.suggest_zone_name(
                latitude=lat,
                longitude=lon,
                dwell_time_minutes=dwell_minutes,
                person_name=person_name,
            )

            if suggestion:
                zone_name = suggestion.get("name", "New Zone")
                icon = suggestion.get("icon", "mdi:map-marker")
                reason = suggestion.get("reason", "")

                # Store zone knowledge in RAG
                hass.async_create_task(
                    coordinator.ai.store_zone_knowledge(
                        zone_id=f"suggested_{lat:.4f}_{lon:.4f}",
                        zone_name=zone_name,
                        coords=(lat, lon),
                        context=reason,
                    )
                )

                await hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": "New Zone Suggested",
                        "message": (
                            f"SOPHIA suggests creating a zone for {person_name}'s location.\n\n"
                            f"Suggested name: {zone_name}\n"
                            f"Icon: {icon}\n"
                            f"Reason: {reason}\n"
                            f"Coordinates: {lat:.5f}, {lon:.5f}\n\n"
                            f"You can create this zone in Settings > Areas & Zones."
                        ),
                        "notification_id": f"sophia_zone_suggest_{lat:.4f}_{lon:.4f}",
                    }
                )
                _LOGGER.info(
                    "Zone suggestion for %s at %.5f, %.5f: %s (%s)",
                    person_name, lat, lon, zone_name, icon
                )

        hass.bus.async_listen(EVENT_ZONE_SUGGESTED, handle_zone_suggested)

    _LOGGER.info("SOPHIA Presence v%s setup complete", VERSION)
    
    return True


def _build_sensor_list(entry: ConfigEntry) -> List[str]:
    """Build list of sensor entity IDs for this config"""
    sensors = [
        "sensor.sophia_presence_status",
        "sensor.sophia_presence_people_home",
        "sensor.sophia_presence_people_away",
        "sensor.sophia_presence_total_people",
        "sensor.sophia_presence_event_log",
    ]
    
    # Add per-person sensors
    for person in entry.data.get(CONF_PEOPLE, []):
        person_id = person[CONF_PERSON_ID]
        sensors.extend([
            f"sensor.sophia_presence_{person_id}_location",
            f"sensor.sophia_presence_{person_id}_activity",
            f"sensor.sophia_presence_{person_id}_battery",
            f"sensor.sophia_presence_{person_id}_speed",
            f"sensor.sophia_presence_{person_id}_distance_from_home",
            f"sensor.sophia_presence_{person_id}_high_accuracy_gps",
        ])
    
    return sensors


def _build_device_tracker_list(entry: ConfigEntry) -> List[str]:
    """Build list of device tracker entity IDs"""
    import re
    trackers = []
    
    for person in entry.data.get(CONF_PEOPLE, []):
        person_id = person[CONF_PERSON_ID]
        # Use stored person_id (already sanitized during setup)
        trackers.append(f"device_tracker.{person_id}")
    
    return trackers


def _build_switch_list(entry: ConfigEntry) -> List[str]:
    """Build list of switch entity IDs"""
    import re
    switches = [
        "switch.sophia_presence_system",
        "switch.sophia_presence_crash_detection",
        "switch.sophia_presence_speed_alerts",
        "switch.sophia_presence_low_battery_alerts",
        "switch.sophia_presence_quiet_hours",
    ]
    
    # Add per-person switches
    for person in entry.data.get(CONF_PEOPLE, []):
        person_id = person[CONF_PERSON_ID]
        # Use stored person_id (already sanitized during setup)
        switches.extend([
            f"switch.sophia_presence_{person_id}_tracking",
            f"switch.sophia_presence_{person_id}_privacy_mode",
            f"switch.sophia_presence_{person_id}_notifications",
        ])
    
    return switches


def _build_dashboard_config(entry: ConfigEntry) -> Dict[str, Any]:
    """Build complete dashboard configuration in Python"""
    
    people = entry.data.get(CONF_PEOPLE, [])
    people_count = len(people)
    
    # Build person entity lists for map
    person_entities = [f"device_tracker.{p[CONF_PERSON_ID]}" for p in people]
    
    cards = [
        # Header card
        {
            "type": "markdown",
            "content": (
                "# SOPHIA Presence\n"
                "## Family Location Tracking\n\n"
                "**Status:** {% if is_state('switch.sophia_presence_system', 'on') %}Active{% else %}Paused{% endif %}\n"
                "**People Home:** {{ states('sensor.sophia_presence_people_home') }}\n"
                "**People Away:** {{ states('sensor.sophia_presence_people_away') }}\n"
                "**Last Updated:** {{ now().strftime('%I:%M %p') }}\n"
            ),
            "style": "ha-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }"
        },
        
        # System controls
        {
            "type": "entities",
            "title": "System Controls",
            "show_header_toggle": False,
            "entities": [
                {"entity": "switch.sophia_presence_system", "name": "Master Tracking"},
                {"entity": "switch.sophia_presence_crash_detection", "name": "Crash Detection"},
                {"entity": "switch.sophia_presence_speed_alerts", "name": "Speed Alerts"},
                {"entity": "switch.sophia_presence_low_battery_alerts", "name": "Low Battery Alerts"},
                {"entity": "switch.sophia_presence_quiet_hours", "name": "Quiet Hours"},
            ]
        },
        
        # Family map
        {
            "type": "map",
            "title": "Family Locations",
            "entities": person_entities,
            "hours_to_show": 1,
            "default_zoom": 13,
            "aspect_ratio": "16x9"
        },
    ]
    
    # Add per-person cards
    for person in people:
        person_id = person[CONF_PERSON_ID]
        person_name = person[CONF_PERSON_NAME]
        
        # Use stored person_id (already sanitized during setup)
        entity_id_suffix = person_id
        
        # Determine gradient based on position in list
        gradients = [
            "linear-gradient(135deg, #3a7bd5 0%, #00d2ff 100%)",  # Blue
            "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",  # Pink
            "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",  # Cyan
            "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",  # Orange
            "linear-gradient(135deg, #30cfd0 0%, #330867 100%)",  # Purple
        ]
        gradient = gradients[people.index(person) % len(gradients)]
        
        person_card = {
            "type": "vertical-stack",
            "cards": [
                # Person header
                {
                    "type": "markdown",
                    "content": (
                        f"# {person_name}\n"
                        "{% set person_entity = 'device_tracker." + entity_id_suffix + "' %}\n"
                        "{% set activity = states('sensor.sophia_presence_" + entity_id_suffix + "_activity') %}\n"
                        "{% if is_state(person_entity, 'home') %}\n"
                        "  **At Home**\n"
                        "{% elif activity == 'in_vehicle' %}\n"
                        "  **Driving** - {{ states('sensor.sophia_presence_" + entity_id_suffix + "_speed') }} mph\n"
                        "{% else %}\n"
                        "  **{{ states('sensor.sophia_presence_" + entity_id_suffix + "_location') }}**\n"
                        "{% endif %}\n"
                    ),
                    "style": f"ha-card {{ background: {gradient}; color: white; }}"
                },
                
                # Person details grid
                {
                    "type": "grid",
                    "columns": 2,
                    "cards": [
                        # Left side - entity details
                        {
                            "type": "entities",
                            "entities": [
                                {"entity": f"device_tracker.{entity_id_suffix}", "name": "Location"},
                                {"entity": f"sensor.sophia_presence_{entity_id_suffix}_distance_from_home", "name": "Distance from Home"},
                                {"entity": f"sensor.sophia_presence_{entity_id_suffix}_battery", "name": "Battery", "icon": "mdi:battery"},
                                {"entity": f"sensor.sophia_presence_{entity_id_suffix}_activity", "name": "Activity", "icon": "mdi:motion-sensor"},
                                {"entity": f"sensor.sophia_presence_{entity_id_suffix}_speed", "name": "Speed", "icon": "mdi:speedometer"},
                                {"entity": f"sensor.sophia_presence_{entity_id_suffix}_high_accuracy_gps", "name": "High Accuracy GPS", "icon": "mdi:crosshairs-gps"},
                            ]
                        },
                        
                        # Right side - individual map
                        {
                            "type": "map",
                            "entities": [f"device_tracker.{entity_id_suffix}"],
                            "hours_to_show": 0,
                            "aspect_ratio": "1x1",
                            "default_zoom": 15
                        }
                    ]
                },
                
                # Person controls
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "button",
                            "name": "SOS",
                            "icon": "mdi:alarm-light",
                            "tap_action": {
                                "action": "call-service",
                                "service": "sophia_presence.trigger_sos",
                                "data": {"person_id": person_id}
                            }
                        },
                        {
                            "type": "button",
                            "name": "Check In",
                            "icon": "mdi:account-check",
                            "tap_action": {
                                "action": "call-service",
                                "service": "sophia_presence.request_checkin",
                                "data": {"person_id": person_id}
                            }
                        },
                        {
                            "type": "entity",
                            "entity": f"switch.sophia_presence_{entity_id_suffix}_privacy_mode",
                            "name": "Privacy",
                            "icon": "mdi:shield-account"
                        },
                        {
                            "type": "entity",
                            "entity": f"switch.sophia_presence_{entity_id_suffix}_tracking",
                            "name": "Tracking",
                            "icon": "mdi:map-marker"
                        }
                    ]
                },

                # Add Zone from current location
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "entities",
                            "entities": [
                                {
                                    "entity": f"text.sophia_presence_{entity_id_suffix}_new_zone_name",
                                    "name": "New Zone Name",
                                    "icon": "mdi:map-marker-plus"
                                }
                            ]
                        },
                        {
                            "type": "button",
                            "name": "Add Zone",
                            "icon": "mdi:map-marker-check",
                            "tap_action": {
                                "action": "call-service",
                                "service": "sophia_presence.add_zone_from_location",
                                "data": {"person_id": person_id}
                            }
                        }
                    ]
                }
            ]
        }
        
        cards.append(person_card)
    
    # Add recent events card
    cards.append({
        "type": "markdown",
        "title": "Recent Location Events",
        "content": "{{ state_attr('sensor.sophia_presence_event_log', 'events_formatted') }}"
    })
    
    # Add system statistics
    cards.append({
        "type": "markdown",
        "title": "System Statistics",
        "content": (
            "**Total People:** {{ states('sensor.sophia_presence_total_people') }}\n"
            "**Update Interval:** {{ state_attr('sensor.sophia_presence_status', 'update_interval') }}s\n"
            "**Tracking Method:** {{ state_attr('sensor.sophia_presence_status', 'tracking_method') | title }}\n"
            "**AI Features:** {{ 'Enabled' if state_attr('sensor.sophia_presence_status', 'ai_features_enabled') else 'Disabled' }}\n"
            "**Active Since:** {{ state_attr('sensor.sophia_presence_status', 'startup_time') }}\n"
        )
    })
    
    return {
        "title": "Presence",
        "path": "presence",
        "icon": "mdi:map-marker-account",
        "badges": [],
        "cards": cards
    }


async def _register_services(hass: HomeAssistant, entry: ConfigEntry, coordinator):
    """Register all SOPHIA Presence services"""
    
    async def handle_update_location(call):
        """Handle manual location update"""
        person_id = call.data.get("person_id")
        latitude = call.data.get("latitude")
        longitude = call.data.get("longitude")
        
        _LOGGER.info("Manual location update: %s to %s, %s", person_id, latitude, longitude)
        
        # Update coordinator data
        await coordinator.async_manual_location_update(person_id, latitude, longitude)
    
    async def handle_add_person(call):
        """Handle adding a new person"""
        # This would require reconfiguration - show notification
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Add Person",
                "message": "To add a new person, please reconfigure the integration from Settings ? Devices & Services ? SOPHIA Presence.",
                "notification_id": "sophia_presence_add_person"
            }
        )
    
    async def handle_request_checkin(call):
        """Handle check-in request"""
        person_id = call.data.get("person_id")
        message = call.data.get("message", "SOPHIA Presence is requesting you check in")
        
        _LOGGER.info("Check-in requested for: %s", person_id)
        
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": f"Check-In Request: {person_id.title()}",
                "message": message,
                "notification_id": f"sophia_presence_checkin_{person_id}"
            }
        )
    
    async def handle_trigger_sos(call):
        """Handle SOS trigger - Alert ALL family members immediately"""
        person_id = call.data.get("person_id")
        
        person_data = coordinator.data.get("people", {}).get(person_id)
        
        if not person_data:
            _LOGGER.error("Person not found: %s", person_id)
            return
        
        location = person_data.get("location", {})
        person_name = person_data.get("name")
        zone_name = location.get("zone", "Unknown").replace("_", " ").title()
        
        # Fire SOS event
        hass.bus.async_fire(EVENT_SOS_TRIGGERED, {
            "person_id": person_id,
            "person_name": person_name,
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "zone": location.get("zone"),
            "timestamp": datetime.now().isoformat()
        })

        # Try AI-crafted SOS message
        sos_title = None
        sos_message = None
        if coordinator.ai and coordinator.ai_features_enabled:
            all_people = coordinator.data.get("people", {}) if coordinator.data else {}
            sos_title, sos_message = await coordinator.ai.craft_sos_message(
                person_data=person_data,
                all_people_data=all_people,
            )

        # Static fallback
        if not sos_message:
            sos_title = f"SOS ALERT: {person_name}"
            sos_message = (
                f"{person_name} has triggered an SOS alert!\n\n"
                f"Location: {zone_name}\n"
                f"Coordinates: {location.get('latitude')}, {location.get('longitude')}\n"
                f"Time: {datetime.now().strftime('%I:%M %p')}"
            )

        await coordinator._notify_all_family(
            title=sos_title,
            message=sos_message,
            notification_id=f"sophia_presence_sos_{person_id}",
            priority="critical"
        )

        _LOGGER.critical("SOS triggered by %s at %s", person_name, zone_name)

    async def handle_get_daily_summary(call):
        """Generate and deliver an AI-powered daily presence briefing."""
        if not coordinator.ai or not coordinator.ai_features_enabled:
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "Daily Presence Summary",
                    "message": "AI features must be enabled to generate a daily summary.",
                    "notification_id": "sophia_presence_daily_summary",
                }
            )
            return

        people_data = coordinator.data.get("people", {}) if coordinator.data else {}
        statistics = coordinator.data.get("statistics", {}) if coordinator.data else {}
        summary = await coordinator.ai.generate_daily_summary(
            people_data=people_data,
            trip_history=coordinator.trip_history,
            statistics=statistics,
        )

        if not summary:
            summary = "Unable to generate summary at this time."

        await hass.services.async_call(
            "persistent_notification", "create",
            {
                "title": f"Daily Presence Summary - {datetime.now().strftime('%A, %B %d')}",
                "message": summary,
                "notification_id": "sophia_presence_daily_summary",
            }
        )
        _LOGGER.info("Daily presence summary delivered")

    async def handle_add_zone_from_location(call) -> None:
        """Create a HA zone at a person's current GPS location.

        Reads zone_name from the text entity if not provided directly.
        Falls back to person_id = first tracked person if not specified.
        """
        person_id = call.data.get("person_id", "")
        zone_name = call.data.get("zone_name", "").strip()

        # If no person_id, use the first tracked person
        if not person_id:
            tracked = list(coordinator.people.keys())
            if not tracked:
                _LOGGER.warning("add_zone_from_location: no tracked people")
                return
            person_id = tracked[0]

        # If no zone_name in call data, read from the text input entity
        if not zone_name:
            text_entity_id = f"text.sophia_presence_{person_id}_new_zone_name"
            state = hass.states.get(text_entity_id)
            if state and state.state not in (None, "unknown", "unavailable"):
                zone_name = state.state.strip()

        if not zone_name:
            _LOGGER.warning("add_zone_from_location: no zone name for %s", person_id)
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "SOPHIA: Zone Name Required",
                    "message": (
                        f"Enter a name in the **New Zone Name** field for {person_id.title()}, "
                        "then press **Add Zone** again."
                    ),
                    "notification_id": f"sophia_presence_zone_name_required_{person_id}",
                }
            )
            return

        # Get person's current coordinates
        people_data = (coordinator.data or {}).get("people", {})
        person_data = people_data.get(person_id, {})
        location = person_data.get("location", {})
        lat = location.get("latitude")
        lon = location.get("longitude")

        if not lat or not lon:
            _LOGGER.warning("add_zone_from_location: no GPS coords for %s", person_id)
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "SOPHIA: No Location",
                    "message": f"No GPS coordinates available for {person_id.title()}. Enable tracking and try again.",
                    "notification_id": f"sophia_presence_zone_no_location_{person_id}",
                }
            )
            return

        # Slugify zone name for entity_id
        zone_slug = zone_name.lower().replace(" ", "_").replace("-", "_")
        zone_entity_id = f"zone.{zone_slug}"

        if hass.states.get(zone_entity_id):
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "SOPHIA: Zone Already Exists",
                    "message": f"A zone named **{zone_name}** already exists. Choose a different name.",
                    "notification_id": f"sophia_presence_zone_exists_{person_id}",
                }
            )
            return

        radius = DEFAULT_ZONE_RADIUS
        try:
            # HA has no zone.create service - zones are managed via storage collection
            # hass.data["zone"] holds the ZoneStorageCollection
            from homeassistant.components.zone import DOMAIN as ZONE_DOMAIN

            zone_collection = hass.data.get(ZONE_DOMAIN)
            if zone_collection is None:
                raise RuntimeError("Zone storage collection not available")

            await zone_collection.async_create_item({
                "name": zone_name,
                "latitude": lat,
                "longitude": lon,
                "radius": radius,
                "icon": "mdi:map-marker",
                "passive": False,
            })
            _LOGGER.info(
                "Zone '%s' created at %.5f, %.5f (radius %dm) by %s",
                zone_name, lat, lon, radius, person_id
            )

            _LOGGER.info("Zone '%s' created successfully", zone_name)

        except Exception as e:
            _LOGGER.error("Failed to create zone '%s': %s", zone_name, e)
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "SOPHIA: Zone Creation Failed",
                    "message": f"Could not create zone **{zone_name}**: {e}",
                    "notification_id": f"sophia_presence_zone_failed_{person_id}",
                }
            )
            return

        # Clear the text input (outside try/except - non-critical)
        try:
            await hass.services.async_call(
                "text", "set_value",
                {"entity_id": f"text.sophia_presence_{person_id}_new_zone_name", "value": " "},
                blocking=False,
            )
        except Exception:
            pass

        # Store in RAG if AI enabled (outside try/except - non-critical)
        if coordinator.ai and coordinator.ai_features_enabled:
            try:
                zone_slug = zone_name.lower().replace(" ", "_").replace("-", "_")
                hass.async_create_task(
                    coordinator.ai.store_zone_knowledge(
                        zone_slug,
                        zone_name,
                        (lat, lon),
                        f"Manually added by {person_id}",
                    )
                )
            except Exception as e:
                _LOGGER.warning("Failed to store zone in RAG: %s", e)

        await hass.services.async_call(
            "persistent_notification", "create",
            {
                "title": "SOPHIA: Zone Added",
                "message": (
                    f"Zone **{zone_name}** created at your current location "
                    f"({lat:.4f}, {lon:.4f}) with radius {radius}m."
                ),
                "notification_id": f"sophia_presence_zone_added_{person_id}",
            }
        )

    # Register services
    hass.services.async_register(DOMAIN, "update_location", handle_update_location)
    hass.services.async_register(DOMAIN, "add_person", handle_add_person)
    hass.services.async_register(DOMAIN, "request_checkin", handle_request_checkin)
    hass.services.async_register(DOMAIN, "trigger_sos", handle_trigger_sos)
    hass.services.async_register(DOMAIN, "get_daily_summary", handle_get_daily_summary)
    hass.services.async_register(DOMAIN, "add_zone_from_location", handle_add_zone_from_location)
    
    _LOGGER.info("Registered %d services", len(SERVICES))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload SOPHIA Presence"""
    
    _LOGGER.info("Unloading SOPHIA Presence...")
    
    # Unregister from SOPHIA Core
    if "sophia_core" in hass.data:
        registry = hass.data["sophia_core"]["registry"]
        registry.unregister_module(DOMAIN)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


class SophiaPresenceCoordinator(DataUpdateCoordinator):
    """Coordinator for SOPHIA Presence data updates"""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, llm_client, event_logger):
        """Initialize the coordinator"""
        super().__init__(
            hass,
            _LOGGER,
            name="SOPHIA Presence",
            update_interval=timedelta(seconds=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        )
        self.entry = entry
        self.llm_client = llm_client
        self.event_logger = event_logger
        
        # Parse configuration
        self.people = {p[CONF_PERSON_ID]: p for p in entry.data.get(CONF_PEOPLE, [])}
        self.tracking_method = entry.data.get(CONF_TRACKING_METHOD)
        self.ai_features_enabled = entry.options.get(CONF_AI_FEATURES, entry.data.get(CONF_AI_FEATURES, False))
        self.ai_features_list = entry.data.get(CONF_AI_FEATURES_LIST, [])
        self.fire_events = entry.data.get(CONF_FIRE_EVENTS, True)
        
        # Safety feature settings
        self.crash_detection_enabled = entry.data.get(CONF_CRASH_DETECTION, True)
        self.speed_alerts_enabled = entry.data.get(CONF_SPEED_ALERTS, True)
        self.low_battery_alerts_enabled = entry.data.get(CONF_LOW_BATTERY_ALERTS, True)
        self.speed_warning_threshold = entry.data.get(CONF_SPEED_WARNING_THRESHOLD, 75)
        self.speed_excessive_threshold = entry.data.get(CONF_SPEED_EXCESSIVE_THRESHOLD, 90)
        self.battery_alert_threshold = entry.data.get(CONF_BATTERY_ALERT_THRESHOLD, 20)
        
        # Zone settings
        self.home_zone = entry.data.get(CONF_HOME_ZONE, "zone.home")
        self.use_ha_zones = entry.data.get(CONF_USE_HA_ZONES, True)
        self.zone_notifications_enabled = entry.data.get(CONF_ZONE_NOTIFICATIONS, True)
        self.zone_auto_suggest_enabled = entry.data.get(CONF_ZONE_AUTO_SUGGEST, True)
        
        # Tracking state
        self.last_zones = {}  # person_id -> zone_name
        self.last_speeds = {}  # person_id -> speed
        self.last_positions = {}  # person_id -> (lat, lon, timestamp)
        self.zone_dwell_timers = {}  # person_id -> (zone_name, entry_time)
        self.last_battery_warnings = {}  # person_id -> timestamp
        self.last_high_accuracy_state = {}  # person_id -> True/False (ON/OFF)
        
        # Trip tracking
        self.active_trips = {}  # person_id -> trip_data
        self.trip_history = []  # Last 30 days of completed trips
        self.trip_retention_days = 30
        self.trip_speeds = {}  # person_id -> list of speeds during trip

        # Anomaly deduplication: person_id -> fingerprint of last notified anomaly
        self._active_anomalies: dict = {}

        # AI layer (set externally after init if ai_features_enabled)
        self.ai = None

        # Track zone transitions for AI high-accuracy GPS decisions
        self._zone_just_changed: Dict[str, bool] = {}

        self.startup_time = datetime.now()
    
    async def _async_update_data(self):
        """Fetch data from all tracked devices"""
        
        _LOGGER.debug("Running SOPHIA Presence update...")
        
        data = {
            "people": {},
            "zones": {},
            "statistics": {},
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Update each person
            for person_id, person_config in self.people.items():
                person_data = await self._update_person(person_id, person_config)
                data["people"][person_id] = person_data
                
                # Check for zone changes
                if person_data.get("available"):
                    await self._check_zone_changes(person_id, person_data)
                    await self._check_speed_alerts(person_id, person_data)
                    await self._check_crash_detection(person_id, person_data)
                    await self._check_battery_alerts(person_id, person_data)
                    
                    # Update active trip with current speed and distance
                    if person_id in self.active_trips:
                        speed = person_data.get("speed", 0)
                        latitude = person_data["location"]["latitude"]
                        longitude = person_data["location"]["longitude"]
                        self._update_trip(person_id, speed, (latitude, longitude))
            
            # Update zone occupancy
            data["zones"] = await self._update_zone_occupancy(data["people"])
            
            # Calculate statistics
            data["statistics"] = self._calculate_statistics(data["people"])
            
            # Check for everyone away / first home events
            await self._check_presence_milestones(data)
            
            return data
            
        except Exception as err:
            _LOGGER.error("Error updating SOPHIA Presence data: %s", err)
            raise UpdateFailed(f"Error updating data: {err}")
    
    async def _update_person(self, person_id: str, config: Dict) -> Dict[str, Any]:
        """Update data for a single person"""
        
        # Get device_tracker state
        tracker_entity = config.get(CONF_DEVICE_TRACKER)
        
        if not tracker_entity:
            return {"available": False, "reason": "No device tracker configured"}
        
        tracker_state = self.hass.states.get(tracker_entity)
        
        if not tracker_state:
            return {"available": False, "reason": "Device tracker not found"}
        
        # Get activity sensor (with auto-detection for companion app)
        activity = "unknown"
        activity_confidence = "unknown"
        
        if config.get(CONF_ACTIVITY_SENSOR):
            # Use configured activity sensor
            activity_state = self.hass.states.get(config[CONF_ACTIVITY_SENSOR])
            if activity_state:
                activity = activity_state.state
                activity_confidence = activity_state.attributes.get("confidence", "unknown")
        else:
            # Auto-detect companion app activity sensor
            # Extract device name from device_tracker entity
            # Example: device_tracker.pixel_9_pro -> pixel_9_pro
            device_name = tracker_entity.replace("device_tracker.", "")
            activity_sensor = f"sensor.{device_name}_detected_activity"
            
            activity_state = self.hass.states.get(activity_sensor)
            if activity_state:
                activity = activity_state.state
                activity_confidence = activity_state.attributes.get("confidence", "unknown")
                _LOGGER.debug("Auto-detected activity sensor for %s: %s (state: %s, confidence: %s)", 
                            person_id, activity_sensor, activity, activity_confidence)
            else:
                _LOGGER.debug("No activity sensor found for %s (tried: %s)", person_id, activity_sensor)
        
        # Normalize activity states between iOS and Android
        # Android: in_vehicle, on_bicycle, on_foot, running, still, tilting, walking, unknown
        # iOS: Stationary, Walking, Running, Automotive, Cycling, Unknown
        activity_normalized = activity.lower()
        
        # Map iOS states to Android equivalents for consistency
        if activity_normalized in ["automotive", "driving"]:
            activity_normalized = ACTIVITY_IN_VEHICLE
        elif activity_normalized in ["stationary"]:
            activity_normalized = "still"
        elif activity_normalized in ["cycling"]:
            activity_normalized = "on_bicycle"
        
        # Get battery sensor if configured
        battery = None
        if config.get(CONF_BATTERY_SENSOR):
            battery_state = self.hass.states.get(config[CONF_BATTERY_SENSOR])
            try:
                battery = float(battery_state.state) if battery_state else None
            except (ValueError, TypeError):
                battery = None
        
        # Get location data
        latitude = tracker_state.attributes.get("latitude")
        longitude = tracker_state.attributes.get("longitude")
        
        if not latitude or not longitude:
            return {"available": False, "reason": "No GPS coordinates"}
        
        # Calculate speed from GPS
        speed = self._calculate_speed(tracker_state)
        
        # Determine current zone
        current_zone = await self._determine_zone(latitude, longitude)
        
        # Calculate distance from home
        distance_from_home = self._calculate_distance_from_home(latitude, longitude)
        
        # Check privacy mode
        privacy_mode = config.get(CONF_PRIVACY_MODE, False)
        
        # Build person data
        person_data = {
            "person_id": person_id,
            "name": config[CONF_PERSON_NAME],
            "available": True,
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "zone": current_zone,
                "address": tracker_state.attributes.get("address", "")
            },
            "activity": activity_normalized,  # Normalized activity (Android format)
            "activity_raw": activity,  # Original activity state
            "activity_confidence": activity_confidence,  # Confidence rating
            "speed": speed,
            "battery": battery,
            "distance_from_home": distance_from_home,
            "privacy_mode": privacy_mode,
            "tracking_paused": False,  # TODO: Implement from switch state
            "last_update": tracker_state.last_changed.isoformat() if tracker_state.last_changed else None,
            "device_tracker": tracker_entity  # Store for high accuracy requests
        }
        
        # ? FIX: HIGH ACCURACY MODE - MOVED BEFORE RETURN!
        # Request or disable high accuracy mode based on movement
        if await self._should_request_high_accuracy(person_id, person_data, latitude, longitude, current_zone):
            await self._request_high_accuracy(tracker_entity, person_id)
        else:
            await self._disable_high_accuracy(tracker_entity, person_id)
        
        return person_data
    
    def _calculate_speed(self, tracker_state) -> float:
        """Calculate speed from device_tracker GPS data"""
        try:
            # Get speed from device_tracker attributes (m/s)
            speed_ms = tracker_state.attributes.get("speed")
            
            if speed_ms is not None and speed_ms > 0:
                # Convert m/s to mph
                speed_mph = speed_ms * 2.237
                return round(speed_mph, 1)
            
            return 0.0
        except (ValueError, TypeError, AttributeError):
            return 0.0
    
    async def _determine_zone(self, latitude: float, longitude: float) -> str:
        """Determine which zone the coordinates are in"""
        
        if not self.use_ha_zones:
            return "not_home"
        
        # Check all Home Assistant zones
        for zone_entity_id in self.hass.states.async_entity_ids("zone"):
            zone_state = self.hass.states.get(zone_entity_id)
            
            if not zone_state:
                continue
            
            zone_lat = zone_state.attributes.get("latitude")
            zone_lon = zone_state.attributes.get("longitude")
            zone_radius = zone_state.attributes.get("radius", 100)  # In meters
            
            if not zone_lat or not zone_lon:
                continue
            
            # Calculate distance to zone center (returns km)
            distance_km = self._calculate_distance(latitude, longitude, zone_lat, zone_lon)
            
            # Convert distance to meters for comparison
            distance_meters = distance_km * 1000
            
            # Apply hysteresis to prevent flip-flopping
            effective_radius = zone_radius * ZONE_HYSTERESIS_FACTOR
            
            if distance_meters <= effective_radius:
                # Extract zone name from entity_id (zone.home -> home)
                zone_name = zone_entity_id.replace("zone.", "")
                return zone_name
        
        return "not_home"
    
    def _calculate_distance_from_home(self, latitude: float, longitude: float) -> float:
        """Calculate distance from home zone in miles"""
        
        # Get configured home zone (defaults to zone.home)
        home_zone = self.hass.states.get(self.home_zone)
        
        if not home_zone:
            return 0.0
        
        home_lat = home_zone.attributes.get("latitude")
        home_lon = home_zone.attributes.get("longitude")
        
        if not home_lat or not home_lon:
            return 0.0
        
        # Calculate distance in km
        distance_km = self._calculate_distance(latitude, longitude, home_lat, home_lon)
        
        # Convert km to miles (1 km = 0.621371 miles)
        distance_miles = distance_km * 0.621371
        
        return round(distance_miles, 2)
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in kilometers"""
        
        # Use Home Assistant's distance utility
        # NOTE: distance_calc ALWAYS returns METERS in modern HA versions
        distance_meters = distance_calc(lat1, lon1, lat2, lon2)
        
        if distance_meters is None:
            return 0.0
        
        # Convert meters to kilometers
        return distance_meters / 1000
    
    async def _should_request_high_accuracy(
        self, 
        person_id: str, 
        person_data: Dict,
        latitude: float,
        longitude: float,
        current_zone: str
    ) -> bool:
        """Determine if high accuracy GPS should be requested.

        Delegates to PresenceAI on zone transitions for nuanced decisions.
        Falls back to simple not_home logic when AI is unavailable.
        """
        last_state = self.last_high_accuracy_state.get(person_id)
        last_zone = self.last_zones.get(person_id)
        zone_just_changed = current_zone != last_zone and last_zone is not None

        # Store transition flag for this cycle
        self._zone_just_changed[person_id] = zone_just_changed

        # Delegate to AI when available
        if self.ai and self.ai_features_enabled:
            should_enable = await self.ai.should_enable_high_accuracy(
                person_id=person_id,
                person_data=person_data,
                current_zone=current_zone,
                last_zone=last_zone,
                zone_just_changed=zone_just_changed,
            )
        else:
            should_enable = (current_zone == "not_home")

        if last_state != should_enable:
            person_name = person_data.get("name")
            if should_enable:
                _LOGGER.info("Person %s left known zones - enabling high accuracy", person_name)
            else:
                _LOGGER.info(
                    "Person %s in zone '%s' - disabling high accuracy", person_name, current_zone
                )

        self.last_high_accuracy_state[person_id] = should_enable
        return should_enable
    
    async def _request_high_accuracy(self, device_tracker_entity: str, person_id: str):
        """Enable high accuracy GPS mode when not in known zones"""
        
        # Extract device name from device_tracker entity
        # Example: device_tracker.pixel_9_pro -> pixel_9_pro
        device_name = device_tracker_entity.replace("device_tracker.", "")
        
        try:
            # Enable high accuracy mode via notification command
            await self.hass.services.async_call(
                "notify",
                f"mobile_app_{device_name}",
                {
                    "message": "command_high_accuracy_mode",
                    "data": {
                        "command": "turn_on"
                    }
                },
                blocking=False
            )
            _LOGGER.debug("?? High accuracy ON for %s", person_id)
        except Exception as e:
            _LOGGER.debug("Could not request high accuracy for %s: %s", person_id, e)
    
    async def _disable_high_accuracy(self, device_tracker_entity: str, person_id: str):
        """Disable high accuracy GPS mode to save battery in known zones"""
        
        # Extract device name from device_tracker entity
        device_name = device_tracker_entity.replace("device_tracker.", "")
        
        try:
            # Disable high accuracy mode via notification command
            await self.hass.services.async_call(
                "notify",
                f"mobile_app_{device_name}",
                {
                    "message": "command_high_accuracy_mode",
                    "data": {
                        "command": "turn_off"
                    }
                },
                blocking=False
            )
            _LOGGER.debug("?? High accuracy OFF for %s", person_id)
        except Exception as e:
            _LOGGER.debug("Could not disable high accuracy for %s: %s", person_id, e)
    
    async def _check_zone_changes(self, person_id: str, person_data: Dict):
        """Check if person changed zones and fire events"""
        
        current_zone = person_data["location"]["zone"]
        last_zone = self.last_zones.get(person_id)
        
        # Log zone state for debugging
        if current_zone != last_zone:
            person_name = person_data.get("name")
            _LOGGER.info("??? Zone change detected: %s from '%s' to '%s'", 
                        person_name, last_zone or "unknown", current_zone)
        
        # Check for zone dwell time to prevent false positives
        # EXCEPTION: Always immediately process transitions involving home or not_home
        immediate_zones = ["home", "not_home"]
        is_immediate_transition = (current_zone in immediate_zones or last_zone in immediate_zones)
        
        if current_zone != last_zone:
            # Check if we're in dwell timer
            if person_id in self.zone_dwell_timers:
                timer_zone, entry_time = self.zone_dwell_timers[person_id]
                
                if timer_zone == current_zone:
                    # Still in same new zone, check dwell time
                    elapsed = (datetime.now() - entry_time).total_seconds()
                    
                    # Process immediately if involving home/not_home, otherwise wait for dwell time
                    if is_immediate_transition or elapsed >= MIN_ZONE_DWELL_TIME:
                        # Confirmed! Process zone change
                        await self._process_zone_change(person_id, person_data, last_zone, current_zone)
                        del self.zone_dwell_timers[person_id]
                else:
                    # Changed zones again before confirming, reset timer
                    self.zone_dwell_timers[person_id] = (current_zone, datetime.now())
            else:
                # Start dwell timer (or process immediately if home/not_home)
                if is_immediate_transition:
                    # Process immediately for home/not_home transitions
                    await self._process_zone_change(person_id, person_data, last_zone, current_zone)
                else:
                    # Start dwell timer for other zones
                    self.zone_dwell_timers[person_id] = (current_zone, datetime.now())
        
        # Update last zone
        self.last_zones[person_id] = current_zone
    
    async def _process_zone_change(self, person_id: str, person_data: Dict, from_zone: str, to_zone: str):
        """Process confirmed zone change with trip tracking"""
        
        person_name = person_data.get("name")
        latitude = person_data["location"]["latitude"]
        longitude = person_data["location"]["longitude"]
        current_coords = (latitude, longitude)
        current_time = datetime.now().strftime("%I:%M %p")
        
        _LOGGER.info("?? PROCESSING zone change: %s from '%s' to '%s'", 
                    person_name, from_zone or "unknown", to_zone)
        
        # Log event
        self.event_logger.log_event("zone_change", {
            "person_id": person_id,
            "person_name": person_name,
            "from_zone": from_zone,
            "to_zone": to_zone
        })
        
        if not self.fire_events:
            _LOGGER.warning("?? Events disabled - zone change logged but not fired")
            return
        
        # Handle zone exit (leaving a known zone)
        if from_zone and from_zone != "not_home":
            _LOGGER.info("%s EXITED zone: %s at %s", person_name, from_zone, current_time)

            self.hass.bus.async_fire(EVENT_PERSON_EXITED_ZONE, {
                "person_id": person_id,
                "person_name": person_name,
                "zone_id": from_zone,
                "zone_name": from_zone.replace("_", " ").title(),
                "timestamp": datetime.now().isoformat()
            })

            if self.zone_notifications_enabled:
                _LOGGER.info("Sending departure notification for %s", person_name)
                await self._send_zone_notification(person_name, from_zone, "left", trip_time=current_time)
            else:
                _LOGGER.warning("Zone notifications disabled - not sending departure notification")

            # Store zone exit in RAG for pattern learning
            if self.ai:
                hass_ref = self.hass
                hass_ref.async_create_task(
                    self.ai.store_zone_visit(person_name, from_zone, "left",
                                             coords=(latitude, longitude))
                )

            self._start_trip(person_id, person_name, from_zone, current_coords)

        # Handle zone entry (arriving at a known zone)
        if to_zone != "not_home":
            _LOGGER.info("%s ENTERED zone: %s at %s", person_name, to_zone, current_time)

            self.hass.bus.async_fire(EVENT_PERSON_ENTERED_ZONE, {
                "person_id": person_id,
                "person_name": person_name,
                "zone_id": to_zone,
                "zone_name": to_zone.replace("_", " ").title(),
                "timestamp": datetime.now().isoformat()
            })

            trip_distance = None
            active_trip_data = self.active_trips.get(person_id)
            if person_id in self.active_trips:
                trip_distance = self.active_trips[person_id]["total_distance"]
                await self._end_trip(person_id, to_zone, current_coords)

            if self.zone_notifications_enabled:
                _LOGGER.info("Sending arrival notification for %s", person_name)
                await self._send_zone_notification(
                    person_name,
                    to_zone,
                    "arrived at",
                    trip_distance=trip_distance,
                    trip_time=current_time,
                    trip_data=active_trip_data,
                )
            else:
                _LOGGER.warning("Zone notifications disabled - not sending arrival notification")

            # Store zone entry in RAG for pattern learning
            if self.ai:
                self.hass.async_create_task(
                    self.ai.store_zone_visit(person_name, to_zone, "arrived at",
                                             coords=(latitude, longitude))
                )
    
    async def _check_speed_alerts(self, person_id: str, person_data: Dict):
        """Check for speed threshold violations"""
        
        if not self.speed_alerts_enabled:
            return
        
        speed = person_data.get("speed", 0)
        last_speed = self.last_speeds.get(person_id, 0)
        
        # Only alert if in vehicle
        activity = person_data.get("activity")
        if activity != ACTIVITY_IN_VEHICLE:
            self.last_speeds[person_id] = speed
            return
        
        # Determine severity
        severity = None
        if speed >= self.speed_excessive_threshold:
            severity = SEVERITY_CRITICAL
        elif speed >= self.speed_warning_threshold:
            severity = SEVERITY_HIGH
        
        # Fire alert if threshold exceeded and wasn't already alerted
        if severity and last_speed < self.speed_warning_threshold:
            person_name = person_data.get("name")
            
            # Log event
            self.event_logger.log_event("speed_alert", {
                "person_id": person_id,
                "person_name": person_name,
                "speed": speed,
                "threshold": self.speed_warning_threshold if severity == SEVERITY_HIGH else self.speed_excessive_threshold,
                "severity": severity
            })
            
            if self.fire_events:
                self.hass.bus.async_fire(EVENT_SPEED_ALERT, {
                    "person_id": person_id,
                    "person_name": person_name,
                    "speed": speed,
                    "threshold": self.speed_warning_threshold if severity == SEVERITY_HIGH else self.speed_excessive_threshold,
                    "severity": severity,
                    "timestamp": datetime.now().isoformat()
                })
            
            # ? FIX: Send notification with better logging
            _LOGGER.info("?? Sending speed alert for %s: %.0f mph", person_name, speed)
            await self._notify_all_family(
                title=f"?? Speed Alert: {person_name}",
                message=f"{person_name} is traveling at {speed:.0f} mph (threshold: {self.speed_warning_threshold:.0f} mph)",
                notification_id=f"speed_alert_{person_id}",
                priority="high" if severity == SEVERITY_HIGH else "critical"
            )
            
            _LOGGER.warning("Speed alert for %s: %.0f mph", person_name, speed)
        
        self.last_speeds[person_id] = speed
    
    async def _check_crash_detection(self, person_id: str, person_data: Dict):
        """Detect possible crashes based on sudden speed drops"""
        
        if not self.crash_detection_enabled:
            return
        
        speed = person_data.get("speed", 0)
        last_speed = self.last_speeds.get(person_id, 0)
        person_name = person_data.get("name")
        
        # Detect crash: Speed drops from 30+ mph to 0 within one update cycle
        # This indicates a sudden stop which could be a crash
        if last_speed >= 30 and speed == 0:
            # Log event
            self.event_logger.log_event("possible_crash", {
                "person_id": person_id,
                "person_name": person_name,
                "previous_speed": last_speed,
                "current_speed": speed,
                "location": person_data.get("location", {})
            })
            
            if self.fire_events:
                self.hass.bus.async_fire(EVENT_CRASH_DETECTED, {
                    "person_id": person_id,
                    "person_name": person_name,
                    "previous_speed": last_speed,
                    "location": person_data.get("location", {}),
                    "timestamp": datetime.now().isoformat()
                })
            
            # Get location info
            location = person_data.get("location", {})
            zone_name = location.get("zone", "Unknown").replace("_", " ").title()
            
            # Notify ALL family members with CRITICAL priority
            crash_message = (
                f"?? Possible crash detected!\n\n"
                f"{person_name} experienced sudden stop\n"
                f"Previous speed: {last_speed:.0f} mph ? 0 mph\n"
                f"Location: {zone_name}\n"
                f"Coordinates: {location.get('latitude')}, {location.get('longitude')}\n"
                f"Time: {datetime.now().strftime('%I:%M %p')}"
            )
            
            await self._notify_all_family(
                title=f"?? CRASH ALERT: {person_name}",
                message=crash_message,
                notification_id=f"crash_alert_{person_id}_{datetime.now().timestamp()}",
                priority="critical"
            )
            
            _LOGGER.critical("Possible crash detected for %s: %d mph ? 0 mph at %s", 
                           person_name, last_speed, zone_name)
    
    async def _check_battery_alerts(self, person_id: str, person_data: Dict):
        """Check for low battery and fire alerts"""
        
        if not self.low_battery_alerts_enabled:
            return
        
        battery = person_data.get("battery")
        
        if battery is None or battery > self.battery_alert_threshold:
            return
        
        # Check if we already alerted recently (within 1 hour)
        last_warning = self.last_battery_warnings.get(person_id)
        if last_warning:
            elapsed = (datetime.now() - last_warning).total_seconds()
            if elapsed < 3600:  # 1 hour
                return
        
        person_name = person_data.get("name")
        
        # Log event
        self.event_logger.log_event("low_battery", {
            "person_id": person_id,
            "person_name": person_name,
            "battery_level": battery,
            "threshold": self.battery_alert_threshold
        })
        
        if self.fire_events:
            self.hass.bus.async_fire(EVENT_LOW_BATTERY, {
                "person_id": person_id,
                "person_name": person_name,
                "battery_level": battery,
                "threshold": self.battery_alert_threshold,
                "timestamp": datetime.now().isoformat()
            })
        
        # Send notification
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": f"?? Low Battery: {person_name}",
                "message": f"{person_name}'s device battery is at {battery}%",
                "notification_id": f"low_battery_{person_id}"
            }
        )
        
        self.last_battery_warnings[person_id] = datetime.now()
        _LOGGER.info("Low battery alert for %s: %d%%", person_name, battery)
    
    async def _update_zone_occupancy(self, people_data: Dict) -> Dict[str, Any]:
        """Calculate which people are in which zones"""
        
        zones = {}
        
        for person_id, person_data in people_data.items():
            if not person_data.get("available"):
                continue
            
            zone = person_data["location"]["zone"]
            
            if zone not in zones:
                zones[zone] = {
                    "zone_id": zone,
                    "zone_name": zone.replace("_", " ").title(),
                    "occupants": []
                }
            
            zones[zone]["occupants"].append({
                "person_id": person_id,
                "person_name": person_data.get("name")
            })
        
        return zones
    
    def _calculate_statistics(self, people_data: Dict) -> Dict[str, Any]:
        """Calculate presence statistics"""
        
        total = 0
        home = 0
        away = 0
        driving = 0
        
        for person_data in people_data.values():
            if not person_data.get("available"):
                continue
            
            total += 1
            
            zone = person_data["location"]["zone"]
            activity = person_data.get("activity")
            
            if zone == "home":
                home += 1
            else:
                away += 1
            
            if activity == ACTIVITY_IN_VEHICLE:
                driving += 1
        
        return {
            "total_people": total,
            "people_home": home,
            "people_away": away,
            "people_driving": driving
        }
    
    async def _check_presence_milestones(self, data: Dict):
        """Check for everyone away / first home events"""
        
        if not self.fire_events:
            return
        
        statistics = data["statistics"]
        people_home = statistics.get("people_home", 0)
        total_people = statistics.get("total_people", 0)
        
        # Everyone away event
        if people_home == 0 and total_people > 0:
            # Check if this is a new state
            # TODO: Track previous state to avoid duplicate events
            
            self.hass.bus.async_fire(EVENT_EVERYONE_AWAY, {
                "timestamp": datetime.now().isoformat(),
                "total_people": total_people
            })
            
            _LOGGER.info("Everyone has left home")
        
        # First person home event
        if people_home == 1:
            # Find who's home
            for person_data in data["people"].values():
                if person_data.get("available") and person_data["location"]["zone"] == "home":
                    self.hass.bus.async_fire(EVENT_FIRST_PERSON_HOME, {
                        "timestamp": datetime.now().isoformat(),
                        "person_id": person_data["person_id"],
                        "person_name": person_data["name"]
                    })
                    
                    _LOGGER.info("First person home: %s", person_data["name"])
                    break
    
    async def _notify_all_family(self, title: str, message: str, notification_id: str, priority: str = "normal"):
        """Send notification to Home Assistant UI and all family members' phones
        
        Args:
            title: Notification title
            message: Notification message
            notification_id: Unique ID for the notification
            priority: 'normal', 'high', or 'critical'
        """
        
        # Send to Home Assistant persistent notification
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": notification_id
            }
        )
        
        _LOGGER.info("?? Sending notification to family: %s", title)
        
        # Send to all family members' phones
        notification_count = 0
        for person_config in self.people.values():
            person_name_cfg = person_config.get(CONF_PERSON_NAME, "unknown")
            device_tracker = person_config.get(CONF_DEVICE_TRACKER, "")
            if not device_tracker:
                _LOGGER.info(
                    "Notification skip: %s has no device tracker configured",
                    person_name_cfg
                )
                continue

            # Derive notify service from device tracker, or use explicit override
            # Override needed when tracker entity name != mobile app registration name
            # e.g. device_tracker.pixel_9_pro -> mobile_app_pixel_9_pro (WRONG)
            #      override: your_device_name -> mobile_app_your_device_name (RIGHT)
            notify_override = person_config.get(CONF_NOTIFY_SERVICE, "")
            if notify_override:
                notify_service = f"mobile_app_{notify_override}"
            else:
                device_name = device_tracker.replace("device_tracker.", "")
                notify_service = f"mobile_app_{device_name}"

            _LOGGER.info(
                "Attempting notification -> notify.%s (person: %s, tracker: %s, override: %s)",
                notify_service, person_name_cfg, device_tracker, notify_override or "none"
            )

            try:
                # Determine notification priority/channel
                data = {"channel": "general"}
                if priority == "silent":
                    data = {
                        "channel": "sophia_presence_anomaly",
                        "importance": "low",
                        "ttl": 0,
                        "vibrationPattern": "0",
                        "ledColor": "blue",
                    }
                elif priority == "high":
                    data = {
                        "channel": "alarm_stream",
                        "importance": "high",
                        "vibrationPattern": "100, 1000, 100, 1000"
                    }
                elif priority == "critical":
                    data = {
                        "channel": "alarm_stream_max",
                        "importance": "max",
                        "vibrationPattern": "100, 1000, 100, 1000, 100, 1000",
                        "ttl": 0,
                        "priority": "high"
                    }

                await self.hass.services.async_call(
                    "notify",
                    notify_service,
                    {
                        "title": title,
                        "message": message,
                        "data": data
                    },
                    blocking=True
                )
                notification_count += 1
                _LOGGER.info("Notification sent OK -> notify.%s", notify_service)
            except Exception as e:
                _LOGGER.warning(
                    "Notification FAILED -> notify.%s (person: %s): %s",
                    notify_service, person_name_cfg, e
                )

        _LOGGER.info("Notification dispatch complete: %d/%d succeeded",
                     notification_count, len(self.people))
    
    async def _send_zone_notification(self, person_name: str, zone: str, action: str, trip_distance: float = None, trip_time: str = None, trip_data: Dict = None):
        """Send zone arrival/departure notification to all family members.

        Uses AI-crafted message when available; falls back to static template.
        """
        zone_name = zone.replace("_", " ").title()

        # Try AI-crafted message first
        ai_message = None
        if self.ai and self.ai_features_enabled and self.data:
            all_people = self.data.get("people", {})
            ai_message = await self.ai.craft_zone_notification(
                person_name=person_name,
                zone=zone,
                action=action,
                trip_data=trip_data,
                all_people_data=all_people,
            )

        if ai_message:
            message = ai_message
        elif action == "arrived at" and trip_distance is not None:
            message = f"{person_name} arrived at {zone_name} at {trip_time} (Trip: {trip_distance:.1f} mi)"
        elif action == "left":
            message = f"{person_name} left {zone_name} at {trip_time}"
        else:
            message = f"{person_name} {action} {zone_name}"

        _LOGGER.info("Zone notification: %s", message)

        await self._notify_all_family(
            title="Location Update",
            message=message,
            notification_id=f"zone_{person_name}_{zone}_{action}",
            priority="normal",
        )
    
    def _start_trip(self, person_id: str, person_name: str, origin_zone: str, origin_coords: Tuple[float, float]):
        """Start tracking a new trip when person leaves a zone"""
        
        self.active_trips[person_id] = {
            "person_id": person_id,
            "person_name": person_name,
            "origin_zone": origin_zone,
            "origin_coords": origin_coords,
            "start_time": datetime.now(),
            "total_distance": 0.0,
            "max_speed": 0.0,
            "speed_samples": []
        }
        self.trip_speeds[person_id] = []
        
        _LOGGER.info("Started trip tracking for %s from %s", person_name, origin_zone)
    
    def _update_trip(self, person_id: str, speed: float, current_coords: Tuple[float, float]):
        """Update trip with current speed and calculate distance"""
        
        if person_id not in self.active_trips:
            return
        
        trip = self.active_trips[person_id]
        
        # Update max speed
        if speed > trip["max_speed"]:
            trip["max_speed"] = speed
        
        # Add speed sample for average calculation
        if speed > 0:  # Only count when moving
            trip["speed_samples"].append(speed)
        
        # Calculate distance traveled since last update
        if person_id in self.last_positions:
            last_lat, last_lon, _ = self.last_positions[person_id]
            distance_km = self._calculate_distance(last_lat, last_lon, current_coords[0], current_coords[1])
            distance_mi = distance_km * 0.621371
            trip["total_distance"] += distance_mi

        # Fire ETA prediction once per trip after 10+ minutes and 1+ mile
        if (
            self.ai
            and self.ai_features_enabled
            and not trip.get("eta_sent")
            and trip["total_distance"] >= 1.0
        ):
            start = trip.get("start_time")
            if start:
                try:
                    elapsed_mins = (datetime.now() - start).total_seconds() / 60
                    if elapsed_mins >= 10:
                        trip["eta_sent"] = True
                        person_data = (self.data or {}).get("people", {}).get(person_id, {})
                        if person_data:
                            self.hass.async_create_task(
                                self._send_eta_notification(person_id, trip, person_data)
                            )
                except Exception:
                    pass
    
    async def _end_trip(self, person_id: str, destination_zone: str, destination_coords: Tuple[float, float]):
        """End trip tracking and save to history"""
        
        if person_id not in self.active_trips:
            return
        
        trip = self.active_trips[person_id]
        
        # Calculate average speed
        if trip["speed_samples"]:
            avg_speed = sum(trip["speed_samples"]) / len(trip["speed_samples"])
        else:
            avg_speed = 0.0
        
        # Calculate trip duration
        duration = datetime.now() - trip["start_time"]
        
        # Create trip record
        trip_record = {
            "person_id": trip["person_id"],
            "person_name": trip["person_name"],
            "origin_zone": trip["origin_zone"],
            "destination_zone": destination_zone,
            "start_time": trip["start_time"].isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_minutes": duration.total_seconds() / 60,
            "distance_miles": trip["total_distance"],
            "avg_speed_mph": avg_speed,
            "max_speed_mph": trip["max_speed"]
        }
        
        # Add to trip history
        self.trip_history.append(trip_record)
        
        # Clean up old trips (keep last 30 days)
        cutoff_date = datetime.now() - timedelta(days=self.trip_retention_days)
        self.trip_history = [
            t for t in self.trip_history 
            if datetime.fromisoformat(t["end_time"]) > cutoff_date
        ]
        
        # Store completed trip in RAG for future pattern / anomaly / ETA use
        if self.ai:
            self.hass.async_create_task(self.ai.store_trip(trip_record))

        # Log trip
        origin_name = trip["origin_zone"].replace("_", " ").title()
        dest_name = destination_zone.replace("_", " ").title()
        
        self.event_logger.log_event("trip_completed", trip_record)
        
        _LOGGER.info(
            "%s travelled from %s to %s, trip details: Avg Speed %.1f mph, Top Speed %.1f mph, Distance %.1f mi",
            trip["person_name"],
            origin_name,
            dest_name,
            avg_speed,
            trip["max_speed"],
            trip["total_distance"]
        )
        
        # Send trip summary notification
        trip_message = (
            f"?? {trip['person_name']} travelled from {origin_name} to {dest_name}. "
            f"Trip details: Avg Speed {avg_speed:.1f} mph, Top Speed {trip['max_speed']:.1f} mph, "
            f"Distance {trip['total_distance']:.1f} mi"
        )
        
        await self._notify_all_family(
            title="?? Trip Completed",
            message=trip_message,
            notification_id=f"trip_{person_id}_{datetime.now().timestamp()}",
            priority="normal"
        )
        
        # Clean up active trip
        del self.active_trips[person_id]
        if person_id in self.trip_speeds:
            del self.trip_speeds[person_id]
    
    async def _send_eta_notification(self, person_id: str, trip_data: Dict, person_data: Dict):
        """Send a mid-trip ETA notification using AI prediction."""
        if not self.ai:
            return
        eta = await self.ai.predict_arrival(
            trip_data=trip_data,
            person_data=person_data,
            destination_hint="home",
        )
        if eta:
            person_name = trip_data.get("person_name", person_id)
            await self._notify_all_family(
                title=f"Trip Update: {person_name}",
                message=eta,
                notification_id=f"eta_{person_id}_{datetime.now().timestamp():.0f}",
                priority="normal",
            )

    async def async_manual_location_update(self, person_id: str, latitude: float, longitude: float):
        """Handle manual location update"""
        
        _LOGGER.info("Manual location update for %s: %s, %s", person_id, latitude, longitude)
        
        # This would update the person's location
        # For now, just trigger a refresh
        await self.async_request_refresh()