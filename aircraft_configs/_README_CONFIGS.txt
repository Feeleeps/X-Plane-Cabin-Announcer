========================================================================
X-PLANE CABIN ANNOUNCER - AIRCRAFT CONFIGURATION DIRECTORY
========================================================================

Each aircraft has its own configuration file (.json or .yaml) specifying
when each announcement sound should be played based on X-Plane datarefs.

FILE FORMAT:
------------
{
  "name": "My Custom Aircraft",
  "author": "Your Name",
  "description": "Rules for my custom airliner",
  "aircraft_icao_match": ["A320", "A321"],
  "rules": [
    {
      "id": "safety_briefing_taxi",
      "sound_name": "SafetyBriefing",
      "description": "Safety demo during taxi out",
      "conditions": [
        {
          "dataref": "sim/flightmodel/failures/onground_any",
          "op": "==",
          "value": 1.0
        },
        {
          "dataref": "sim/flightmodel/position/groundspeed",
          "op": ">",
          "value": 1.5
        },
        {
          "dataref": "sim/cockpit2/switches/beacon_on",
          "op": "==",
          "value": 1.0
        }
      ],
      "delay_seconds": 3,
      "cooldown_seconds": 300,
      "once_per_flight": true
    }
  ]
}

AVAILABLE OPERATORS ("op"):
---------------------------
- "=="              Equal to value (e.g. 1.0)
- "!="              Not equal to value
- ">"               Greater than value
- ">="              Greater than or equal to value
- "<"               Less than value
- "<="              Less than or equal to value
- "between"         Value inside range [min, max]
- "transition_to"   Triggers when dataref flips from another value to this value
- "increased_past"  Triggers when climbing through a value (was <=, now >)
- "decreased_past"  Triggers when descending through a value (was >=, now <)

RULE PROPERTIES:
----------------
- id:               Unique string ID for the rule.
- sound_name:       Fenix sound name (e.g. SafetyBriefing, ArmDoors, TopOfClimbPilot).
- conditions:       Array of condition objects (all conditions must be true = AND).
- delay_seconds:    Seconds to wait after condition is met before playing audio.
- cooldown_seconds: Minimum seconds before this rule can trigger again.
- once_per_flight:  If true, triggers only once per flight until flight reset.
