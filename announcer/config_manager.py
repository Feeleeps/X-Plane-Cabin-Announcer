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
      "sim/time/local_time_sec between 75600 and 21600"
      "local_time_hour between 21 and 6"
      "boarding_started == 1"
      "boarding_completed == 1"
      "played SafetyBriefing"
    """
    if isinstance(expr, dict):
        if "logic" in expr and "conditions" in expr:
            return {
                "logic": expr.get("logic", "AND").upper(),
                "conditions": [parse_condition_expr(c) for c in expr.get("conditions", [])]
            }
        return expr  # Already a dict format

    expr_str = str(expr).strip()
    if not expr_str:
        return {"dataref": "", "op": "==", "value": 1.0}

    # Protect 'between ... and ...' from being split by boolean 'and'
    protected = re.sub(
        r"(between\s+[\d\.\-]+)\s+and\s+([\d\.\-]+)",
        r"\1 __AND_BETWEEN__ \2",
        expr_str,
        flags=re.IGNORECASE
    )

    # Tokenize boolean structure: parentheses and boolean keywords
    parts = re.split(r"(\(|\)|\b(?:OR|NOR|AND|NAND|NOT)\b)", protected, flags=re.IGNORECASE)
    tokens = []
    for p in parts:
        p_str = p.strip()
        if not p_str:
            continue
        up = p_str.upper()
        if up in ("(", ")", "OR", "NOR", "AND", "NAND", "NOT"):
            tokens.append((up, up))
        else:
            tokens.append(("ATOM", p_str.replace("__AND_BETWEEN__", "and")))

    # If no boolean operators or parentheses, parse as single atomic condition
    bool_toks = [t for t in tokens if t[0] in ("OR", "NOR", "AND", "NAND", "NOT", "(", ")")]
    if not bool_toks:
        return _parse_atomic_condition(expr_str)

    # Recursive descent parser for compound boolean expressions
    idx = 0
    def peek():
        return tokens[idx] if idx < len(tokens) else (None, None)

    def get():
        nonlocal idx
        tok = peek()
        idx += 1
        return tok

    def parse_or():
        left = parse_and()
        while peek()[0] in ("OR", "NOR"):
            op = get()[0]
            right = parse_and()
            if isinstance(left, dict) and left.get("logic") == op:
                left["conditions"].append(right)
            else:
                left = {"logic": op, "conditions": [left, right]}
        return left

    def parse_and():
        left = parse_not()
        while peek()[0] in ("AND", "NAND"):
            op = get()[0]
            right = parse_not()
            if isinstance(left, dict) and left.get("logic") == op:
                left["conditions"].append(right)
            else:
                left = {"logic": op, "conditions": [left, right]}
        return left

    def parse_not():
        if peek()[0] == "NOT":
            get()
            sub = parse_primary()
            return {"logic": "NAND", "conditions": [sub, sub]}
        return parse_primary()

    def parse_primary():
        tok, val = get()
        if tok == "(":
            sub = parse_or()
            if peek()[0] == ")":
                get()
            return sub
        elif tok == "ATOM":
            return _parse_atomic_condition(val)
        else:
            return _parse_atomic_condition(val or "")

    try:
        return parse_or()
    except Exception as e:
        logger.warning(f"Error parsing compound expression '{expr_str}', falling back: {e}")
        return _parse_atomic_condition(expr_str)


def _parse_atomic_condition(expr):
    """Parses a single atomic condition string into an evaluation dict."""
    expr = str(expr).strip()

    # Normalize 'is >' -> '>', 'is <' -> '<', 'is >=' -> '>=', etc.
    expr = re.sub(r"\bis\s*([<>=!]+)", r"\1", expr, flags=re.IGNORECASE)
    # Normalize 'is 1' -> '== 1'
    expr = re.sub(r"\bis\s+([\d\.\-]+)$", r"== \1", expr, flags=re.IGNORECASE)
    # Normalize single '=' not part of '==', '>=', '<=', '!='
    expr = re.sub(r"(?<![<>=!])=(?!=)", "==", expr)

    # 1. Boarding state conditions: "boarding_started", "boarding_completed"
    m_bs = re.match(r"^boarding_started(?:\s*(==|!=)\s*([01]))?$", expr, re.IGNORECASE)
    if m_bs:
        val = 1
        if m_bs.group(1) and m_bs.group(2):
            val = int(m_bs.group(2)) if m_bs.group(1) == "==" else (0 if m_bs.group(2) == "1" else 1)
        return {"op": "boarding_started", "value": val}

    m_bc = re.match(r"^boarding_completed(?:\s*(==|!=)\s*([01]))?$", expr, re.IGNORECASE)
    if m_bc:
        val = 1
        if m_bc.group(1) and m_bc.group(2):
            val = int(m_bc.group(2)) if m_bc.group(1) == "==" else (0 if m_bc.group(2) == "1" else 1)
        return {"op": "boarding_completed", "value": val}

    # 2. Announcement dependency condition: "played SafetyBriefing", "after ArmDoors"
    m = re.match(r"^(?:played|after|has_played)\s+([A-Za-z0-9_\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"announcement": m.group(1).strip(), "op": "has_played"}

    # 3. Range / between condition: "sim/time/local_time_sec between 75600 and 21600"
    m = re.match(r"^(.+?)\s+between\s+([\d\.\-]+)\s+and\s+([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {
            "dataref": m.group(1).strip(),
            "op": "between",
            "value": [float(m.group(2)), float(m.group(3))]
        }

    # 4. Climbs past / increased past
    m = re.match(r"^(.+?)\s+(?:climbs_past|increased_past)\s+([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"dataref": m.group(1).strip(), "op": "increased_past", "value": float(m.group(2))}

    # 5. Descends past / decreased past
    m = re.match(r"^(.+?)\s+(?:descends_past|decreased_past)\s+([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"dataref": m.group(1).strip(), "op": "decreased_past", "value": float(m.group(2))}

    # 6. Transition to / flips to: ->, becomes, changes_to
    m = re.match(r"^(.+?)\s*(?:->|becomes|changes_to)\s*([\d\.\-]+)$", expr, re.IGNORECASE)
    if m:
        return {"dataref": m.group(1).strip(), "op": "transition_to", "value": float(m.group(2))}

    # 7. Standard comparison operators: ==, !=, >=, <=, >, <
    m = re.match(r"^(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+)$", expr)
    if m:
        val_str = m.group(3).strip()
        try:
            val = float(val_str)
        except ValueError:
            try:
                import json
                val = json.loads(val_str)
            except Exception:
                val = val_str
        return {"dataref": m.group(1).strip(), "op": m.group(2), "value": val}

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
            rule["logic"] = trigger_def.get("logic", "AND").upper()

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
        def _collect(cond_item):
            if not isinstance(cond_item, dict):
                return
            if "conditions" in cond_item:
                for sub in cond_item["conditions"]:
                    _collect(sub)
            dref = cond_item.get("dataref")
            if dref and not dref.startswith("__") and dref not in ("boarding_started", "boarding_completed"):
                datarefs.add(dref.strip())

        rules = config.get("rules", [])
        for rule in rules:
            for cond in rule.get("conditions", []):
                _collect(cond)

        # Include custom hardware mappings datarefs if defined
        hw = config.get("hardware_mappings") or {}
        pa_dref = hw.get("pa_volume_dataref")
        pa_idx = hw.get("pa_volume_index")
        if pa_dref:
            try:
                if pa_idx is not None and str(pa_idx).strip() != "" and int(pa_idx) > 0:
                    datarefs.add(f"{pa_dref}[{pa_idx}]")
                else:
                    datarefs.add(pa_dref.strip())
            except Exception:
                datarefs.add(pa_dref.strip())
        call_dref = hw.get("cabin_call_annunciator_dataref")
        if call_dref:
            datarefs.add(call_dref.strip())
                    
        # Always include baseline flight status datarefs (standard + popular custom like AirbusFBW)
        baseline = {
            "sim/flightmodel/failures/onground_any",
            "sim/flightmodel/position/elevation",
            "sim/flightmodel/position/y_agl",
            "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
            "sim/cockpit2/gauges/indicators/radio_altimeter_height_ft_pilot",
            "sim/flightmodel/position/indicated_airspeed",
            "sim/flightmodel/position/groundspeed",
            "sim/cockpit2/switches/fasten_seat_belts",
            "sim/cockpit2/switches/beacon_on",
            "sim/cockpit2/controls/parking_brake_ratio",
            "sim/time/local_time_sec",
            # ToLiss native status datarefs
            "AirbusFBW/ParkBrake",
            "AirbusFBW/SeatBeltSignsOn",
            "AirbusFBW/BeaconLightsOn",
            "AirbusFBW/NoSmokingSignsOn",
            # Audio Control Panel & Cockpit Volume datarefs
            "AirbusFBW/ACP1RotaryPositions",
            "AirbusFBW/ACP2RotaryPositions",
            "sim/cockpit2/radios/actuators/audio_volume_com1",
            "sim/cockpit2/radios/actuators/audio_volume_com2",
            # Cabin Call & Ready datarefs
            "AirbusFBW/CheckCabin",
            "AirbusFBW/CabinReady"
        }
        datarefs.update(baseline)
        return datarefs
