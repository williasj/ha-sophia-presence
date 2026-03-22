# -*- coding: utf-8 -*-
"""Constants for SOPHIA Presence"""

DOMAIN = "sophia_presence"
VERSION = "1.3.0"

# Platforms
PLATFORMS = ["sensor", "device_tracker", "switch", "text"]

# Service names
SERVICES = [
    "update_location",
    "add_person",
    "remove_person",
    "create_zone",
    "request_checkin",
    "trigger_sos",
    "get_location_history",
    "add_zone_from_location",
    "get_daily_summary",
]

# Default configuration
DEFAULT_UPDATE_INTERVAL = 60  # seconds
DEFAULT_HISTORY_RETENTION = 30  # days
DEFAULT_ZONE_RADIUS = 100  # meters
DEFAULT_SPEED_WARNING = 75  # mph
DEFAULT_SPEED_EXCESSIVE = 90  # mph
DEFAULT_BATTERY_THRESHOLD = 20  # percent
DEFAULT_STATIONARY_ZONE_SUGGESTION = 30  # minutes

# Activity types
ACTIVITY_IN_VEHICLE = "in_vehicle"
ACTIVITY_ON_BICYCLE = "on_bicycle"
ACTIVITY_WALKING = "walking"
ACTIVITY_RUNNING = "running"
ACTIVITY_STATIONARY = "stationary"
ACTIVITY_STILL = "still"
ACTIVITY_UNKNOWN = "unknown"

# Privacy modes
PRIVACY_MODE_OFF = "off"
PRIVACY_MODE_BLUR = "blur"  # Show zone only
PRIVACY_MODE_HIDDEN = "hidden"  # Hide completely

# Tracking methods
TRACKING_METHOD_COMPANION = "companion_app"
TRACKING_METHOD_DEVICE_TRACKER = "device_tracker"
TRACKING_METHOD_GPS = "gps_api"
TRACKING_METHOD_NETWORK = "network"

# Event types
EVENT_PERSON_ENTERED_ZONE = f"{DOMAIN}_zone_entered"
EVENT_PERSON_EXITED_ZONE = f"{DOMAIN}_zone_exited"
EVENT_EVERYONE_AWAY = f"{DOMAIN}_everyone_away"
EVENT_FIRST_PERSON_HOME = f"{DOMAIN}_first_home"
EVENT_SPEED_ALERT = f"{DOMAIN}_speed_alert"
EVENT_CRASH_DETECTED = f"{DOMAIN}_crash_detected"
EVENT_LOW_BATTERY = f"{DOMAIN}_low_battery"
EVENT_SOS_TRIGGERED = f"{DOMAIN}_sos"
EVENT_ZONE_SUGGESTED = f"{DOMAIN}_zone_suggested"
EVENT_LOCATION_UPDATED = f"{DOMAIN}_location_updated"

# Alert severities
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

# Zone icons
ZONE_ICONS = [
    "mdi:home",
    "mdi:office-building",
    "mdi:school",
    "mdi:cart",
    "mdi:hospital-building",
    "mdi:church",
    "mdi:gas-station",
    "mdi:food",
    "mdi:coffee",
    "mdi:dumbbell",
    "mdi:hospital-box",
    "mdi:book",
    "mdi:theater",
    "mdi:stadium",
    "mdi:account-multiple",
    "mdi:map-marker"
]

# Speed thresholds
SPEED_STOPPED = 1  # mph
SPEED_WALKING = 5  # mph
SPEED_RUNNING = 10  # mph
SPEED_VEHICLE_MIN = 15  # mph

# Distance thresholds
DISTANCE_VERY_CLOSE = 0.1  # miles
DISTANCE_CLOSE = 0.5  # miles
DISTANCE_NEARBY = 1.0  # miles
DISTANCE_FAR = 5.0  # miles

# Time constants
QUIET_HOURS_START = 22  # 10 PM
QUIET_HOURS_END = 7    # 7 AM
CHECKIN_TIMEOUT = 300  # seconds (5 minutes)

# Crash detection
CRASH_DETECTION_THRESHOLD_G_FORCE = 2.5  # G-forces
CRASH_DETECTION_SUDDEN_STOP_MPH = 30  # mph decrease in short time

# Zone detection
ZONE_HYSTERESIS_FACTOR = 1.1  # 10% buffer to prevent flip-flopping
MIN_ZONE_DWELL_TIME = 60  # seconds before confirming zone entry

# AI/LLM features
AI_FEATURE_ARRIVAL_PREDICTION = "arrival_prediction"
AI_FEATURE_PATTERN_RECOGNITION = "pattern_recognition"
AI_FEATURE_ANOMALY_DETECTION = "anomaly_detection"
AI_FEATURE_SMART_NOTIFICATIONS = "smart_notifications"

# Configuration keys
CONF_PEOPLE = "people"
CONF_TRACKING_METHOD = "tracking_method"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_HISTORY_RETENTION = "history_retention"
CONF_SAFETY_FEATURES = "safety_features"
CONF_CRASH_DETECTION = "crash_detection_enabled"
CONF_SPEED_ALERTS = "speed_alerts_enabled"
CONF_LOW_BATTERY_ALERTS = "low_battery_alerts_enabled"
CONF_ZONE_MANAGEMENT = "zone_management"
CONF_HOME_ZONE = "home_zone"
CONF_USE_HA_ZONES = "use_ha_zones"
CONF_ZONE_NOTIFICATIONS = "zone_notifications_enabled"
CONF_ZONE_AUTO_SUGGEST = "zone_auto_suggest_enabled"
CONF_AI_FEATURES = "ai_features_enabled"
CONF_AI_FEATURES_LIST = "ai_features_list"
CONF_FIRE_EVENTS = "fire_events"
CONF_INTEGRATION_OPTIONS = "integration_options"

# Person configuration keys
CONF_PERSON_ID = "person_id"
CONF_PERSON_NAME = "name"
CONF_DEVICE_TRACKER = "device_tracker"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_ACTIVITY_SENSOR = "activity_sensor"
CONF_BATTERY_SENSOR = "battery_sensor"
CONF_AVATAR = "avatar"
CONF_PRIVACY_MODE = "privacy_mode"
CONF_ENABLE_NOTIFICATIONS = "enable_notifications"
CONF_SPEED_WARNING_THRESHOLD = "speed_warning_threshold"
CONF_SPEED_EXCESSIVE_THRESHOLD = "speed_excessive_threshold"
CONF_BATTERY_ALERT_THRESHOLD = "battery_alert_threshold"
CONF_WORK_LOCATION = "work_location"

# Attribute keys
ATTR_PERSON_ID = "person_id"
ATTR_PERSON_NAME = "person_name"
ATTR_ZONE_ID = "zone_id"
ATTR_ZONE_NAME = "zone_name"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_SPEED = "speed"
ATTR_BATTERY = "battery"
ATTR_ACTIVITY = "activity"
ATTR_DISTANCE = "distance"
ATTR_TIMESTAMP = "timestamp"
ATTR_CONFIDENCE = "confidence"
ATTR_OCCUPANTS = "occupants"
ATTR_LAST_UPDATE = "last_update"
ATTR_PRIVACY_MODE = "privacy_mode"
ATTR_TRACKING_PAUSED = "tracking_paused"