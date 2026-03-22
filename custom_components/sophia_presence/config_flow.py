# -*- coding: utf-8 -*-
"""Config flow for SOPHIA Presence"""
import re
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    VERSION,
    TRACKING_METHOD_COMPANION,
    TRACKING_METHOD_DEVICE_TRACKER,
    TRACKING_METHOD_GPS,
    TRACKING_METHOD_NETWORK,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_HISTORY_RETENTION,
    DEFAULT_SPEED_WARNING,
    DEFAULT_SPEED_EXCESSIVE,
    DEFAULT_BATTERY_THRESHOLD,
    DEFAULT_STATIONARY_ZONE_SUGGESTION,
    ZONE_ICONS,
    CONF_TRACKING_METHOD,
    CONF_PEOPLE,
    CONF_UPDATE_INTERVAL,
    CONF_HISTORY_RETENTION,
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
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_DEVICE_TRACKER,
    CONF_NOTIFY_SERVICE,
    CONF_ACTIVITY_SENSOR,
    CONF_BATTERY_SENSOR,
    CONF_AVATAR,
    CONF_PRIVACY_MODE,
    CONF_ENABLE_NOTIFICATIONS,
    CONF_SPEED_WARNING_THRESHOLD,
    CONF_SPEED_EXCESSIVE_THRESHOLD,
    CONF_BATTERY_ALERT_THRESHOLD,
    CONF_WORK_LOCATION,
    AI_FEATURE_ARRIVAL_PREDICTION,
    AI_FEATURE_PATTERN_RECOGNITION,
    AI_FEATURE_ANOMALY_DETECTION,
    AI_FEATURE_SMART_NOTIFICATIONS,
)


class SophiaPresenceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SOPHIA Presence"""

    VERSION = 2

    def __init__(self):
        """Initialize the config flow"""
        self.data = {}
        self.people = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - Welcome screen"""
        
        # Check SOPHIA Core dependency
        if "sophia_core" not in self.hass.data:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors={"base": "sophia_core_not_found"},
                description_placeholders={
                    "info": (
                        "?? SOPHIA Core is required but not found.\n\n"
                        "Please install and configure SOPHIA Core first, then return to set up SOPHIA Presence."
                    )
                },
            )
        
        if user_input is not None:
            return await self.async_step_tracking_method()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "info": (
                    "# Welcome to SOPHIA Presence! \n\n"
                    "**Track your family's locations with AI-powered intelligence.**\n\n"
                    "? Features:\n"
                    "- Real-time location tracking\n"
                    "- Geofence zones with notifications\n"
                    "- Speed alerts and crash detection\n"
                    "- Privacy controls per person\n"
                    "- AI-powered arrival predictions\n"
                    "- Pattern recognition and anomaly detection\n"
                    "- Integration with SOPHIA Climate and future modules\n\n"
                    "This wizard will guide you through setup in a few easy steps.\n\n"
                    "**Ready to start?** Click Submit to continue!"
                )
            },
        )

    async def async_step_tracking_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Select tracking method"""
        
        errors = {}
        
        if user_input is not None:
            self.data[CONF_TRACKING_METHOD] = user_input[CONF_TRACKING_METHOD]
            return await self.async_step_add_person()

        return self.async_show_form(
            step_id="tracking_method",
            data_schema=vol.Schema({
                vol.Required(CONF_TRACKING_METHOD, default=TRACKING_METHOD_COMPANION): vol.In({
                    TRACKING_METHOD_COMPANION: "Home Assistant Companion App (Recommended)",
                    TRACKING_METHOD_DEVICE_TRACKER: "Existing device_tracker Entities",
                    TRACKING_METHOD_GPS: "GPS Coordinates (Manual/API)",
                    TRACKING_METHOD_NETWORK: "Network Detection (WiFi/Bluetooth)",
                }),
            }),
            errors=errors,
            description_placeholders={
                "info": (
                    "## How do you track locations?\n\n"
                    "**Companion App (Recommended):**\n"
                    "Uses Home Assistant mobile app for accurate GPS tracking.\n\n"
                    "**Existing device_tracker:**\n"
                    "Use any existing device_tracker entities you've already configured.\n\n"
                    "**GPS Coordinates:**\n"
                    "Manual entry or API integration for GPS data.\n\n"
                    "**Network Detection:**\n"
                    "Uses WiFi or Bluetooth presence detection (less accurate outdoors)."
                )
            },
        )

    async def async_step_add_person(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Add people to track"""
        
        errors = {}
        
        if user_input is not None:
            # Get person entity (REQUIRED)
            person_entity_id = user_input.get("person_entity")
            
            if not person_entity_id:
                errors["base"] = "person_required"
            else:
                # Get person entity state
                person_state = self.hass.states.get(person_entity_id)
                
                if not person_state:
                    errors["base"] = "person_not_found"
                else:
                    # Extract person_id from entity_id (e.g., person.john -> john)
                    person_id = person_entity_id.replace("person.", "")
                    
                    # Get name from person entity
                    person_name = person_state.attributes.get("friendly_name", person_state.name)
                    
                    # Get avatar from person entity
                    avatar_url = person_state.attributes.get("entity_picture", "")
                    
                    # Get device trackers linked to this person
                    linked_trackers = person_state.attributes.get("source", [])
                    if isinstance(linked_trackers, str):
                        linked_trackers = [linked_trackers]
                    
                    # Use first linked tracker as default
                    default_tracker = linked_trackers[0] if linked_trackers else None
                    
                    # Check if person already added
                    if any(p[CONF_PERSON_ID] == person_id for p in self.people):
                        errors["base"] = "person_already_exists"
                    else:
                        # Add person to list
                        person_config = {
                            CONF_PERSON_ID: person_id,
                            CONF_PERSON_NAME: person_name,
                            CONF_DEVICE_TRACKER: user_input.get(CONF_DEVICE_TRACKER) or default_tracker,
                            CONF_ACTIVITY_SENSOR: user_input.get(CONF_ACTIVITY_SENSOR),
                            CONF_BATTERY_SENSOR: user_input.get(CONF_BATTERY_SENSOR),
                            CONF_AVATAR: avatar_url,
                            CONF_PRIVACY_MODE: user_input.get(CONF_PRIVACY_MODE, False),
                            CONF_ENABLE_NOTIFICATIONS: user_input.get(CONF_ENABLE_NOTIFICATIONS, True),
                            CONF_WORK_LOCATION: user_input.get(CONF_WORK_LOCATION, ""),
                            "person_entity": person_entity_id,  # Store reference
                        }
                        
                        self.people.append(person_config)
                        
                        # Check if user wants to add another person
                        if user_input.get("add_another", False):
                            return await self.async_step_add_person()
                        else:
                            self.data[CONF_PEOPLE] = self.people
                            return await self.async_step_safety_features()

        # Build schema - REQUIRED person entity selector
        schema = {
            vol.Required("person_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
        }
        
        tracking_method = self.data.get(CONF_TRACKING_METHOD)
        
        if tracking_method == TRACKING_METHOD_COMPANION or tracking_method == TRACKING_METHOD_DEVICE_TRACKER:
            schema[vol.Optional(CONF_DEVICE_TRACKER)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker")
            )
            schema[vol.Optional(CONF_ACTIVITY_SENSOR)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
            schema[vol.Optional(CONF_BATTERY_SENSOR)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
        
        schema.update({
            vol.Optional(CONF_NOTIFY_SERVICE, default=""): selector.TextSelector(),
            vol.Optional(CONF_WORK_LOCATION, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_PRIVACY_MODE, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_ENABLE_NOTIFICATIONS, default=True): selector.BooleanSelector(),
            vol.Optional("add_another", default=False): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="add_person",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "info": (
                    f"## Add Person #{len(self.people) + 1}\n\n"
                    f"**Currently added:** {', '.join(p[CONF_PERSON_NAME] for p in self.people) if self.people else 'None yet'}\n\n"
                    "**Select a Home Assistant Person:**\n\n"
                    "- **Person** (REQUIRED): Choose from your configured HA users\n"
                    "  - Name and avatar auto-populate from person entity\n"
                    "  - Linked device trackers pre-selected from person config\n"
                    "  - Only actual HA users can be tracked (for security)\n"
                    "  - Integrates with HA Mobile App automatically\n\n"
                    "- **Device Tracker**: (Optional) Override auto-detected tracker\n"
                    "- **Activity Sensor**: (Optional) For detecting driving, walking, etc.\n"
                    "- **Battery Sensor**: (Optional) For low battery alerts\n\n"
                    "Check 'Add Another Person' to add more, or uncheck to continue.\n\n"
                    "*Note: Create Person entities first (Settings ? People) if they don't exist*"
                )
            },
        )

    async def async_step_safety_features(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Configure safety features"""
        
        if user_input is not None:
            self.data[CONF_CRASH_DETECTION] = user_input.get(CONF_CRASH_DETECTION, False)
            self.data[CONF_SPEED_ALERTS] = user_input.get(CONF_SPEED_ALERTS, False)
            self.data[CONF_LOW_BATTERY_ALERTS] = user_input.get(CONF_LOW_BATTERY_ALERTS, False)
            self.data[CONF_SPEED_WARNING_THRESHOLD] = user_input.get(CONF_SPEED_WARNING_THRESHOLD, DEFAULT_SPEED_WARNING)
            self.data[CONF_SPEED_EXCESSIVE_THRESHOLD] = user_input.get(CONF_SPEED_EXCESSIVE_THRESHOLD, DEFAULT_SPEED_EXCESSIVE)
            self.data[CONF_BATTERY_ALERT_THRESHOLD] = user_input.get(CONF_BATTERY_ALERT_THRESHOLD, DEFAULT_BATTERY_THRESHOLD)
            
            return await self.async_step_zone_management()

        return self.async_show_form(
            step_id="safety_features",
            data_schema=vol.Schema({
                vol.Optional(CONF_CRASH_DETECTION, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_SPEED_ALERTS, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_SPEED_WARNING_THRESHOLD, default=DEFAULT_SPEED_WARNING): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=50,
                        max=100,
                        step=5,
                        unit_of_measurement="mph",
                        mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Optional(CONF_SPEED_EXCESSIVE_THRESHOLD, default=DEFAULT_SPEED_EXCESSIVE): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=75,
                        max=120,
                        step=5,
                        unit_of_measurement="mph",
                        mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Optional(CONF_LOW_BATTERY_ALERTS, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_BATTERY_ALERT_THRESHOLD, default=DEFAULT_BATTERY_THRESHOLD): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=50,
                        step=5,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
            }),
            description_placeholders={
                "info": (
                    "## Safety & Alert Features\n\n"
                    "**Crash Detection:**\n"
                    "Monitors for sudden stops and high G-forces while driving.\n\n"
                    "**Speed Alerts:**\n"
                    "Receive notifications when speeds exceed thresholds.\n"
                    "- Warning: First level alert\n"
                    "- Excessive: Critical alert\n\n"
                    "**Low Battery Alerts:**\n"
                    "Get notified when tracked devices run low on battery."
                )
            },
        )

    async def async_step_zone_management(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 5: Configure zone/geofence management"""
        
        if user_input is not None:
            self.data[CONF_HOME_ZONE] = user_input.get(CONF_HOME_ZONE, "zone.home")
            self.data[CONF_USE_HA_ZONES] = user_input.get(CONF_USE_HA_ZONES, True)
            self.data[CONF_ZONE_NOTIFICATIONS] = user_input.get(CONF_ZONE_NOTIFICATIONS, True)
            self.data[CONF_ZONE_AUTO_SUGGEST] = user_input.get(CONF_ZONE_AUTO_SUGGEST, True)
            
            return await self.async_step_advanced_settings()

        return self.async_show_form(
            step_id="zone_management",
            data_schema=vol.Schema({
                vol.Optional(CONF_HOME_ZONE, default="zone.home"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
                vol.Optional(CONF_USE_HA_ZONES, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_ZONE_NOTIFICATIONS, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_ZONE_AUTO_SUGGEST, default=True): selector.BooleanSelector(),
            }),
            description_placeholders={
                "info": (
                    "## Zone & Geofence Settings\n\n"
                    "**Use Home Assistant Zones:**\n"
                    "Integrate with existing HA zones (Home, Work, etc.)\n\n"
                    "**Zone Notifications:**\n"
                    "Get notified when people arrive or leave zones.\n\n"
                    "**Auto-Suggest Zones:**\n"
                    "SOPHIA will suggest creating zones for frequently visited locations.\n"
                    "This helps save battery by disabling high-accuracy GPS at known locations."
                )
            },
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 6: Advanced settings"""
        
        if user_input is not None:
            self.data[CONF_UPDATE_INTERVAL] = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            self.data[CONF_HISTORY_RETENTION] = user_input.get(CONF_HISTORY_RETENTION, DEFAULT_HISTORY_RETENTION)
            self.data[CONF_AI_FEATURES] = user_input.get(CONF_AI_FEATURES, False)
            
            if self.data[CONF_AI_FEATURES]:
                return await self.async_step_ai_features()
            else:
                return await self.async_step_integration_options()

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=vol.Schema({
                vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=600,
                        step=30,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Optional(CONF_HISTORY_RETENTION, default=DEFAULT_HISTORY_RETENTION): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=90,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Optional(CONF_AI_FEATURES, default=False): selector.BooleanSelector(),
            }),
            description_placeholders={
                "info": (
                    "## Advanced Settings\n\n"
                    "**Update Interval:**\n"
                    "How often to check locations. Lower = more battery usage.\n"
                    "Recommended: 60 seconds\n\n"
                    "**History Retention:**\n"
                    "How long to keep location history data.\n\n"
                    "**AI-Powered Features:**\n"
                    "Enable SOPHIA's LLM for intelligent predictions and insights.\n"
                    "Requires SOPHIA Core LLM to be configured."
                )
            },
        )

    async def async_step_ai_features(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 6b: Select AI features to enable"""
        
        if user_input is not None:
            ai_features = []
            if user_input.get(AI_FEATURE_ARRIVAL_PREDICTION, False):
                ai_features.append(AI_FEATURE_ARRIVAL_PREDICTION)
            if user_input.get(AI_FEATURE_PATTERN_RECOGNITION, False):
                ai_features.append(AI_FEATURE_PATTERN_RECOGNITION)
            if user_input.get(AI_FEATURE_ANOMALY_DETECTION, False):
                ai_features.append(AI_FEATURE_ANOMALY_DETECTION)
            if user_input.get(AI_FEATURE_SMART_NOTIFICATIONS, False):
                ai_features.append(AI_FEATURE_SMART_NOTIFICATIONS)
            
            self.data[CONF_AI_FEATURES_LIST] = ai_features
            
            return await self.async_step_integration_options()

        return self.async_show_form(
            step_id="ai_features",
            data_schema=vol.Schema({
                vol.Optional(AI_FEATURE_ARRIVAL_PREDICTION, default=True): selector.BooleanSelector(),
                vol.Optional(AI_FEATURE_PATTERN_RECOGNITION, default=True): selector.BooleanSelector(),
                vol.Optional(AI_FEATURE_ANOMALY_DETECTION, default=True): selector.BooleanSelector(),
                vol.Optional(AI_FEATURE_SMART_NOTIFICATIONS, default=True): selector.BooleanSelector(),
            }),
            description_placeholders={
                "info": (
                    "## AI-Powered Features\n\n"
                    "**Arrival Time Prediction:**\n"
                    "Predict when people will arrive at destinations based on location and traffic.\n\n"
                    "**Pattern Recognition:**\n"
                    "Learn daily routines and regular locations automatically.\n\n"
                    "**Anomaly Detection:**\n"
                    "Get alerted to unusual location patterns or behaviors.\n\n"
                    "**Smart Notifications:**\n"
                    "Contextual, intelligent alerts tailored to each situation.\n\n"
                    "*All AI processing happens locally via SOPHIA Core's LLM.*"
                )
            },
        )

    async def async_step_integration_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 7: Integration options with other SOPHIA modules"""
        
        if user_input is not None:
            self.data[CONF_FIRE_EVENTS] = user_input.get(CONF_FIRE_EVENTS, True)
            
            # Create the entry!
            return self.async_create_entry(
                title=f"SOPHIA Presence ({len(self.people)} people)",
                data=self.data
            )

        return self.async_show_form(
            step_id="integration_options",
            data_schema=vol.Schema({
                vol.Optional(CONF_FIRE_EVENTS, default=True): selector.BooleanSelector(),
            }),
            description_placeholders={
                "info": (
                    "## Integration with Other Modules\n\n"
                    "**Fire Events for Other Modules:**\n"
                    "Allow other SOPHIA modules to respond to presence events.\n\n"
                    "**Examples:**\n"
                    "- SOPHIA Climate: Switch to eco mode when everyone leaves\n"
                    "- Future Security Module: Arm system when away\n"
                    "- Future Lighting Module: Turn off lights when leaving\n\n"
                    "**Ready to finish?** Click Submit to complete setup!\n\n"
                    f"?? Summary: {len(self.people)} people, "
                    f"{'AI enabled' if self.data.get(CONF_AI_FEATURES) else 'AI disabled'}, "
                    f"{self.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)}s updates"
                )
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler"""
        return SophiaPresenceOptionsFlowHandler()


class SophiaPresenceOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for SOPHIA Presence"""

    async def async_step_init(self, user_input=None):
        """Manage the options - main menu"""
        if user_input is not None:
            action = user_input.get("action")
            
            if action == "settings":
                return await self.async_step_settings()
            elif action == "manage_people":
                return await self.async_step_manage_people()
            elif action == "done":
                return self.async_create_entry(title="", data={})
        
        # Main menu
        current_people = self.config_entry.data.get(CONF_PEOPLE, [])
        people_list = ", ".join(p[CONF_PERSON_NAME] for p in current_people) if current_people else "None"
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="settings"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "settings", "label": "Adjust Settings"},
                            {"value": "manage_people", "label": "Manage People (Add/Remove)"},
                            {"value": "done", "label": "Done - Close Options"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "info": (
                    f"## SOPHIA Presence Configuration\n\n"
                    f"**Currently tracking:** {people_list}\n\n"
                    "**What would you like to do?**\n\n"
                    "- **Adjust Settings**: Change update intervals, alerts, features\n"
                    "- **Manage People**: Add new people or remove existing ones\n"
                    "- **Done**: Close options and apply changes"
                )
            },
        )
    
    async def async_step_settings(self, user_input=None):
        """Adjust integration settings"""
        if user_input is not None:
            # Update config entry with new settings
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data
            )
            return await self.async_step_init()
        
        # Get current config with safe defaults
        config_data = self.config_entry.data
        
        # Settings form
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=config_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=600,
                        step=30,
                        unit_of_measurement="seconds",
                        mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Optional(
                    CONF_CRASH_DETECTION,
                    default=config_data.get(CONF_CRASH_DETECTION, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_SPEED_ALERTS,
                    default=config_data.get(CONF_SPEED_ALERTS, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_LOW_BATTERY_ALERTS,
                    default=config_data.get(CONF_LOW_BATTERY_ALERTS, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ZONE_NOTIFICATIONS,
                    default=config_data.get(CONF_ZONE_NOTIFICATIONS, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_AI_FEATURES,
                    default=config_data.get(CONF_AI_FEATURES, False)
                ): selector.BooleanSelector(),
            }),
            description_placeholders={
                "info": (
                    "## Adjust Settings\n\n"
                    "- **Update Interval**: How often to check locations\n"
                    "- **Crash Detection**: Monitor for sudden stops\n"
                    "- **Speed Alerts**: Notify on speeding\n"
                    "- **Low Battery Alerts**: Notify on low battery\n"
                    "- **Zone Notifications**: Notify on zone changes\n"
                    "- **AI Features**: Enable AI-powered predictions\n\n"
                    "*Changes take effect immediately!*"
                )
            },
        )
    
    async def async_step_manage_people(self, user_input=None):
        """Manage people - add, edit, or remove"""
        if user_input is not None:
            action = user_input.get("action")

            if action == "add_person":
                return await self.async_step_add_person()
            elif action == "edit_person":
                return await self.async_step_edit_person_select()
            elif action == "remove_person":
                return await self.async_step_remove_person()
            elif action == "back":
                return await self.async_step_init()

        current_people = self.config_entry.data.get(CONF_PEOPLE, [])
        people_list = "\n".join(f"- {p[CONF_PERSON_NAME]}" for p in current_people) if current_people else "- None"

        return self.async_show_form(
            step_id="manage_people",
            data_schema=vol.Schema({
                vol.Required("action", default="add_person"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "add_person", "label": "Add New Person"},
                            {"value": "edit_person", "label": "Edit Person Settings"},
                            {"value": "remove_person", "label": "Remove Person"},
                            {"value": "back", "label": "Back to Main Menu"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "info": (
                    f"## Manage People\n\n"
                    f"**Currently tracking:**\n{people_list}\n\n"
                    "**What would you like to do?**\n\n"
                    "- **Add New Person**: Track a new family member or friend\n"
                    "- **Edit Person Settings**: Update notify service, sensors, privacy\n"
                    "- **Remove Person**: Stop tracking someone\n"
                    "- **Back**: Return to main menu"
                )
            },
        )
    
    async def async_step_add_person(self, user_input=None):
        """Add a new person to track"""
        errors = {}
        
        if user_input is not None:
            # Get person entity (REQUIRED)
            person_entity_id = user_input.get("person_entity")
            
            if not person_entity_id:
                errors["base"] = "person_required"
            else:
                # Get person entity state
                person_state = self.hass.states.get(person_entity_id)
                
                if not person_state:
                    errors["base"] = "person_not_found"
                else:
                    # Extract person_id from entity_id
                    person_id = person_entity_id.replace("person.", "")
                    
                    # Get name from person entity
                    person_name = person_state.attributes.get("friendly_name", person_state.name)
                    
                    # Get avatar from person entity
                    avatar_url = person_state.attributes.get("entity_picture", "")
                    
                    # Get device trackers linked to this person
                    linked_trackers = person_state.attributes.get("source", [])
                    if isinstance(linked_trackers, str):
                        linked_trackers = [linked_trackers]
                    
                    # Use first linked tracker as default
                    default_tracker = linked_trackers[0] if linked_trackers else None
                    
                    # Check if person already added
                    current_people = self.config_entry.data.get(CONF_PEOPLE, [])
                    if any(p[CONF_PERSON_ID] == person_id for p in current_people):
                        errors["base"] = "person_already_exists"
                    else:
                        # Add person to list
                        person_config = {
                            CONF_PERSON_ID: person_id,
                            CONF_PERSON_NAME: person_name,
                            CONF_DEVICE_TRACKER: user_input.get(CONF_DEVICE_TRACKER) or default_tracker,
                            CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE, ""),
                            CONF_ACTIVITY_SENSOR: user_input.get(CONF_ACTIVITY_SENSOR),
                            CONF_BATTERY_SENSOR: user_input.get(CONF_BATTERY_SENSOR),
                            CONF_AVATAR: avatar_url,
                            CONF_PRIVACY_MODE: user_input.get(CONF_PRIVACY_MODE, False),
                            CONF_ENABLE_NOTIFICATIONS: user_input.get(CONF_ENABLE_NOTIFICATIONS, True),
                            CONF_WORK_LOCATION: user_input.get(CONF_WORK_LOCATION, ""),
                            "person_entity": person_entity_id,
                        }
                        
                        # Update config entry
                        new_people = current_people + [person_config]
                        new_data = {**self.config_entry.data, CONF_PEOPLE: new_people}
                        self.hass.config_entries.async_update_entry(
                            self.config_entry,
                            data=new_data
                        )
                        
                        # Force reload to create new entities
                        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                        
                        return await self.async_step_manage_people()
        
        # Build schema
        tracking_method = self.config_entry.data.get(CONF_TRACKING_METHOD)
        schema = {
            vol.Required("person_entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
        }
        
        if tracking_method in [TRACKING_METHOD_COMPANION, TRACKING_METHOD_DEVICE_TRACKER]:
            schema[vol.Optional(CONF_DEVICE_TRACKER)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker")
            )
            schema[vol.Optional(CONF_ACTIVITY_SENSOR)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
            schema[vol.Optional(CONF_BATTERY_SENSOR)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
        
        schema.update({
            vol.Optional(CONF_NOTIFY_SERVICE, default=""): selector.TextSelector(),
            vol.Optional(CONF_WORK_LOCATION, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_PRIVACY_MODE, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_ENABLE_NOTIFICATIONS, default=True): selector.BooleanSelector(),
        })
        
        return self.async_show_form(
            step_id="add_person",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "info": (
                    "## Add New Person\n\n"
                    "**Select a Home Assistant Person:**\n\n"
                    "- **Person** (REQUIRED): Choose from your configured HA users\n"
                    "  - Name and avatar auto-populate\n"
                    "  - Linked device trackers pre-selected\n"
                    "- **Device Tracker**: (Optional) Override auto-detected tracker\n"
                    "- **Activity/Battery Sensors**: (Optional) For additional data\n"
                    "- **Work Location**: (Optional) e.g. 'My Workplace' - helps anomaly detection\n\n"
                    "*The integration will reload and create new entities automatically!*"
                )
            },
        )
    
    async def async_step_remove_person(self, user_input=None):
        """Remove a person from tracking"""
        current_people = self.config_entry.data.get(CONF_PEOPLE, [])
        
        if not current_people:
            # No people to remove, go back
            return await self.async_step_manage_people()
        
        if user_input is not None:
            person_to_remove = user_input.get("person_to_remove")
            
            if person_to_remove:
                # Remove person from list
                new_people = [p for p in current_people if p[CONF_PERSON_ID] != person_to_remove]
                new_data = {**self.config_entry.data, CONF_PEOPLE: new_people}
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data
                )
                
                # Force reload to remove entities
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                
                return await self.async_step_manage_people()
        
        # Build options for people to remove
        people_options = [
            {"value": p[CONF_PERSON_ID], "label": p[CONF_PERSON_NAME]}
            for p in current_people
        ]
        
        return self.async_show_form(
            step_id="remove_person",
            data_schema=vol.Schema({
                vol.Required("person_to_remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=people_options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "info": (
                    "## Remove Person\n\n"
                    "**Select a person to stop tracking:**\n\n"
                    "*All entities for this person will be removed.*\n"
                    "*The integration will reload automatically!*"
                )
            },
        )

    async def async_step_edit_person_select(self, user_input=None):
        """Select which person to edit"""
        current_people = self.config_entry.data.get(CONF_PEOPLE, [])

        if not current_people:
            return await self.async_step_manage_people()

        if user_input is not None:
            self._edit_person_id = user_input.get("person_to_edit")
            return await self.async_step_edit_person()

        people_options = [
            {"value": p[CONF_PERSON_ID], "label": p[CONF_PERSON_NAME]}
            for p in current_people
        ]

        return self.async_show_form(
            step_id="edit_person_select",
            data_schema=vol.Schema({
                vol.Required("person_to_edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=people_options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "info": "## Edit Person\n\n**Select a person to edit:**"
            },
        )

    async def async_step_edit_person(self, user_input=None):
        """Edit settings for a specific person"""
        current_people = self.config_entry.data.get(CONF_PEOPLE, [])
        person_id = getattr(self, "_edit_person_id", None)

        if not person_id:
            return await self.async_step_manage_people()

        # Find existing config for this person
        existing = next(
            (p for p in current_people if p[CONF_PERSON_ID] == person_id), None
        )
        if not existing:
            return await self.async_step_manage_people()

        person_name = existing.get(CONF_PERSON_NAME, person_id)

        if user_input is not None:
            # Merge updates into existing person config
            updated = {
                **existing,
                CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE, ""),
                CONF_DEVICE_TRACKER: user_input.get(CONF_DEVICE_TRACKER) or existing.get(CONF_DEVICE_TRACKER),
                CONF_ACTIVITY_SENSOR: user_input.get(CONF_ACTIVITY_SENSOR) or existing.get(CONF_ACTIVITY_SENSOR),
                CONF_BATTERY_SENSOR: user_input.get(CONF_BATTERY_SENSOR) or existing.get(CONF_BATTERY_SENSOR),
                CONF_PRIVACY_MODE: user_input.get(CONF_PRIVACY_MODE, existing.get(CONF_PRIVACY_MODE, False)),
                CONF_ENABLE_NOTIFICATIONS: user_input.get(CONF_ENABLE_NOTIFICATIONS, existing.get(CONF_ENABLE_NOTIFICATIONS, True)),
                CONF_WORK_LOCATION: user_input.get(CONF_WORK_LOCATION, existing.get(CONF_WORK_LOCATION, "")),
            }

            new_people = [
                updated if p[CONF_PERSON_ID] == person_id else p
                for p in current_people
            ]
            new_data = {**self.config_entry.data, CONF_PEOPLE: new_people}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

            # Reload to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return await self.async_step_manage_people()

        tracking_method = self.config_entry.data.get(CONF_TRACKING_METHOD)

        schema = {}
        if tracking_method in [TRACKING_METHOD_COMPANION, TRACKING_METHOD_DEVICE_TRACKER]:
            schema[vol.Optional(
                CONF_DEVICE_TRACKER,
                default=existing.get(CONF_DEVICE_TRACKER, "")
            )] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker")
            )
            schema[vol.Optional(
                CONF_ACTIVITY_SENSOR,
                default=existing.get(CONF_ACTIVITY_SENSOR, "")
            )] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
            schema[vol.Optional(
                CONF_BATTERY_SENSOR,
                default=existing.get(CONF_BATTERY_SENSOR, "")
            )] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )

        schema.update({
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                default=existing.get(CONF_NOTIFY_SERVICE, "")
            ): selector.TextSelector(),
            vol.Optional(
                CONF_WORK_LOCATION,
                default=existing.get(CONF_WORK_LOCATION, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_PRIVACY_MODE,
                default=existing.get(CONF_PRIVACY_MODE, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_ENABLE_NOTIFICATIONS,
                default=existing.get(CONF_ENABLE_NOTIFICATIONS, True)
            ): selector.BooleanSelector(),
        })

        current_notify = existing.get(CONF_NOTIFY_SERVICE, "")
        current_tracker = existing.get(CONF_DEVICE_TRACKER, "none")

        return self.async_show_form(
            step_id="edit_person",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "info": (
                    f"## Edit {person_name}\n\n"
                    f"**Current device tracker:** {current_tracker}\n"
                    f"**Current notify service:** "
                    f"{'mobile_app_' + current_notify if current_notify else 'auto (from tracker)'}\n\n"
                    "**Notify Service Override:**\n"
                    "Fill this ONLY if your mobile app notify service name doesn't match "
                    "your device tracker name.\n"
                    "Example: if notify service is `notify.mobile_app_your_device_name`, "
                    "enter `your_device_name`\n"
                    "Leave blank to auto-derive from device tracker."
                )
            },
        )