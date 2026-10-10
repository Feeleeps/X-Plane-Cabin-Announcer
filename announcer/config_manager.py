"""
Aircraft configuration manager.
Loads, validates, and manages aircraft-specific config files (.json and .yaml).
Extracts datarefs and triggers for each aircraft.
"""

import os
import json
import logging

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger("CabinAnnouncer.Config")

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
                    
        # Always include baseline flight status datarefs if not already present
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
