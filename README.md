# SOPHIA Presence

<p align="center">
  <img src="https://raw.githubusercontent.com/williasj/ha-sophia-presence/main/images/sophia_logo.png" alt="SOPHIA Logo" width="200"/>
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS Custom"/></a>
  <a href="https://github.com/williasj/ha-sophia-presence/releases"><img src="https://img.shields.io/github/v/release/williasj/ha-sophia-presence" alt="Release"/></a>
  <a href="https://github.com/williasj/ha-sophia-presence"><img src="https://img.shields.io/badge/HA%20Minimum-2024.4.0-blue.svg" alt="HA Minimum"/></a>
  <a href="https://polyformproject.org/licenses/noncommercial/1.0.0"><img src="https://img.shields.io/badge/License-PolyForm%20NC-green.svg" alt="License"/></a>
</p>

AI-powered family location tracking for Home Assistant. Part of the SOPHIA ecosystem.

SOPHIA Presence tracks family members in real time using HA device trackers, manages geofence zones, sends contextual notifications, and uses a local LLM to predict arrivals, detect anomalies, and craft intelligent alerts — all running locally with no cloud dependency.

---

## Features

- **Real-time location tracking** via Home Assistant Companion App or any device_tracker entity
- **Geofence zones** with arrival and departure notifications
- **Per-person device trackers** visible on the Home Assistant map
- **Automatic high-accuracy GPS** — enables when away from known zones, conserves battery at home
- **Trip tracking** — records distance, average speed, top speed, and duration for every trip
- **Safety alerts** — crash detection (sudden stop from speed), speed threshold warnings, low battery alerts
- **Privacy controls** — per-person privacy mode and tracking pause switches
- **Zone creation** — create HA zones from a person's current GPS position from the dashboard
- **AI-powered features** (optional, requires SOPHIA Core LLM):
  - Contextual zone arrival/departure notifications written by the LLM
  - ETA prediction mid-trip using stored trip history
  - Anomaly detection — flags unusual patterns vs learned routine (once per occurrence)
  - Daily presence briefing on demand
  - Zone auto-naming suggestions for unknown dwell locations
  - RAG-backed pattern storage (Qdrant + TEI)
- **SOPHIA Core integration** — fires presence events consumed by SOPHIA Climate and other modules
- **Auto-generated dashboard** injected into SOPHIA Core's module registry

---

## Requirements

- [SOPHIA Core](https://github.com/williasj/ha-sophia-core) installed and configured
- Home Assistant 2024.4.0 or later
- Home Assistant Companion App on tracked devices (recommended)
- For AI features: Ollama, Qdrant, and TEI configured in SOPHIA Core

---

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > three-dot menu > **Custom repositories**
3. Add `https://github.com/williasj/ha-sophia-presence` as an **Integration**
4. Find **SOPHIA Presence** in HACS and install it
5. Restart Home Assistant
6. Go to **Settings** > **Devices & Services** > **Add Integration** > search **SOPHIA Presence**

### Manual

Copy `custom_components/sophia_presence/` into your HA config `custom_components/` directory and restart.

---

## Configuration

SOPHIA Presence uses a 7-step guided setup wizard:

1. **Welcome** — confirms SOPHIA Core is present
2. **Tracking Method** — choose Companion App, existing device_tracker, GPS API, or Network
3. **Add People** — select HA Person entities; name and avatar auto-populate; supports adding multiple people
4. **Safety Features** — crash detection, speed warning/excessive thresholds, low battery alerts
5. **Zone Management** — home zone, HA zone integration, zone notifications, auto-suggest
6. **Advanced Settings** — update interval, history retention, AI features toggle
7. **Integration Options** — enable/disable event firing for other SOPHIA modules

People can be added, edited (notify service override, sensors, privacy), or removed at any time via **Options** without reconfiguring from scratch.

---

## Entities Created

For each tracked person:
- `device_tracker.<person_id>` — GPS tracker shown on HA map
- `sensor.sophia_presence_<person_id>_location` — current zone name
- `sensor.sophia_presence_<person_id>_activity` — driving, walking, stationary, etc.
- `sensor.sophia_presence_<person_id>_battery` — device battery level
- `sensor.sophia_presence_<person_id>_speed` — current speed in mph
- `sensor.sophia_presence_<person_id>_distance_from_home` — miles from home zone
- `sensor.sophia_presence_<person_id>_high_accuracy_gps` — high accuracy mode state
- `switch.sophia_presence_<person_id>_tracking` — pause/resume tracking
- `switch.sophia_presence_<person_id>_privacy_mode` — hide location
- `switch.sophia_presence_<person_id>_notifications` — per-person notification toggle
- `text.sophia_presence_<person_id>_new_zone_name` — zone name input for dashboard zone creation

Global sensors and switches:
- `sensor.sophia_presence_status`, `_people_home`, `_people_away`, `_total_people`, `_event_log`
- `switch.sophia_presence_system`, `_crash_detection`, `_speed_alerts`, `_low_battery_alerts`, `_quiet_hours`

---

## Services

| Service | Description |
|---|---|
| `sophia_presence.update_location` | Manually update a person's GPS coordinates |
| `sophia_presence.add_person` | Prompt to reconfigure and add a person |
| `sophia_presence.remove_person` | Prompt to reconfigure and remove a person |
| `sophia_presence.request_checkin` | Send a check-in request notification |
| `sophia_presence.trigger_sos` | Fire SOS alert to all family members |
| `sophia_presence.get_daily_summary` | Generate AI daily presence briefing |
| `sophia_presence.add_zone_from_location` | Create an HA zone at a person's current position |

---

## Notify Service Override

SOPHIA derives each person's mobile notify service from their device_tracker entity name. If your HA mobile app registration name differs from the tracker, set the **Notify Service** override per person in Options. For example, if the notify service is `notify.mobile_app_your_device_name`, enter `your_device_name` in the override field.

---

## SOPHIA Ecosystem

| Module | Description | Status |
|---|---|---|
| [SOPHIA Core](https://github.com/williasj/ha-sophia-core) | Shared LLM client, module registry, dashboard | Released |
| [SOPHIA Climate](https://github.com/williasj/ha-sophia-climate) | AI-powered multi-zone HVAC control | Released |
| [SOPHIA Systems](https://github.com/williasj/ha-sophia-systems) | Hardware telemetry (TrueNAS, GPU, BMC) | Released |
| **SOPHIA Presence** | Family location tracking | **This module** |

---

## Support

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/sophiadev)

If SOPHIA Presence saves your family a worry or two, consider buying a coffee.

---

## License

PolyForm Noncommercial License 1.0.0 — free for personal and home use, not for commercial products or services.

Copyright Scott Williams — [Scott.J.Williams14@gmail.com](mailto:Scott.J.Williams14@gmail.com) — [github.com/williasj](https://github.com/williasj)
