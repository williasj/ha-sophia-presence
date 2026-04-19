# -*- coding: utf-8 -*-
"""
SOPHIA Presence AI - LLM intelligence layer for sophia_presence.

Features implemented:
  1. Smart notification crafting        - contextual zone arrival/departure messages
  2. Context-aware SOS composition      - rich emergency alert with all available data
  3. Arrival time prediction            - ETA during active trips using trip history RAG
  4. AI-controlled high accuracy GPS    - nuanced GPS decisions on zone transitions only
  5. Zone auto-naming                   - suggest name + icon for unknown dwell locations
  6. Daily presence briefing            - natural language summary of the day
  7. Anomaly detection                  - flag unusual patterns vs stored history

RAG collections (auto-created):
  sophia_presence_patterns  - zone visit events, daily routine patterns per person
  sophia_presence_zones     - named location context and visit frequency
  sophia_presence_trips     - completed trip records for ETA and anomaly context

All methods fall back to returning None / False gracefully if the LLM or
Qdrant is unavailable so the coordinator can use static fallbacks.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

COLLECTION_PATTERNS = "sophia_presence_patterns"
COLLECTION_ZONES = "sophia_presence_zones"
COLLECTION_TRIPS = "sophia_presence_trips"

REQUIRED_COLLECTIONS = [COLLECTION_PATTERNS, COLLECTION_ZONES, COLLECTION_TRIPS]

# Minimum trips before anomaly detection is meaningful
MIN_TRIP_HISTORY = 5

# Minimum time (seconds) between anomaly checks per person
ANOMALY_CHECK_INTERVAL = 1800


class PresenceAI:
    """AI intelligence layer for SOPHIA Presence.

    All interaction with Qdrant and TEI flows through the sophia_core
    SophiaLLMClient public RAG API (rag_ensure_collection, rag_upsert,
    rag_search, rag_embed, rag_purge_older_than). This module does not
    import aiohttp, read qdrant_url/tei_url, or talk to those services
    directly - that responsibility belongs entirely to sophia_core.
    """

    def __init__(self, llm_client, coordinator) -> None:
        self._llm = llm_client
        self._coordinator = coordinator

        # Cache last high-accuracy GPS AI decision per person: {person_id: (decision, datetime)}
        self._last_ha_decision: Dict[str, Tuple[bool, datetime]] = {}

        # Track last anomaly check timestamp per person
        self._last_anomaly_check: Dict[str, datetime] = {}

        _LOGGER.info("PresenceAI initialized (RAG I/O delegated to sophia_core)")

    # =========================================================================
    # Collection Management (via sophia_core public RAG API)
    # =========================================================================

    async def ensure_collections(self) -> None:
        """Create the three presence RAG collections via sophia_core."""
        for collection in REQUIRED_COLLECTIONS:
            try:
                await self._llm.rag_ensure_collection(collection)
            except Exception as err:
                _LOGGER.warning(
                    "PresenceAI: ensure_collections error for '%s': %s",
                    collection, err,
                )

    async def _store_document(
        self,
        collection: str,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None,
    ) -> bool:
        """Thin wrapper around core's rag_upsert to preserve existing call sites."""
        try:
            return await self._llm.rag_upsert(collection, text, metadata, doc_id)
        except Exception as err:
            _LOGGER.warning(
                "PresenceAI: _store_document failed for '%s': %s", collection, err
            )
            return False

    # =========================================================================
    # Feature 1: Smart Notification Crafting
    # =========================================================================

    async def craft_zone_notification(
        self,
        person_name: str,
        zone: str,
        action: str,
        trip_data: Optional[Dict] = None,
        all_people_data: Optional[Dict] = None,
    ) -> Optional[str]:
        """Generate a contextual, friendly zone notification message.

        Returns the message string, or None if AI is unavailable (caller uses
        the static fallback in that case).
        """
        zone_name = zone.replace("_", " ").title()
        time_str = datetime.now().strftime("%I:%M %p")
        day_str = datetime.now().strftime("%A")
        hour = datetime.now().hour

        if 5 <= hour < 12:
            time_context = "morning"
        elif 12 <= hour < 17:
            time_context = "afternoon"
        elif 17 <= hour < 21:
            time_context = "evening"
        else:
            time_context = "night"

        # Who else is home
        home_people = []
        if all_people_data:
            for pdata in all_people_data.values():
                if (
                    pdata.get("available")
                    and pdata["location"]["zone"] == "home"
                    and pdata["name"] != person_name
                ):
                    home_people.append(pdata["name"])

        if home_people:
            home_context = f"Currently home: {', '.join(home_people)}."
        else:
            home_context = "No one else is home right now."

        # Trip stats if available
        trip_context = ""
        if trip_data:
            dist = trip_data.get("total_distance", 0)
            max_spd = trip_data.get("max_speed", 0)
            start = trip_data.get("start_time")
            if start:
                try:
                    elapsed_mins = (
                        datetime.now() - datetime.fromisoformat(str(start))
                    ).total_seconds() / 60
                    trip_context = (
                        f"Trip: {dist:.1f} miles over {elapsed_mins:.0f} minutes, "
                        f"top speed {max_spd:.0f} mph."
                    )
                except Exception:
                    trip_context = f"Trip: {dist:.1f} miles."

        prompt = (
            f"Generate a brief, friendly home automation notification (1-2 sentences max).\n"
            f"Situation: {person_name} has {action} {zone_name} at {time_str} on {day_str} {time_context}.\n"
            f"{home_context}\n"
            f"{trip_context}\n"
            f"Requirements:\n"
            f"- Casual and warm tone, like a family group chat message\n"
            f"- Include relevant details naturally (time, trip info when available)\n"
            f"- Vary phrasing so it does not feel robotic\n"
            f"- Plain text only, no markdown, no emoji in the text\n"
            f"Output ONLY the notification message, nothing else."
        )

        try:
            result = await self._llm.generate(
                prompt=prompt,
                module_id="sophia_presence",
                use_rag=True,
                rag_collection=COLLECTION_PATTERNS,
                search_query=f"{person_name} {zone} {action}",
            )
            if result and result.get("response"):
                msg = result["response"].strip()
                if 10 < len(msg) < 300 and "Requirements:" not in msg:
                    return msg
        except Exception as err:
            _LOGGER.debug("PresenceAI: craft_zone_notification failed: %s", err)

        return None

    # =========================================================================
    # Feature 2: Context-Aware SOS Composition
    # =========================================================================

    async def craft_sos_message(
        self,
        person_data: Dict,
        all_people_data: Optional[Dict] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Generate an SOS alert title and message body.

        Returns (title, body) tuple, or (None, None) on failure.
        """
        person_name = person_data.get("name", "Unknown")
        location = person_data.get("location", {})
        zone_name = location.get("zone", "unknown").replace("_", " ").title()
        lat = location.get("latitude", "unknown")
        lon = location.get("longitude", "unknown")
        speed = person_data.get("speed", 0)
        activity = person_data.get("activity", "unknown").replace("_", " ")
        battery = person_data.get("battery")
        dist_from_home = person_data.get("distance_from_home", 0)
        time_str = datetime.now().strftime("%I:%M %p")
        battery_str = f"{battery}%" if battery is not None else "unknown"

        # Find nearest available family member
        nearest = "unknown"
        nearest_dist = float("inf")
        if all_people_data:
            for pdata in all_people_data.values():
                if pdata.get("available") and pdata["name"] != person_name:
                    d = pdata.get("distance_from_home", 999)
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest = pdata["name"]

        prompt = (
            f"Compose an urgent SOS emergency alert notification.\n"
            f"Person in distress: {person_name}\n"
            f"Time: {time_str}\n"
            f"Location: {zone_name}\n"
            f"Coordinates: {lat}, {lon}\n"
            f"Distance from home: {dist_from_home:.1f} miles\n"
            f"Speed: {speed:.0f} mph\n"
            f"Activity: {activity}\n"
            f"Battery: {battery_str}\n"
            f"Nearest family member: {nearest}\n"
            f"\n"
            f"Write a 3-5 line emergency alert message. Be urgent but clear.\n"
            f"Include the exact coordinates and all relevant context.\n"
            f"Plain text only, no markdown.\n"
            f"Output ONLY the message body, nothing else."
        )

        try:
            result = await self._llm.generate(prompt=prompt, module_id="sophia_presence")
            if result and result.get("response"):
                msg = result["response"].strip()
                if len(msg) > 20:
                    return f"SOS ALERT: {person_name}", msg
        except Exception as err:
            _LOGGER.debug("PresenceAI: craft_sos_message failed: %s", err)

        return None, None

    # =========================================================================
    # Feature 3: Arrival Time Prediction
    # =========================================================================

    async def predict_arrival(
        self,
        trip_data: Dict,
        person_data: Dict,
        destination_hint: str = "home",
    ) -> Optional[str]:
        """Predict arrival time for an active trip.

        Uses RAG trip history to improve accuracy over pure calculation.
        Returns a short sentence like 'Should arrive around 5:45 PM', or None.
        """
        person_name = trip_data.get("person_name", "Unknown")
        origin = trip_data.get("origin_zone", "unknown").replace("_", " ").title()
        distance_so_far = trip_data.get("total_distance", 0)
        max_speed = trip_data.get("max_speed", 0)
        speed_samples = trip_data.get("speed_samples", [])
        current_speed = person_data.get("speed", 0)

        start_time = trip_data.get("start_time")
        elapsed_mins = 0.0
        if start_time:
            try:
                elapsed_mins = (
                    datetime.now() - datetime.fromisoformat(str(start_time))
                ).total_seconds() / 60
            except Exception:
                pass

        avg_speed = (
            sum(speed_samples) / len(speed_samples) if speed_samples else current_speed
        )
        day_str = datetime.now().strftime("%A")
        time_str = datetime.now().strftime("%I:%M %p")

        prompt = (
            f"Estimate arrival time for a trip in progress.\n"
            f"Person: {person_name}\n"
            f"Left from: {origin} heading to: {destination_hint}\n"
            f"Departed {elapsed_mins:.0f} minutes ago at {time_str} on {day_str}\n"
            f"Distance covered so far: {distance_so_far:.1f} miles\n"
            f"Current speed: {current_speed:.0f} mph\n"
            f"Average speed so far: {avg_speed:.0f} mph\n"
            f"Top speed so far: {max_speed:.0f} mph\n"
            f"\n"
            f"Use historical trip context if available to improve the estimate.\n"
            f"Respond with ONE sentence only, e.g. 'Should arrive around 5:45 PM'.\n"
            f"Plain text. Output ONLY the estimate sentence."
        )

        try:
            result = await self._llm.generate(
                prompt=prompt,
                module_id="sophia_presence",
                use_rag=True,
                rag_collection=COLLECTION_TRIPS,
                search_query=f"{person_name} trip {origin} {destination_hint} {day_str}",
            )
            if result and result.get("response"):
                resp = result["response"].strip()
                if 5 < len(resp) < 200:
                    return resp
        except Exception as err:
            _LOGGER.debug("PresenceAI: predict_arrival failed: %s", err)

        return None

    # =========================================================================
    # Feature 4: AI-Controlled High Accuracy GPS
    # =========================================================================

    async def should_enable_high_accuracy(
        self,
        person_id: str,
        person_data: Dict,
        current_zone: str,
        last_zone: Optional[str],
        zone_just_changed: bool,
    ) -> bool:
        """Nuanced GPS accuracy decision using AI context.

        Only queries the LLM when a zone transition just occurred to avoid
        adding latency to every 60-second poll cycle.

        Falls back to simple not_home == True logic if AI is unavailable.
        """
        simple_decision = current_zone == "not_home"

        if not zone_just_changed:
            # Return cached decision, no LLM call
            cached = self._last_ha_decision.get(person_id)
            if cached:
                return cached[0]
            return simple_decision

        person_name = person_data.get("name", person_id)
        speed = person_data.get("speed", 0)
        activity = person_data.get("activity", "unknown").replace("_", " ")
        battery = person_data.get("battery")
        dist_from_home = person_data.get("distance_from_home", 0)
        time_str = datetime.now().strftime("%I:%M %p")
        day_str = datetime.now().strftime("%A")
        battery_str = f"{battery}%" if battery is not None else "unknown"

        prompt = (
            f"Decide whether to enable high accuracy GPS for {person_name}.\n"
            f"Zone transition: {last_zone or 'unknown'} -> {current_zone}\n"
            f"Speed: {speed:.0f} mph, Activity: {activity}\n"
            f"Battery: {battery_str}, Distance from home: {dist_from_home:.1f} miles\n"
            f"Time: {time_str} on {day_str}\n"
            f"\n"
            f"High accuracy GPS gives precise location but consumes more battery.\n"
            f"Enable when: person is in transit, near zone boundaries, speed is changing, "
            f"zone is unknown, or context safety matters.\n"
            f"Disable when: person is settled in a known zone, battery is critically low, "
            f"or location has been stable.\n"
            f"\n"
            f"Respond with ONLY 'YES' or 'NO' followed by a one-line reason.\n"
            f"Example: YES - Person just left home and is in transit"
        )

        try:
            result = await self._llm.generate(
                prompt=prompt,
                module_id="sophia_presence",
                use_rag=True,
                rag_collection=COLLECTION_PATTERNS,
                search_query=f"{person_name} GPS accuracy pattern {current_zone}",
            )
            if result and result.get("response"):
                resp = result["response"].strip()
                decision = resp.upper().startswith("YES")
                self._last_ha_decision[person_id] = (decision, datetime.now())
                _LOGGER.debug(
                    "PresenceAI: high_accuracy %s -> %s | %s",
                    person_name,
                    "ON" if decision else "OFF",
                    resp[:100],
                )
                return decision
        except Exception as err:
            _LOGGER.debug("PresenceAI: should_enable_high_accuracy failed: %s", err)

        self._last_ha_decision[person_id] = (simple_decision, datetime.now())
        return simple_decision

    # =========================================================================
    # Feature 5: Zone Auto-Naming
    # =========================================================================

    async def suggest_zone_name(
        self,
        latitude: float,
        longitude: float,
        dwell_time_minutes: float,
        person_name: str,
    ) -> Optional[Dict[str, str]]:
        """Suggest a zone name and MDI icon for an unrecognized dwell location.

        Uses web search to try to identify the actual business or place.
        Returns dict with 'name', 'icon', 'reason', or None on failure.
        """
        time_str = datetime.now().strftime("%I:%M %p")
        day_str = datetime.now().strftime("%A")

        prompt = (
            f"Suggest a Home Assistant zone name for an unrecognized location.\n"
            f"Person: {person_name} spent {dwell_time_minutes:.0f} minutes here.\n"
            f"Coordinates: {latitude:.5f}, {longitude:.5f}\n"
            f"Time of visit: {time_str} on {day_str}\n"
            f"\n"
            f"If web search results are available, use them to identify the location.\n"
            f"Otherwise infer from time of day and dwell duration.\n"
            f"\n"
            f"Respond with a JSON object ONLY (no markdown fences):\n"
            f"{{\"name\": \"Short Zone Name\", \"icon\": \"mdi:icon-name\", "
            f"\"reason\": \"One line explanation\"}}\n"
            f"\n"
            f"Use common MDI icons: mdi:store, mdi:school, mdi:dumbbell, mdi:food,\n"
            f"mdi:church, mdi:hospital, mdi:gas-station, mdi:car-wash,\n"
            f"mdi:office-building, mdi:home-variant, mdi:soccer-field, mdi:library\n"
            f"Output ONLY the JSON object."
        )

        try:
            result = await self._llm.generate(
                prompt=prompt,
                module_id="sophia_presence",
                use_web_search=True,
                search_query=f"location {latitude:.4f} {longitude:.4f}",
            )
            if result and result.get("response"):
                resp = result["response"].strip()
                resp = resp.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(resp)
                if "name" in parsed and "icon" in parsed:
                    return parsed
        except Exception as err:
            _LOGGER.debug("PresenceAI: suggest_zone_name failed: %s", err)

        return None

    # =========================================================================
    # Feature 6: Daily Presence Briefing
    # =========================================================================

    async def generate_daily_summary(
        self,
        people_data: Dict,
        trip_history: List[Dict],
        statistics: Dict,
    ) -> Optional[str]:
        """Generate a natural language summary of today's presence activity."""
        today = datetime.now().strftime("%A, %B %d")
        today_prefix = datetime.now().strftime("%Y-%m-%d")

        todays_trips = [
            t for t in trip_history if t.get("end_time", "").startswith(today_prefix)
        ]

        people_lines = []
        for pdata in people_data.values():
            if pdata.get("available"):
                zone = pdata["location"]["zone"].replace("_", " ").title()
                activity = pdata.get("activity", "unknown").replace("_", " ")
                people_lines.append(f"  {pdata['name']}: {zone} ({activity})")

        trip_lines = []
        for trip in todays_trips[-10:]:
            origin = trip.get("origin_zone", "?").replace("_", " ").title()
            dest = trip.get("destination_zone", "?").replace("_", " ").title()
            dist = trip.get("distance_miles", 0)
            duration = trip.get("duration_minutes", 0)
            person = trip.get("person_name", "?")
            trip_lines.append(
                f"  {person}: {origin} to {dest}, {dist:.1f} mi, {duration:.0f} min"
            )

        people_block = "\n".join(people_lines) if people_lines else "  No data available"
        trips_block = "\n".join(trip_lines) if trip_lines else "  No trips recorded today"

        prompt = (
            f"Generate a friendly daily family presence briefing for {today}.\n"
            f"\n"
            f"Current status:\n{people_block}\n"
            f"\n"
            f"Today's trips:\n{trips_block}\n"
            f"\n"
            f"Stats: {statistics.get('total_people', 0)} tracked, "
            f"{statistics.get('people_home', 0)} home, "
            f"{statistics.get('people_away', 0)} away.\n"
            f"\n"
            f"Write a 3-5 sentence conversational summary of the day.\n"
            f"Note any patterns, activity highlights, or notable events.\n"
            f"Warm and friendly tone. Plain text. No markdown. No bullet points.\n"
            f"Output ONLY the summary."
        )

        try:
            result = await self._llm.generate(
                prompt=prompt,
                module_id="sophia_presence",
                use_rag=True,
                rag_collection=COLLECTION_PATTERNS,
                search_query="daily family routine home away pattern",
            )
            if result and result.get("response"):
                return result["response"].strip()
        except Exception as err:
            _LOGGER.debug("PresenceAI: generate_daily_summary failed: %s", err)

        return None

    # =========================================================================
    # Feature 7: Anomaly Detection
    # =========================================================================

    async def check_for_anomalies(
        self,
        person_id: str,
        person_data: Dict,
        trip_history: List[Dict],
        work_location: str = "",
    ) -> List[Dict]:
        """Compare current state against historical patterns and flag anomalies.

        Returns a list of anomaly dicts: [{description, severity, person, person_id, fingerprint}]
        Returns empty list if no anomalies, AI unavailable, or throttled.
        """
        last_check = self._last_anomaly_check.get(person_id)
        if last_check and (datetime.now() - last_check).total_seconds() < ANOMALY_CHECK_INTERVAL:
            return []

        person_name = person_data.get("name", person_id)
        current_zone = person_data["location"]["zone"].replace("_", " ").title()
        speed = person_data.get("speed", 0)
        activity = person_data.get("activity", "unknown").replace("_", " ")
        time_str = datetime.now().strftime("%I:%M %p")
        day_str = datetime.now().strftime("%A")
        battery = person_data.get("battery")
        dist_from_home = person_data.get("distance_from_home", 0)
        battery_str = f"{battery}%" if battery is not None else "unknown"

        person_trips = [t for t in trip_history if t.get("person_id") == person_id]
        if len(person_trips) < MIN_TRIP_HISTORY:
            _LOGGER.debug(
                "PresenceAI: not enough trip history for %s (%d trips, need %d)",
                person_name, len(person_trips), MIN_TRIP_HISTORY,
            )
            return []

        trip_lines = []
        for t in person_trips[-10:]:
            origin = t.get("origin_zone", "?")
            dest = t.get("destination_zone", "?")
            start = t.get("start_time", "")[:10]
            trip_lines.append(f"  {start}: {origin} -> {dest}")

        trips_block = "\n".join(trip_lines)

        work_context = (
            f"This person's known workplace is '{work_location}'. "
            f"Presence at or near '{work_location}' during work hours is NORMAL and must NOT be flagged.\n"
            if work_location else ""
        )

        prompt = (
            f"Analyze location data for anomalies for {person_name}.\n"
            f"Current state: {current_zone}, {activity}, {speed:.0f} mph, "
            f"{dist_from_home:.1f} miles from home, battery {battery_str}\n"
            f"Time: {time_str} on {day_str}\n"
            f"{work_context}"
            f"\n"
            f"Recent trip history (last 10 of {len(person_trips)} trips):\n"
            f"{trips_block}\n"
            f"\n"
            f"Flag ONLY genuine anomalies: unexpected absence from usual location at this "
            f"time, unusual travel route or destination, concerning patterns, or "
            f"unexplained extended stays in unfamiliar places.\n"
            f"Do NOT flag normal day-to-day variation or presence at known work location.\n"
            f"\n"
            f"If no anomalies: respond with exactly NONE\n"
            f"If anomalies exist, respond with a JSON array (no markdown fences):\n"
            f"[{{\"description\": \"brief description\", \"severity\": \"low|medium|high\"}}]\n"
            f"Output ONLY 'NONE' or the JSON array."
        )

        try:
            result = await self._llm.generate(
                prompt=prompt,
                module_id="sophia_presence",
                use_rag=True,
                rag_collection=COLLECTION_PATTERNS,
                search_query=f"{person_name} normal routine {day_str}",
            )
            self._last_anomaly_check[person_id] = datetime.now()

            if result and result.get("response"):
                resp = result["response"].strip()
                if resp.upper() == "NONE":
                    return []
                resp = resp.replace("```json", "").replace("```", "").strip()
                anomalies = json.loads(resp)
                if isinstance(anomalies, list):
                    for a in anomalies:
                        a["person"] = person_name
                        a["person_id"] = person_id
                        # Fingerprint: person + zone + first 60 chars of description
                        a["fingerprint"] = f"{person_id}|{current_zone}|{a.get('description', '')[:60]}"
                    return anomalies
        except Exception as err:
            _LOGGER.debug("PresenceAI: check_for_anomalies failed for %s: %s", person_name, err)

        return []

    # =========================================================================
    # RAG Storage Helpers
    # =========================================================================

    async def store_trip(self, trip_record: Dict) -> None:
        """Embed a completed trip record and store it in sophia_presence_trips."""
        person = trip_record.get("person_name", "unknown")
        origin = trip_record.get("origin_zone", "unknown")
        dest = trip_record.get("destination_zone", "unknown")
        dist = trip_record.get("distance_miles", 0)
        duration = trip_record.get("duration_minutes", 0)
        avg_spd = trip_record.get("avg_speed_mph", 0)
        max_spd = trip_record.get("max_speed_mph", 0)
        start_time = trip_record.get("start_time", "")

        day_context = ""
        try:
            dt = datetime.fromisoformat(start_time)
            day_context = f"{dt.strftime('%A')} at {dt.strftime('%I:%M %p')}"
        except Exception:
            day_context = start_time[:16] if start_time else "unknown time"

        text = (
            f"Trip by {person} on {day_context}: from {origin} to {dest}. "
            f"Distance: {dist:.1f} miles. Duration: {duration:.0f} minutes. "
            f"Average speed: {avg_spd:.0f} mph. Top speed: {max_spd:.0f} mph."
        )

        metadata = {
            "person_id": trip_record.get("person_id"),
            "person_name": person,
            "origin": origin,
            "destination": dest,
            "start_time": start_time,
            "type": "trip_record",
        }

        safe_time = start_time[:19].replace(":", "-").replace(" ", "T") if start_time else "unknown"
        doc_id = f"trip_{trip_record.get('person_id', 'x')}_{safe_time}"
        await self._store_document(COLLECTION_TRIPS, text, metadata, doc_id)

    async def store_zone_visit(
        self,
        person_name: str,
        zone: str,
        action: str,
        coords: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Store a zone visit event for pattern learning."""
        time_str = datetime.now().strftime("%I:%M %p")
        day_str = datetime.now().strftime("%A")
        date_str = datetime.now().strftime("%Y-%m-%d")
        zone_name = zone.replace("_", " ").title()

        coord_str = f" at ({coords[0]:.5f}, {coords[1]:.5f})" if coords else ""

        text = (
            f"{person_name} {action} {zone_name}{coord_str} on {day_str} at {time_str}."
        )

        metadata = {
            "person_name": person_name,
            "zone": zone,
            "action": action,
            "day_of_week": day_str,
            "time": time_str,
            "date": date_str,
            "type": "zone_visit",
        }

        safe_time = time_str.replace(":", "").replace(" ", "")
        doc_id = f"visit_{person_name}_{zone}_{date_str}_{safe_time}"
        await self._store_document(COLLECTION_PATTERNS, text, metadata, doc_id)

    async def store_zone_knowledge(
        self,
        zone_id: str,
        zone_name: str,
        coords: Tuple[float, float],
        context: str,
    ) -> None:
        """Store identified zone context (from auto-naming) in sophia_presence_zones."""
        text = (
            f"Zone '{zone_name}' (id: {zone_id}) at ({coords[0]:.5f}, {coords[1]:.5f}). "
            f"Context: {context}"
        )

        metadata = {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "latitude": coords[0],
            "longitude": coords[1],
            "type": "zone_knowledge",
        }

        doc_id = f"zone_{zone_id}"
        await self._store_document(COLLECTION_ZONES, text, metadata, doc_id)