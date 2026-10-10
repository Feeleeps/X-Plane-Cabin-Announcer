"""
Auto-detection module for X-Plane 12 aircraft type and airline sound pack.
Strict Matching Rules:
1. Aircraft: Matches aircraft .acf path and ICAO to configured aircraft profiles.
2. Airline: Matches ONLY if:
   - A custom mapping exists in the user's local 'livery_mappings.json' config file, OR
   - The exact airline ICAO code (e.g. EZY, BAW, DLH) is found in the livery folder name.
   Otherwise, requires manual user selection (no brand name dictionary guessing).
"""

import os
import re
import json
import logging

logger = logging.getLogger("CabinAnnouncer.Detector")

class AutoDetector:
    def __init__(self, xplane_dir=None, pack_manager=None, config_manager=None, base_dir=None):
        self.pack_manager = pack_manager
        self.config_manager = config_manager
        self.base_dir = base_dir or os.getcwd()
        self.xplane_dir = self._find_xplane_dir(xplane_dir)
        
        self.mappings_file = os.path.join(self.base_dir, "livery_mappings.json")
        self.user_mappings = self._load_mappings()

        self.detected_acf_path = None
        self.detected_livery_name = None
        self.detected_aircraft_config = None
        self.detected_airline = None

    def _find_xplane_dir(self, custom_dir=None):
        """Finds or confirms the X-Plane 12 root folder."""
        candidates = []
        if custom_dir and os.path.exists(custom_dir):
            candidates.append(custom_dir)

        # Standard drives & paths across Windows, macOS, and Linux
        home = os.path.expanduser("~")
        candidates.extend([
            # Windows
            r"E:\X-Plane",
            r"D:\X-Plane 12",
            r"D:\X-Plane",
            r"C:\X-Plane 12",
            r"C:\Program Files (x86)\Steam\steamapps\common\X-Plane 12",
            r"D:\SteamLibrary\steamapps\common\X-Plane 12",
            r"E:\SteamLibrary\steamapps\common\X-Plane 12",
            # macOS
            "/Applications/X-Plane 12",
            "/Applications/X-Plane",
            os.path.join(home, "Desktop/X-Plane 12"),
            os.path.join(home, "Library/Application Support/Steam/steamapps/common/X-Plane 12"),
            # Linux
            os.path.join(home, "X-Plane 12"),
            os.path.join(home, ".local/share/Steam/steamapps/common/X-Plane 12"),
            os.path.join(home, ".steam/steam/steamapps/common/X-Plane 12"),
            "/opt/X-Plane 12"
        ])

        for path in candidates:
            if os.path.exists(os.path.join(path, "Log.txt")) or \
               os.path.exists(os.path.join(path, "X-Plane.exe")) or \
               os.path.exists(os.path.join(path, "X-Plane-x86_64")) or \
               os.path.exists(os.path.join(path, "X-Plane.app")):
                logger.info(f"Discovered X-Plane root at: {path}")
                return os.path.abspath(path)

        return None

    def _load_mappings(self):
        """Loads user-saved livery-to-airline mappings from local config file."""
        # Check user's personal file first, then fall back to example template if not created yet
        target_file = self.mappings_file
        if not os.path.exists(target_file):
            example_file = os.path.join(self.base_dir, "livery_mappings.example.json")
            if os.path.exists(example_file):
                target_file = example_file

        if os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Filter out comment keys like _comment
                        clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
                        logger.info(f"Loaded {len(clean_data)} custom livery mappings from {target_file}")
                        return clean_data
            except Exception as e:
                logger.error(f"Error loading livery mappings: {e}")
        return {}

    def save_mapping(self, livery_name, airline_icao):
        """Saves a user's manual livery mapping to local config file."""
        if not livery_name or not airline_icao:
            return
        clean_livery = livery_name.strip()
        clean_icao = airline_icao.strip().upper()

        self.user_mappings[clean_livery] = clean_icao
        try:
            with open(self.mappings_file, "w", encoding="utf-8") as f:
                json.dump(self.user_mappings, f, indent=2)
            logger.info(f"Saved custom livery mapping: '{clean_livery}' -> '{clean_icao}'")
        except Exception as e:
            logger.error(f"Failed to save livery_mappings.json: {e}")

    def scan_log(self):
        """Scans the latest entries in X-Plane's Log.txt for aircraft and livery loads."""
        if not self.xplane_dir:
            return None, None

        log_path = os.path.join(self.xplane_dir, "Log.txt")
        if not os.path.exists(log_path):
            return None, None

        acf_path = None
        livery_name = None

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line in reversed(lines):
                # 1. Aircraft loading pattern
                if not acf_path and "I/ACF: Loading airplane number 0 with" in line:
                    match = re.search(r"Loading airplane number 0 with\s+(.+)$", line)
                    if match:
                        acf_path = match.group(1).strip()

                # 2. Livery loading patterns
                if not livery_name and ("liveries" in line.lower() or "livery" in line.lower()):
                    m = re.search(r"liveries[\\/]([^\\/]+)", line, re.IGNORECASE)
                    if m:
                        livery_name = m.group(1).strip()

                if acf_path and livery_name:
                    break

            if acf_path:
                self.detected_acf_path = acf_path
            if livery_name:
                self.detected_livery_name = livery_name

        except Exception as e:
            logger.debug(f"Error reading Log.txt: {e}")

        return self.detected_acf_path, self.detected_livery_name

    def match_aircraft_config(self, acf_path, acf_icao=None):
        """Matches the detected aircraft path / ICAO to one of the loaded configs."""
        if not self.config_manager:
            return "Generic X-Plane 12 Airliner"

        configs = self.config_manager.configs
        search_terms = []
        if acf_path:
            search_terms.append(acf_path.lower())
        if acf_icao:
            search_terms.append(acf_icao.lower().strip())

        search_str = " ".join(search_terms)

        # 1. Check for specific keywords
        if "toliss" in search_str:
            for name in configs:
                if "toliss" in name.lower():
                    return name

        if "zibo" in search_str or "b738" in search_str or "737-800" in search_str:
            for name in configs:
                if "zibo" in name.lower() or "737" in name.lower():
                    return name

        # 2. Check ICAO matches defined inside the config files
        for name, data in configs.items():
            icao_list = data.get("aircraft_icao_match", [])
            for icao in icao_list:
                if icao.lower() in search_str:
                    return name

        # Default fallback
        for name in configs:
            if "generic" in name.lower():
                return name

        available = self.config_manager.get_config_names()
        return available[0] if available else None

    def match_airline(self, livery_name):
        """
        Strict matching:
        1. Checks user's local 'livery_mappings.json' config file.
        2. Matches ONLY if an available airline ICAO (e.g. EZY, BAW) is found in the livery folder name.
        Otherwise returns None.
        """
        if not self.pack_manager or not livery_name:
            return None

        clean_livery = livery_name.strip()
        available_packs = self.pack_manager.get_available_airlines()

        # 1. Check user's local config file (livery_mappings.json)
        if clean_livery in self.user_mappings:
            mapped_icao = self.user_mappings[clean_livery]
            if mapped_icao in available_packs:
                logger.info(f"Matched via livery_mappings.json: '{clean_livery}' -> '{mapped_icao}'")
                return mapped_icao

        # 2. Check if the airline ICAO code itself is present as a word/token in the livery name
        for pack in available_packs:
            if pack.upper() == "DEFAULT":
                continue
            # Word boundary regex match for ICAO code (e.g. \bEZY\b or \bBAW\b)
            if re.search(rf"\b{re.escape(pack)}\b", clean_livery, re.IGNORECASE):
                logger.info(f"Direct ICAO code '{pack}' matched in livery name: '{clean_livery}'")
                return pack

        # No match found -> Requires manual selection
        return None

    def run_detection(self, udp_client=None):
        """
        Runs complete detection from Log.txt and UDP datarefs.
        Returns dict with detected information.
        """
        acf_path, livery_name = self.scan_log()

        # Extract ICAO string from UDP dataref if connected
        acf_icao = None
        if udp_client and udp_client.is_connected():
            chars = []
            for i in range(4):
                val = udp_client.get_value(f"sim/aircraft/view/acf_ICAO[{i}]", None)
                if val is not None and val > 0:
                    try:
                        chars.append(chr(int(val)))
                    except Exception:
                        pass
            if chars:
                acf_icao = "".join(chars).strip()

        matched_config = self.match_aircraft_config(acf_path, acf_icao)
        matched_airline = self.match_airline(livery_name)

        return {
            "xplane_dir": self.xplane_dir,
            "acf_path": acf_path,
            "acf_icao": acf_icao,
            "livery_name": livery_name,
            "matched_config": matched_config,
            "matched_airline": matched_airline
        }
