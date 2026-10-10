"""
Rule engine for evaluating aircraft dataref triggers and playing cabin announcements.
Handles edge detection, cooldowns, once-per-flight rules, delays, and flight phase state.
"""

import time
import threading
import logging

logger = logging.getLogger("CabinAnnouncer.RuleEngine")

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
        
        # Flight state heuristics
        self.flight_phase = "BOARDING"
        self._was_airborne = False

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
        self._was_airborne = False
        self.flight_phase = "BOARDING"
        self._log_event("Flight state reset. All announcements armed.")

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

    def trigger_sound_manually(self, sound_name):
        """Allows manual triggering of any announcement sound."""
        hour = self.get_current_flight_hour()
        sound_file = self.packs.resolve_sound(self.active_airline, sound_name, time_hour=hour)
        if not sound_file:
            self._log_event(f"❌ Sound '{sound_name}' not found for airline {self.active_airline}.")
            return False

        if sound_name == "BoardingMusic":
            if self.audio.is_music_playing():
                self.audio.stop_music()
                self._log_event("⏹ Stopped boarding music.")
                return True
            else:
                self.audio.play_boarding_music(sound_file)
                self._log_event(f"🎵 Playing boarding music: {self.active_airline}")
                return True
        else:
            self.audio.play_announcement(sound_file)
            self._log_event(f"🔊 Playing announcement: {sound_name} ({self.active_airline})")
            return True

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
        beacon = current_values.get("sim/cockpit2/switches/beacon_on", 0.0) >= 0.5
        prk_brk = current_values.get("sim/cockpit2/controls/parking_brake_ratio", 0.0)

        if not onground:
            self._was_airborne = True
            if alt_agl > 15000 * 0.3048:
                self.flight_phase = "CRUISE"
            elif alt_agl > 1000 * 0.3048:
                self.flight_phase = "CLIMB/DESCENT"
            else:
                self.flight_phase = "AIRBORNE"
        else:
            if self._was_airborne:
                if gs < 15.0 and prk_brk >= 0.5:
                    self.flight_phase = "DEBOARDING"
                else:
                    self.flight_phase = "TAXI_IN"
            else:
                if prk_brk >= 0.5 and not beacon:
                    self.flight_phase = "BOARDING"
                elif beacon and gs > 1.5:
                    self.flight_phase = "TAXI_OUT"
                elif beacon:
                    self.flight_phase = "PUSHBACK"

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

            # Evaluate all conditions (logical AND)
            conditions = rule.get("conditions", [])
            if not conditions:
                continue

            match = True
            for cond in conditions:
                if not self._check_condition(cond, current_values):
                    match = False
                    break

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
                        self._log_event(f"🔔 [Auto-Trigger] '{sound_name}' ({desc}) -> {self.active_airline}")
                    else:
                        self._log_event(f"⚠️ [Auto-Trigger] '{sound_name}' triggered, but no audio file found.")

        # Save previous values for edge detection
        self._prev_values = dict(current_values)

    def _check_condition(self, cond, current_values):
        dataref = cond.get("dataref")
        if not dataref:
            return False

        current_val = current_values.get(dataref)
        if current_val is None:
            return False  # Dataref not yet received from X-Plane

        op = cond.get("op", cond.get("operator", "==")).lower()
        target = cond.get("value")
        prev_val = self._prev_values.get(dataref)

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
            min_v, max_v = target[0], target[1]
            return min_v <= float(current_val) <= max_v

        elif op in ("transition_to", "changed_to"):
            # Was not target previously, but now is target
            if prev_val is None:
                return False
            was_target = abs(float(prev_val) - float(target)) < 0.01
            is_target = abs(float(current_val) - float(target)) < 0.01
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
