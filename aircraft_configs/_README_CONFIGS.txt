========================================================================
X-PLANE CABIN ANNOUNCER - SIMPLIFIED AIRCRAFT CONFIG GUIDE
========================================================================

Aircraft config files (.json or .yaml) tell the announcer when each sound
should be played based on X-Plane datarefs.

SIMPLIFIED FORMAT EXAMPLE:
-------------------------
{
  "name": "My Custom Airliner",
  "aircraft_icao_match": ["A320", "A321"],
  "triggers": {
    "BoardingWelcome": {
      "when": [
        "sim/flightmodel/failures/onground_any == 1",
        "AirbusFBW/ParkBrake >= 0.9",
        "AirbusFBW/BeaconLightsOn == 0"
      ],
      "delay": 6
    },
    "ArmDoors": {
      "when": [
        "sim/flightmodel/failures/onground_any == 1",
        "AirbusFBW/BeaconLightsOn -> 1"
      ],
      "delay": 2
    },
    "SafetyBriefing": {
      "when": [
        "sim/flightmodel/failures/onground_any == 1",
        "sim/flightmodel/position/groundspeed > 1.5",
        "AirbusFBW/BeaconLightsOn == 1"
      ],
      "delay": 4
    },
    "AfterTakeoff": {
      "when": "sim/flightmodel/position/y_agl climbs_past 457.2",
      "delay": 4
    },
    "FastenSeatbelt": {
      "when": "AirbusFBW/SeatBeltSignsOn -> 1",
      "delay": 1,
      "cooldown": 60,
      "repeat": true
    }
  }
}

AVAILABLE OPERATORS IN EXPRESSIONS ("when"):
--------------------------------------------
- "dataref == value"          Equal (e.g. "sim/cockpit2/switches/beacon_on == 1")
- "dataref != value"          Not equal
- "dataref > value"           Greater than (e.g. "groundspeed > 1.5")
- "dataref >= value"          Greater than or equal
- "dataref < value"           Less than
- "dataref <= value"          Less than or equal
- "dataref -> value"          Rising edge / transition to (e.g. switch flipped ON)
- "dataref climbs_past val"   Climbing through an altitude (MSL or AGL)
- "dataref descends_past val" Descending through an altitude (MSL or AGL)

OPTIONAL TRIGGER SETTINGS:
--------------------------
- "delay":      Seconds to wait after condition is met before playing (default: 0).
- "repeat":     true if the sound can play multiple times per flight (e.g. seatbelts).
- "cooldown":   Minimum seconds before it can trigger again (default: 300).
