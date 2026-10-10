"""
Airline sound pack manager.
Scans and resolves Fenix A320 format sound files and directory structures.
Supports time-of-day tags ([Morning], [Afternoon], [Evening], [Night]),
numeric random variations (e.g. SafetyBriefing1.ogg, SafetyBriefing2.ogg),
and multiple audio extensions (.ogg, .wav, .mp3).
"""

import os
import re
import glob
import random
from datetime import datetime
import logging

logger = logging.getLogger("CabinAnnouncer.Packs")

# Recognized Fenix standard sound event keys
STANDARD_SOUND_KEYS = [
    "BoardingWelcome",
    "BoardingWelcomePilot",
    "BoardingMusic",
    "BoardingComplete",
    "ArmDoors",
    "PreSafetyBriefing",
    "SafetyBriefing",
    "CabinDimTakeoff",
    "CrewSeatsTakeoff",
    "CallCabinSecureTakeoff",
    "AfterTakeoff",
    "FastenSeatbelt",
    "TopOfClimbPilot",
    "CruiseElapsed",
    "TopOfDescentPilot",
    "Descent",
    "Approach",
    "AfterLanding",
    "DisarmDoors",
    "Deboarding"
]

SUPPORTED_EXTENSIONS = (".ogg", ".wav", ".mp3", ".flac")

def get_current_time_tag(current_hour=None):
    """Returns the time tag matching Fenix convention based on hour (0-23)."""
    if current_hour is None:
        current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        return "Morning"
    elif 12 <= current_hour < 18:
        return "Afternoon"
    elif 18 <= current_hour < 22:
        return "Evening"
    else:
        return "Night"

class PackManager:
    def __init__(self, base_airlines_dir):
        self.base_airlines_dir = os.path.abspath(base_airlines_dir)
        self.packs = {}  # { "ICAO": pack_dir_path }
        self.rescan()

    def rescan(self):
        """Scans the airlines directory for airline sound packs."""
        self.packs.clear()
        if not os.path.exists(self.base_airlines_dir):
            os.makedirs(self.base_airlines_dir, exist_ok=True)
            return

        # Direct folders in base_airlines_dir (e.g. airlines/BAW, airlines/DEFAULT)
        # Also supports Fenix Announcements subfolder: airlines/Announcements/BAW
        candidates = []
        for entry in os.scandir(self.base_airlines_dir):
            if entry.is_dir():
                if entry.name.lower() == "announcements":
                    # Scan inside Announcements/
                    for sub in os.scandir(entry.path):
                        if sub.is_dir():
                            candidates.append(sub)
                else:
                    candidates.append(entry)

        for folder in candidates:
            pack_name = folder.name.strip().upper()
            self.packs[pack_name] = folder.path
            
        logger.info(f"Discovered {len(self.packs)} airline sound packs: {list(self.packs.keys())}")

    def get_available_airlines(self):
        """Returns sorted list of available airline pack names."""
        return sorted(list(self.packs.keys()))

    def get_pack_directory(self, airline_icao):
        """Returns absolute directory for an airline pack."""
        return self.packs.get(airline_icao.strip().upper())

    def get_sound_files_in_pack(self, airline_icao):
        """Returns list of audio files inside a specific airline folder."""
        pack_dir = self.get_pack_directory(airline_icao)
        if not pack_dir or not os.path.exists(pack_dir):
            return []
        
        files = []
        for root, _, filenames in os.walk(pack_dir):
            for f in filenames:
                if f.lower().endswith(SUPPORTED_EXTENSIONS):
                    files.append(os.path.join(root, f))
        return files

    def resolve_sound(self, airline_icao, sound_key, time_hour=None, fallback_to_default=True):
        """
        Resolves the best matching audio file for a given sound key and airline.
        Handles time tags ([Morning], [Evening], etc.) and randomized variations.
        Falls back to 'DEFAULT' pack if not found in requested airline.
        """
        chosen_file = self._find_sound_in_pack(airline_icao, sound_key, time_hour)
        if chosen_file:
            return chosen_file

        # Fallback to DEFAULT pack if requested
        if fallback_to_default and airline_icao.upper() != "DEFAULT" and "DEFAULT" in self.packs:
            logger.info(f"Sound '{sound_key}' not found in {airline_icao}, falling back to DEFAULT pack.")
            return self._find_sound_in_pack("DEFAULT", sound_key, time_hour)

        return None

    def _find_sound_in_pack(self, airline_icao, sound_key, time_hour=None):
        pack_dir = self.get_pack_directory(airline_icao)
        if not pack_dir or not os.path.exists(pack_dir):
            return None

        time_tag = get_current_time_tag(time_hour)
        clean_key = sound_key.strip().lower()

        candidate_files = []
        for root, _, filenames in os.walk(pack_dir):
            for f in filenames:
                if not f.lower().endswith(SUPPORTED_EXTENSIONS):
                    continue
                file_stem = os.path.splitext(f)[0]
                full_path = os.path.join(root, f)

                # Check if this file relates to sound_key
                # e.g. "BoardingWelcome", "BoardingWelcome[Morning]", "BoardingWelcome1"
                # Strip bracketed tags and numbers to find base name
                base_name = re.sub(r"\[.*?\]", "", file_stem)
                base_name = re.sub(r"\d+$", "", base_name).strip().lower()

                if base_name == clean_key:
                    candidate_files.append((f, full_path, file_stem))

        if not candidate_files:
            return None

        # Filter by time tag if any file specifically matches current time of day
        time_matches = []
        for f, full_path, file_stem in candidate_files:
            # Check for tag like [Morning], [Evening]
            if f"[{time_tag.lower()}]" in file_stem.lower():
                time_matches.append(full_path)

        if time_matches:
            # If multiple time matches exist (e.g. BoardingWelcome[Morning]1.ogg, BoardingWelcome[Morning]2.ogg), pick random
            return random.choice(time_matches)

        # Filter out files tagged for a DIFFERENT time of day
        all_tags = ["[morning]", "[afternoon]", "[evening]", "[night]"]
        general_matches = []
        for f, full_path, file_stem in candidate_files:
            stem_lower = file_stem.lower()
            has_other_tag = any(t in stem_lower for t in all_tags if t != f"[{time_tag.lower()}]")
            if not has_other_tag:
                general_matches.append(full_path)

        if general_matches:
            return random.choice(general_matches)

        # Fallback to any matching candidate file
        return random.choice([p for _, p, _ in candidate_files])
