========================================================================
X-PLANE CABIN ANNOUNCER - AIRLINE SOUND PACKS DIRECTORY
========================================================================

HOW TO INSTALL AIRLINE PACKS:
-----------------------------
Simply drop your Fenix A320 announcement airline folders directly into this 
directory!

Examples:
  airlines/
    DEFAULT/           <-- Built-in default chimes & fallback sounds
    BAW/               <-- British Airways sound files (.ogg, .wav, .mp3)
    DLH/               <-- Lufthansa
    AAL/               <-- American Airlines
    RYR/               <-- Ryanair
    AFR/               <-- Air France

You can also drop an entire "Announcements" folder hierarchy straight from 
your Community folder (e.g., airlines/Announcements/BAW/...) and it will be
automatically detected.


SUPPORTED AUDIO FORMATS:
------------------------
- .ogg (Fenix standard)
- .wav
- .mp3


STANDARD SOUND FILE NAMES (FENIX A320 CONVENTION):
--------------------------------------------------
- BoardingWelcome.ogg        (Attendant welcome announcement)
- BoardingWelcomePilot.ogg   (Captain welcome announcement)
- BoardingMusic.ogg          (Cabin boarding background music)
- BoardingComplete.ogg       (Boarding finished announcement)
- ArmDoors.ogg               (Cabin crew arm doors / cross check)
- PreSafetyBriefing.ogg      (Pre-safety announcement)
- SafetyBriefing.ogg         (Full safety briefing demonstration)
- CabinDimTakeoff.ogg        (Cabin lighting dimmed for takeoff)
- CrewSeatsTakeoff.ogg       (Cabin crew take your seats for takeoff)
- CallCabinSecureTakeoff.ogg (Cabin secure report)
- AfterTakeoff.ogg           (After takeoff climb announcement)
- FastenSeatbelt.ogg         (Seatbelt sign chime / message)
- TopOfClimbPilot.ogg        (Cruise altitude captain PA)
- CruiseElapsed.ogg          (Enroute flight update)
- TopOfDescentPilot.ogg      (Descent preparation captain PA)
- Descent.ogg                (Attendant prepare cabin for landing)
- Approach.ogg               (Final approach / 10,000 ft announcement)
- AfterLanding.ogg           (Welcome to destination announcement)
- DisarmDoors.ogg            (Cabin crew disarm doors)
- Deboarding.ogg             (Deboarding farewell announcement)


TIME OF DAY & VARIATIONS:
-------------------------
The announcer supports standard Fenix tags:
1. Time of day tags:
   - [Morning]   (05:00 - 11:59) -> e.g. BoardingWelcome[Morning].ogg
   - [Afternoon] (12:00 - 17:59) -> e.g. BoardingWelcome[Afternoon].ogg
   - [Evening]   (18:00 - 21:59) -> e.g. BoardingWelcome[Evening].ogg
   - [Night]     (22:00 - 04:59) -> e.g. BoardingWelcome[Night].ogg

2. Numbered variations:
   If you have multiple files like SafetyBriefing1.ogg and SafetyBriefing2.ogg,
   the announcer will randomly select one variation each flight!
