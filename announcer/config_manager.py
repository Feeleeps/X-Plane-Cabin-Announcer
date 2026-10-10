"""
Aircraft configuration manager.
Loads, validates, and manages aircraft-specific config files (.json and .yaml).
Supports both:
1. Simplified Human-Readable Trigger Expressions (e.g. "AirbusFBW/BeaconLightsOn -> 1", "elevation climbs_past 3048")
2. Full Verbose Rules Format (backwards compatible)
"""

import os
import re
import json
import logging

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger("CabinAnnouncer.Config")

def parse_condition_expr(expr):
    """
    Parses a human-readable condition expression into standard condition dict:
    Examples:
      "sim/flightmodel/failures/onground_any == 1"
      "sim/cockpit2/controls/parking_brake_ratio >= 0.8"
      "AirbusFBW/BeaconLightsOn -> 1"
      "sim/flightmodel/position/y_agl climbs_past 457.2"
      "sim/flightmodel/position/elevation descends_past 3048"
    """
    if isinstance(expr, dict):
        return expr  # Already a dict format

    expr = str(expr).strip()

    # 1. Climbs past / increased past
    m = re.match(r"^(.+?)\s+(?:climbs_past|increased_past)\s+([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"dataref": m.group(1).strip(), "op": "increased_past", "value": float(m.group(2))}

    # 2. Descends past / decreased past
    m = re.match(r"^(.+?)\s+(?:descends_past|decreased_past)\s+([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"dataref": m.group(1).strip(), "op": "decreased_past", "value": float(m.group(2))}

    # 3. Transition to / flips to: ->, becomes, changes_to
    m = re.match(r"^(.+?)\s*(?:->|becomes|changes_to)\s*([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"dataref": m.group(1).strip(), "op": "transition_to", "value": float(m.group(2))}

    # 4. Standard comparison operators: ==, !=, >=, <=, >, <
    m = re.match(r"^(.+?)\s*(==|!=|>=|<=|>|<)\s*([\d\.\-]+)$", expr)
    if m:
        return {"dataref": m.group(1).strip(), "op": m.group(2), "value": float(m.group(3))}

    logger.warning(f"Could not parse condition expression: '{expr}'")
    return {"dataref": expr, "op": "==", "value": 1.0}

def normalize_config(config_data, filename=""):
    """
    Converts simplified 'triggers' dictionary syntax into standard 'rules' array.
    Ensures 100% compatibility and zero loss of functionality.
    """
    if not isinstance(config_data, dict):
        return None

    # If already using verbose 'rules' format
    if "rules" in config_data and isinstance(config_data["rules"], list):
        # Normalize any condition expressions inside verbose rules
        for rule in config_data["rules"]:
            conds = rule.get("conditions", [])
            norm_conds = []
            for c in conds:
                norm_conds.append(parse_condition_expr(c))
            rule["conditions"] = norm_conds
        return config_data

    # Convert clean 'triggers' format to normalized 'rules'
    triggers = config_data.get("triggers", {})
    rules = []

    for sound_name, trigger_def in triggers.items():
        rule = {
            "id": f"{sound_name.lower()}_rule",
            "sound_name": sound_name,
            "description": f"{sound_name} trigger",
            "delay_seconds": 0,
            "cooldown_seconds": 300,
            "once_per_flight": True,
            "conditions": []
        }

        # Case 1: Simple string trigger: "ArmDoors": "AirbusFBW/BeaconLightsOn -> 1"
        if isinstance(trigger_def, (str, list)):
            raw_conds = [trigger_def] if isinstance(trigger_def, str) else trigger_def
            rule["conditions"] = [parse_condition_expr(c) for c in raw_conds]

        # Case 2: Object trigger: "BoardingWelcome": { "when": [...], "delay": 6 }
        elif isinstance(trigger_def, dict):
            rule["description"] = trigger_def.get("desc", trigger_def.get("description", rule["description"]))
            rule["delay_seconds"] = float(trigger_def.get("delay", trigger_def.get("delay_seconds", 0)))
            rule["cooldown_seconds"] = float(trigger_def.get("cooldown", trigger_def.get("cooldown_seconds", 300)))
            
            # Default once_per_flight: true unless repeat: true or once_per_flight: false
            repeat = trigger_def.get("repeat", False)
            rule["once_per_flight"] = trigger_def.get("once_per_flight", not repeat)

            when = trigger_def.get("when", trigger_def.get("conditions", []))
            raw_conds = [when] if isinstance(when, str) else (when if isinstance(when, list) else [])
            rule["conditions"] = [parse_condition_expr(c) for c in raw_conds]

        rules.append(rule)

    config_data["rules"] = rules
    return config_data


class ConfigManager:
    def __init__(self, configs_dir):
        self.configs_dir = os.path.abspath(configs_dir)
        self.configs = {}  # { "Config_Name": config_dict }
        self.rescan()

    def rescan(self):
        """Scans the configs directory for .json and .yaml config files."""
        self.configs.clear()
        if not os.path.exists(self.configs_dir):
            os.makedirs(self.configs_dir, exist_ok=True)
            return

        for f in os.listdir(self.configs_dir):
            full_path = os.path.join(self.configs_dir, f)
            if not os.path.isfile(full_path):
                continue

            config_data = None
            if f.lower().endswith(".json"):
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        config_data = json.load(fp)
                except Exception as e:
                    logger.error(f"Error loading JSON config {f}: {e}")
            elif f.lower().endswith((".yaml", ".yml")) and YAML_AVAILABLE:
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        config_data = yaml.safe_load(fp)
                except Exception as e:
                    logger.error(f"Error loading YAML config {f}: {e}")

            if config_data and isinstance(config_data, dict):
                config_data = normalize_config(config_data, f)
                config_name = config_data.get("name", os.path.splitext(f)[0])
                config_data["_filename"] = f
                config_data["_filepath"] = full_path
                self.configs[config_name] = config_data

        logger.info(f"Loaded {len(self.configs)} aircraft configs: {list(self.configs.keys())}")

    def get_config_names(self):
        """Returns list of loaded configuration profile names."""
        return sorted(list(self.configs.keys()))

    def get_config(self, config_name):
        """Returns the config dictionary for a given profile name."""
        return self.configs.get(config_name)

    def extract_required_datarefs(self, config_name):
        """
        Extracts a unique set of all dataref names referenced in the rules of this config.
        """
        config = self.get_config(config_name)
        if not config:
            return set()

        datarefs = set()
        rules = config.get("rules", [])
        for rule in rules:
            conditions = rule.get("conditions", [])
            for cond in conditions:
                dref = cond.get("dataref")
                if dref:
                    datarefs.add(dref.strip())
                    
        # Always include baseline flight status datarefs
        baseline = {
            "sim/flightmodel/failures/onground_any",
            "sim/flightmodel/position/elevation",
            "sim/flightmodel/position/y_agl",
            "sim/flightmodel/position/indicated_airspeed",
            "sim/flightmodel/position/groundspeed",
            "sim/cockpit2/switches/fasten_seat_belts",
            "sim/cockpit2/switches/beacon_on",
            "sim/cockpit2/controls/parking_brake_ratio",
            "sim/time/local_time_sec"
        }
        datarefs.update(baseline)
        return datarefs
