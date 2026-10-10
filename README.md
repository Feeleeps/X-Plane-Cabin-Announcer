# ✈️ X-Plane Cabin Announcer

A cabin announcement companion app and plugin for **X-Plane 12**, designed to play announcement packs formatted for the **Fenix A320**.

---

## 🌟 Highlights

- **Fenix A320 Sound Pack Compatibility**: Supports `.ogg`, `.wav`, and `.mp3` files matching Fenix A320 naming standards (`BoardingWelcome`, `ArmDoors`, `SafetyBriefing`, `TopOfClimbPilot`, `AfterLanding`, etc.).
- **Smart Tag & Variation Handling**:
  - Automatically matches time-of-day tags like `[Morning]`, `[Afternoon]`, `[Evening]`, and `[Night]`.
  - Randomly selects numbered variations (e.g. `SafetyBriefing1.ogg`, `SafetyBriefing2.ogg`).
  - Falls back to `DEFAULT` chimes if an airline pack lacks a particular sound.
- **Aircraft-Specific Dataref Configs**:
  - Store trigger profiles in `aircraft_configs/` (`.json` or `.yaml`).
  - Pre-packaged with configs for **Generic X-Plane 12 Airliners**, **ToLiss A320 Family**, and **Zibo Mod 737-800**.
  - Highly expressive conditions: `==`, `>`, `<`, `transition_to`, `increased_past`, `decreased_past`, delays, cooldowns, and `once_per_flight` protection.
- **Automatic Aircraft & Livery Detection**:
  - Automatically identifies loaded aircraft and liveries directly from X-Plane 12 (`Log.txt` & UDP datarefs).
  - Strict matching: matches ONLY if the airline's 3-letter ICAO code (e.g. `EZY`, `BAW`, `DLH`) is in the livery folder name, or if saved in your local `livery_mappings.json` config file.
  - No complex brand dictionaries to maintain. Unmatched liveries are simply manually selected in the GUI and automatically remembered for future flights.
- **Startup Splash & Configuration Screen**:
  - Polished loading screen that initializes modules, verifies the simulator path, and previews detected flight information.
  - Allows pre-flight confirmation before smoothly transitioning to the main Flight Deck interface.
- **Modern Flight-Deck CustomTkinter GUI**:
  - Rounded cards, clean cool dark-slate color palette (`#0d1117`, `#161b22`, `#38bdf8`).
  - Real-time status badges for X-Plane 12 UDP connectivity and dynamic flight phase.
  - Dropdown selector for airlines and aircraft profiles with one-click folder shortcuts (`📂`).
  - Independent volume controls for **Master**, **Announcements**, and **Boarding Music**.
  - Interactive manual soundboard to preview or trigger announcements anytime.
  - Real-time dataref telemetry table and live event log.
- **Zero C++ Compiler Required**: Runs directly via Python 3 with rock-solid UDP networking and `pygame-ce` audio streaming.

---

## 📁 Directory Structure

```
XPlaneCabinAnnouncer/
├── main.py                     # Main application entry point
├── run.bat                     # Double-click launcher for Windows
├── requirements.txt            # Python dependencies (pygame-ce, pyyaml)
├── settings.json               # Persisted user preferences
├── announcer/                  # Core application modules
│   ├── audio_engine.py         # Multi-channel audio mixer
│   ├── pack_manager.py         # Fenix A320 pack scanner & tag resolver
│   ├── config_manager.py       # Aircraft dataref config loader
│   ├── xplane_udp.py           # Real-time X-Plane RREF UDP interface
│   ├── rule_engine.py          # Trigger evaluator & flight phase tracker
│   └── gui.py                  # Dark-themed Tkinter GUI
├── airlines/                   # Drop your Fenix sound packs here!
│   ├── DEFAULT/                # Built-in chime fallback pack
│   └── BAW/                    # Example airline folder (British Airways)
└── aircraft_configs/           # Per-aircraft dataref trigger rules
    ├── Generic_XPlane12.json   # Works with default A330, 737, etc.
    ├── ToLiss_A320.json        # Uses ToLiss AirbusFBW datarefs
    └── Zibo_B738.json          # Uses Zibo 737 custom datarefs
```

---

## 🚀 Getting Started

### 1. Launching the App
Double-click `run.bat` or run:
```cmd
python main.py
```

### 2. Adding Airline Sound Packs
1. Open the `airlines/` folder (or click the `📂` button next to the airline dropdown in the GUI).
2. Paste your airline folders (e.g. `BAW`, `DLH`, `AAL`, `AFR`) directly into `airlines/`.
3. In the GUI, click the `🔄` refresh button and select your airline!

### 3. Connecting to X-Plane 12
- Simply launch X-Plane 12!
- By default, X-Plane listens on UDP port `49000` on `127.0.0.1`.
- When X-Plane is running and an aircraft is loaded, the status badge will switch to **🟢 CONNECTED** and start displaying live flight telemetry.
