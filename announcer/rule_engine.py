"""
Rule engine for evaluating aircraft dataref triggers and playing cabin announcements.
Handles edge detection, cooldowns, once-per-flight rules, delays, and flight phase state.
"""

import time
import threading
import logging
from announcer.pack_manager import SOUND_ALIASES

logger = logging.getLogger("CabinAnnouncer.RuleEngine")

DEPARTURE_SOUNDS = {
    "boardingwelcome",
    "boardingwelcomepilot",
    "boardingmusic",
    "boardingcomplete",
    "armdoors",
    "presafetybriefing",
    "safetybriefing",
    "cabindimtakeoff",
    "crewseatstakeoff",
    "callcabinsecuretakeoff",
    "cabinready",
    "aftertakeoff"
}

ARRIVAL_SOUNDS = {
    "descentseatbelts",
    "descent",
    "topofdescentpilot",
    "callcabinsecurelanding",
    "crewseatslanding",
    "afterlanding",
    "disarmdoors",
    "disembarkstarted",
    "deboarding"
}

class RuleEngine:
    def __init__(self, udp_client, pack_manager, audio_engine):
        self.udp = udp_client
        self.packs = pack_manager
        self.audio = audio_engine

        self.active_config = None
        self.active_airline = "DEFAULT"
        self.auto_triggers_enabled = True

        # State tracking
        self._prev_values = {}
        self._triggered_rules = set()  # rule IDs triggered in current flight
        self._cooldown_expiry = {}    # rule_id -> timestamp when allowed to trigger again
        self._pending_delayed = {}    # rule_id -> (target_time, sound_name, rule_desc)
        self._played_announcements = set()  # sound names that have played in current flight
        self.boarding_started = False       # gate boarding until explicitly started
        self.boarding_completed = False     # tracks boarding completion
        
        # Flight state heuristics
        self.flight_phase = "BOARDING"
        self.state_summary = "At gate - preparing for boarding"
        self._was_airborne = False

        # Cabin Call & Ready Handshake state
        self.cabin_call_ringing = False
        self.cabin_ready_completed = False
        self._last_call_time = 0

        self._running = False
        self._thread = None
        self._callbacks = []  # UI log callbacks

    def set_config(self, config_data):
        """Sets the active aircraft configuration rules and resets triggers."""
        self.active_config = config_data
        self.reset_flight_state()
        logger.info(f"Loaded active config rules: {config_data.get('name', 'Unknown') if config_data else 'None'}")

    def set_airline(self, airline_icao):
        """Sets the active airline sound pack."""
        self.active_airline = airline_icao.strip().upper()
        logger.info(f"Active airline set to: {self.active_airline}")

    def add_log_callback(self, callback):
        """Registers a callback for announcement trigger events."""
        self._callbacks.append(callback)

    def _log_event(self, message):
        logger.info(message)
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    def reset_flight_state(self):
        """Resets triggered rules for a fresh flight."""
        self._triggered_rules.clear()
        self._cooldown_expiry.clear()
        self._pending_delayed.clear()
        self._played_announcements.clear()
        self.boarding_started = False
        self.boarding_completed = False
        self._was_airborne = False
        self.cabin_call_ringing = False
        self.cabin_ready_completed = False
        self.flight_phase = "BOARDING"
        self._log_event("Flight state reset. All announcements armed.")

    def start_boarding(self):
        """Manually starts passenger boarding phase, plays BoardingWelcome, and starts BoardingMusic."""
        self.boarding_started = True
        self.boarding_completed = False
        self.flight_phase = "BOARDING"
        self.state_summary = "Passenger boarding started"
        self._log_event("🛫 [Boarding] Passenger boarding initiated.")

        # 1. Start Boarding Music (if available in pack and not already playing)
        if not self.audio.is_music_playing():
            music_file = self.packs.resolve_sound(self.active_airline, "BoardingMusic")
            if music_file:
                self.audio.play_boarding_music(music_file, loop=True)
                self._record_played_sound("BoardingMusic")
                self._log_event(f"🎵 [Boarding] Playing boarding music ({self.active_airline}).")
            else:
                self._log_event(f"ℹ️ No 'BoardingMusic' audio found for airline {self.active_airline}.")

        # 2. Trigger Welcome Announcement
        return self.trigger_sound_manually("BoardingWelcome")

    def complete_boarding(self):
        """Manually completes passenger boarding phase and triggers BoardingComplete announcement."""
        self.boarding_completed = True
        self.flight_phase = "BOARDING_COMPLETE"
        self.state_summary = "Passenger boarding complete"
        self._log_event("📋 [Boarding] Passenger boarding marked complete.")
        if self.audio.is_music_playing():
            self.audio.stop_music()
            self._log_event("⏹ Stopped boarding music.")
        return self.trigger_sound_manually("BoardingComplete")

    def initiate_cabin_call(self):
        """Cabin crew initiates an interphone call to the cockpit."""
        if self.cabin_ready_completed:
            return
        self.cabin_call_ringing = True
        self._last_call_time = time.time()
        self._log_event("📞 [Cabin Call] Cabin crew calling cockpit (interphone chime)...")

    def answer_cabin_call(self):
        """Flight deck answers the cabin call -> triggers Cabin Ready announcement."""
        self.cabin_call_ringing = False
        self.cabin_ready_completed = True
        self._played_announcements.add("CallCabinSecureTakeoff")
        self._played_announcements.add("CabinReady")
        self._log_event("🎙️ [Flight Deck] Cabin call answered.")

        # Send ToLiss / X-Plane check cabin command to update ECAM
        try:
            self.udp.send_command("AirbusFBW/CheckCabin")
        except Exception:
            pass

        # Play Cabin Ready announcement
        hour = self.get_current_flight_hour()
        sound_file = self.packs.resolve_sound(self.active_airline, "CallCabinSecureTakeoff", time_hour=hour)
        if not sound_file:
            sound_file = self.packs.resolve_sound(self.active_airline, "CabinReady", time_hour=hour)

        if sound_file:
            self.audio.play_announcement(sound_file)
            self._log_event(f"🔔 [Cabin Ready] 'Cabin is secure and ready for departure' -> {self.active_airline}")
        else:
            self._log_event("⚠️ 'CallCabinSecureTakeoff' audio not found in pack.")

    def start(self):
        """Starts background evaluation loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._eval_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops background evaluation loop."""
        self._running = False

    def get_current_flight_hour(self):
        """Returns the current flight hour: prefers in-sim local time from X-Plane, falls back to real wall clock."""
        if self.udp.is_connected():
            sim_time = self.udp.get_value("sim/time/local_time_sec", None)
            if sim_time is not None and sim_time > 0:
                return int(sim_time // 3600) % 24
        from datetime import datetime
        return datetime.now().hour

    def _record_played_sound(self, sound_name):
        self._played_announcements.add(sound_name)
        clean = sound_name.lower()
        self._played_announcements.add(clean)
        for alias in SOUND_ALIASES.get(clean, []):
            self._played_announcements.add(alias)

    def trigger_sound_manually(self, sound_name):
        """Allows manual triggering of any announcement sound."""
        try:
            if sound_name in ("CallCabinSecureTakeoff", "CabinReady"):
                self.answer_cabin_call()
                return True

            hour = self.get_current_flight_hour()
            sound_file = self.packs.resolve_sound(self.active_airline, sound_name, time_hour=hour)
            if not sound_file:
                self._log_event(f"❌ Sound '{sound_name}' not found for airline {self.active_airline}.")
                return False

            if sound_name == "BoardingWelcome":
                self.boarding_started = True

            if sound_name == "BoardingComplete":
                self.boarding_completed = True

            if sound_name == "BoardingMusic":
                if self.audio.is_music_playing():
                    self.audio.stop_music()
                    self._log_event("⏹ Stopped boarding music.")
                    return True
                else:
                    self.audio.play_boarding_music(sound_file)
                    self._record_played_sound(sound_name)
                    self._log_event(f"🎵 Playing boarding music: {self.active_airline}")
                    return True
            else:
                self.audio.play_announcement(sound_file)
                self._record_played_sound(sound_name)
                self._log_event(f"🔊 Playing announcement: {sound_name} ({self.active_airline})")
                return True
        except Exception as e:
            logger.error(f"Error triggering sound '{sound_name}' manually: {e}", exc_info=True)
            self._log_event(f"❌ Error playing '{sound_name}': {e}")
            return False

    def _eval_loop(self):
        """Main loop that ticks 4 times per second to evaluate rules."""
        while self._running:
            try:
                if self.auto_triggers_enabled and self.udp.is_connected() and self.active_config:
                    self._evaluate_tick()
                self._check_delayed_triggers()
            except Exception as e:
                logger.error(f"Error in rule evaluation tick: {e}", exc_info=True)
            time.sleep(0.25)

    def _check_delayed_triggers(self):
        """Fires any pending announcements whose delay timer has expired."""
        now = time.time()
        to_fire = []
        for rule_id, (target_time, sound_name, desc) in list(self._pending_delayed.items()):
            if now >= target_time:
                to_fire.append((rule_id, sound_name, desc))
                del self._pending_delayed[rule_id]

        for rule_id, sound_name, desc in to_fire:
            hour = self.get_current_flight_hour()
            sound_file = self.packs.resolve_sound(self.active_airline, sound_name, time_hour=hour)
            if sound_file:
                self.audio.play_announcement(sound_file)
                self._record_played_sound(sound_name)
                self._log_event(f"🔔 [Auto-Trigger] '{sound_name}' ({desc}) -> {self.active_airline}")
            else:
                self._log_event(f"⚠️ [Auto-Trigger] '{sound_name}' triggered, but no audio file found in pack.")

    def _evaluate_tick(self):
        current_values = self.udp.get_all_values()
        rules = self.active_config.get("rules", [])
        now = time.time()

        # Update flight phase estimation
        onground = current_values.get("sim/flightmodel/failures/onground_any", 1.0) >= 0.5
        gs = current_values.get("sim/flightmodel/position/groundspeed", 0.0)
        alt_agl = current_values.get("sim/flightmodel/position/y_agl", 0.0)
        beacon_raw = current_values.get("sim/cockpit2/switches/beacon_on", current_values.get("AirbusFBW/BeaconLightsOn", 0.0))
        beacon = beacon_raw >= 0.5
        prk_brk_raw = current_values.get("sim/cockpit2/controls/parking_brake_ratio", current_values.get("AirbusFBW/ParkBrake", 0.0))
        prk_brk = prk_brk_raw >= 0.5

        # Check airborne status (must be off ground AND above 15m / 50ft AGL to avoid sim load glitches)
        if not onground and alt_agl > 15.0:
            self._was_airborne = True
            if alt_agl > 15000 * 0.3048:
                self.flight_phase = "CRUISE"
                self.state_summary = "Cruising at high altitude"
            elif alt_agl > 1000 * 0.3048:
                self.flight_phase = "CLIMB/DESCENT"
                self.state_summary = "Climbing out / descending"
            else:
                self.flight_phase = "AIRBORNE"
                self.state_summary = "Low altitude flight"
        else:
            if self._was_airborne:
                if gs < 5.0 and prk_brk:
                    self.flight_phase = "DEBOARDING"
                    self.state_summary = "Arrived at gate - parked & deboarding"
                else:
                    self.flight_phase = "TAXI_IN"
                    self.state_summary = "Taxing to arrival gate"
            else:
                if prk_brk and not beacon:
                    self.flight_phase = "BOARDING"
                    self.state_summary = "Parked at gate - passenger boarding"
                elif beacon and gs > 2.0:
                    self.flight_phase = "TAXI_OUT"
                    self.state_summary = "Taxing out to runway"
                elif beacon:
                    self.flight_phase = "PUSHBACK"
                    self.state_summary = "Engines/Beacon ON - pushback & engine start"
                else:
                    self.flight_phase = "BOARDING"
                    self.state_summary = "At gate - preparing for boarding"

        for idx, rule in enumerate(rules):
            rule_id = rule.get("id", f"rule_{idx}")
            sound_name = rule.get("sound_name")
            if not sound_name:
                continue

            # Check if once-per-flight and already triggered
            if rule.get("once_per_flight", True) and rule_id in self._triggered_rules:
                continue

            # Check cooldown
            if rule_id in self._cooldown_expiry and now < self._cooldown_expiry[rule_id]:
                continue

            # Already waiting on delay timer?
            if rule_id in self._pending_delayed:
                continue

            clean_sound = sound_name.strip().lower()

            # Boarding rules require manual boarding start
            if clean_sound in ("boardingwelcome", "boardingmusic") and not self.boarding_started:
                continue

            # Prevent departure / takeoff rules from triggering once airborne or after landing
            if self._was_airborne and clean_sound in DEPARTURE_SOUNDS:
                continue

            # Prevent landing / arrival rules from triggering before ever taking off
            if not self._was_airborne and clean_sound in ARRIVAL_SOUNDS:
                continue

            # Evaluate conditions according to rule logic (AND, OR, NAND, NOR)
            conditions = rule.get("conditions", [])
            if not conditions:
                continue

            logic = rule.get("logic", "AND").upper()
            results = [self._check_condition(cond, current_values) for cond in conditions]

            if logic == "OR":
                match = any(results)
            elif logic == "NAND":
                match = not all(results)
            elif logic == "NOR":
                match = not any(results)
            else:  # default "AND"
                match = all(results)

            if match:
                # Mark triggered and set cooldown
                self._triggered_rules.add(rule_id)
                cooldown = rule.get("cooldown_seconds", 300)
                self._cooldown_expiry[rule_id] = now + cooldown

                delay = float(rule.get("delay_seconds", 0))
                desc = rule.get("description", sound_name)

                if delay > 0:
                    self._pending_delayed[rule_id] = (now + delay, sound_name, desc)
                    logger.debug(f"Rule '{rule_id}' conditions met. Delayed by {delay}s.")
                else:
                    hour = self.get_current_flight_hour()
                    sound_file = self.packs.resolve_sound(self.active_airline, sound_name, time_hour=hour)
                    if sound_file:
                        self.audio.play_announcement(sound_file)
                        self._record_played_sound(sound_name)
                        self._log_event(f"🔔 [Auto-Trigger] '{sound_name}' ({desc}) -> {self.active_airline}")
                    else:
                        self._log_event(f"⚠️ [Auto-Trigger] '{sound_name}' triggered, but no audio file found.")

        # Save previous values for edge detection
        self._prev_values = dict(current_values)

    def _get_dataref_val(self, dataref, values_dict):
        if not dataref or not values_dict:
            return None
        if dataref in ("local_time_hour", "time_hour", "flight_hour", "hour"):
            if dataref in values_dict and values_dict[dataref] is not None:
                return float(values_dict[dataref])
            return float(self.get_current_flight_hour())
        if dataref in ("altitude_ft", "altitude_msl_ft", "sim/cockpit2/gauges/indicators/altitude_ft_pilot", "sim/flightmodel/position/elevation_ft"):
            if "sim/cockpit2/gauges/indicators/altitude_ft_pilot" in values_dict and values_dict["sim/cockpit2/gauges/indicators/altitude_ft_pilot"] is not None:
                return float(values_dict["sim/cockpit2/gauges/indicators/altitude_ft_pilot"])
            elif "sim/flightmodel/position/elevation" in values_dict and values_dict["sim/flightmodel/position/elevation"] is not None:
                return float(values_dict["sim/flightmodel/position/elevation"]) * 3.28084
            return values_dict.get(dataref)
        if dataref in ("altitude_agl_ft", "radio_alt_ft", "sim/cockpit2/gauges/indicators/radio_altimeter_height_ft_pilot", "sim/flightmodel/position/y_agl_ft"):
            if "sim/cockpit2/gauges/indicators/radio_altimeter_height_ft_pilot" in values_dict and values_dict["sim/cockpit2/gauges/indicators/radio_altimeter_height_ft_pilot"] is not None:
                return float(values_dict["sim/cockpit2/gauges/indicators/radio_altimeter_height_ft_pilot"])
            elif "sim/flightmodel/position/y_agl" in values_dict and values_dict["sim/flightmodel/position/y_agl"] is not None:
                return float(values_dict["sim/flightmodel/position/y_agl"]) * 3.28084
            return values_dict.get(dataref)
        return values_dict.get(dataref)

    def _check_condition(self, cond, current_values):
        # 0. Nested logic group: {"logic": "OR", "conditions": [...]}
        if "logic" in cond and "conditions" in cond:
            group_logic = cond.get("logic", "AND").upper()
            sub_results = [self._check_condition(c, current_values) for c in cond.get("conditions", [])]
            if group_logic == "OR":
                return any(sub_results)
            elif group_logic == "NAND":
                return not all(sub_results)
            elif group_logic == "NOR":
                return not any(sub_results)
            else:
                return all(sub_results)

        op = cond.get("op", cond.get("operator", "==")).lower()

        # 1. Boarding state conditions: "boarding_started", "boarding_completed"
        if op == "boarding_started" or cond.get("dataref") == "boarding_started":
            target = cond.get("value", 1)
            return bool(target) == bool(self.boarding_started)

        if op == "boarding_completed" or cond.get("dataref") == "boarding_completed":
            target = cond.get("value", 1)
            return bool(target) == bool(self.boarding_completed)

        # 2. Announcement dependency condition: "played SafetyBriefing", "after ArmDoors"
        if op == "has_played" or "announcement" in cond:
            ann = cond.get("announcement")
            if not ann:
                return False
            clean = ann.strip().lower()
            aliases = {clean}
            aliases.update(SOUND_ALIASES.get(clean, []))
            played_lower = {str(p).lower() for p in self._played_announcements}
            return any(a in played_lower for a in aliases)

        # 3. Dataref evaluation
        dataref = cond.get("dataref")
        if not dataref:
            return False

        current_val = self._get_dataref_val(dataref, current_values)
        if current_val is None:
            return False  # Dataref not yet received from X-Plane

        target = cond.get("value")
        prev_val = self._get_dataref_val(dataref, self._prev_values)

        if op in ("==", "eq"):
            return abs(float(current_val) - float(target)) < 0.01

        elif op in ("!=", "ne"):
            return abs(float(current_val) - float(target)) >= 0.01

        elif op in (">", "gt"):
            return float(current_val) > float(target)

        elif op in (">=", "gte"):
            return float(current_val) >= float(target)

        elif op in ("<", "lt"):
            return float(current_val) < float(target)

        elif op in ("<=", "lte"):
            return float(current_val) <= float(target)

        elif op in ("between", "in_range"):
            if isinstance(target, (list, tuple)) and len(target) == 2:
                min_v, max_v = float(target[0]), float(target[1])
                val = float(current_val)
                if min_v > max_v:
                    # Wraparound range (e.g. 21:00 to 06:00, or 75600s to 21600s)
                    return val >= min_v or val <= max_v
                else:
                    return min_v <= val <= max_v
            return False

        elif op in ("transition_to", "changed_to"):
            # Was not target previously, but now is target
            if prev_val is None:
                return False
            t_val = float(target)
            if t_val > 0:
                was_target = float(prev_val) >= t_val
                is_target = float(current_val) >= t_val
            else:
                was_target = abs(float(prev_val) - t_val) < 0.01
                is_target = abs(float(current_val) - t_val) < 0.01
            return (not was_target) and is_target

        elif op in ("increased_past", "climbed_through"):
            # Was <= target previously, but now > target
            if prev_val is None:
                return False
            return float(prev_val) <= float(target) and float(current_val) > float(target)

        elif op in ("decreased_past", "descended_through"):
            # Was >= target previously, but now < target
            if prev_val is None:
                return False
            return float(prev_val) >= float(target) and float(current_val) < float(target)
        return False
