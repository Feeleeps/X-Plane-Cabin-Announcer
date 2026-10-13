"""
X-Plane Cabin Announcer - Main Entry Point.
Launches the background UDP telemetry client, audio engine, trigger engine,
and displays pre-flight setup splash screen before launching the flight deck GUI.
"""

import os
import sys
import logging

def _ensure_dependencies():
    required = [
        ("customtkinter", "customtkinter"),
        ("sounddevice", "sounddevice"),
        ("soundfile", "soundfile"),
        ("scipy", "scipy"),
        ("numpy", "numpy"),
        ("pygame", "pygame-ce"),
        ("yaml", "pyyaml"),
        ("PIL", "pillow"),
        ("pystray", "pystray"),
    ]
    missing = []
    for mod_name, pkg_name in required:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print("=" * 60)
        print("   X-PLANE CABIN ANNOUNCER - FIRST TIME SETUP")
        print("=" * 60)
        print(f"Missing required packages: {', '.join(missing)}")
        print("Installing packages from requirements.txt... Please wait...")
        try:
            import subprocess
            base = os.path.dirname(os.path.abspath(__file__))
            req_file = os.path.join(base, "requirements.txt")
            if os.path.exists(req_file):
                cmd = [sys.executable, "-m", "pip", "install", "-r", req_file, "--prefer-binary"]
            else:
                cmd = [sys.executable, "-m", "pip", "install", *missing, "--prefer-binary"]
            subprocess.check_call(cmd)
            print("Dependencies installed successfully! Launching...\n")
        except Exception as e:
            print(f"\n[ERROR] Failed to auto-install dependencies: {e}")
            print("Please run manually in terminal: pip install -r requirements.txt\n")
            sys.exit(1)

_ensure_dependencies()

import customtkinter as ctk

from announcer.audio_engine import AudioEngine
from announcer.pack_manager import PackManager
from announcer.config_manager import ConfigManager
from announcer.xplane_udp import XPlaneUDP
from announcer.rule_engine import RuleEngine
from announcer.detector import AutoDetector
from announcer.splash import SplashScreen
from announcer.gui import CabinAnnouncerGUI, apply_window_icon

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

def main():
    setup_logging()
    logger = logging.getLogger("CabinAnnouncer.Main")
    logger.info("Starting X-Plane Cabin Announcer...")

    # Determine base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    airlines_dir = os.path.join(base_dir, "airlines")
    configs_dir = os.path.join(base_dir, "aircraft_configs")

    # 1. Initialize Audio Engine (Real-Time DSP)
    audio_engine = AudioEngine()

    # 2. Initialize Sound Pack Manager (Fenix A320 format)
    pack_manager = PackManager(airlines_dir)

    # 3. Initialize Aircraft Dataref Config Manager
    config_manager = ConfigManager(configs_dir)

    # 4. Initialize AutoDetector
    detector = AutoDetector(pack_manager=pack_manager, config_manager=config_manager)

    # 5. Initialize X-Plane UDP Client
    udp_client = XPlaneUDP(xplane_ip="127.0.0.1", xplane_port=49000)
    udp_client.start()

    # 6. Initialize Rule Engine
    rule_engine = RuleEngine(udp_client, pack_manager, audio_engine)
    rule_engine.start()

    # 7. Start Web Config Editor server in background (available at http://127.0.0.1:8765)
    try:
        from announcer.editor_server import start_editor_server
        start_editor_server(base_dir, port=8765, open_browser=False, config_manager=config_manager)
    except Exception as e:
        logger.debug(f"Web editor startup: {e}")

    # App User Model ID on Windows for custom taskbar grouping
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xplane.cabinannouncer.app.1")
        except Exception:
            pass

    # Single root window architecture (prevents CustomTkinter Tcl/destroy crashes)
    root = ctk.CTk()

    # Window Icon (Windows .ico vs Mac/Linux .png)
    apply_window_icon(root, base_dir)

    def launch_flight_deck(options):
        # 1. Clean up splash frame
        splash.destroy()

        # 2. Resize and configure root window for main flight deck
        root.title("X-Plane Cabin Announcer")
        root.geometry("1080x830")
        root.minsize(980, 750)
        root.resizable(True, True)

        # Center on screen
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - 1080) // 2)
        y = max(0, (sh - 830) // 2)
        root.geometry(f"1080x830+{x}+{y}")

        # Ensure custom taskbar and titlebar icon persists after resizable / geometry reconfiguration
        apply_window_icon(root, base_dir)
        root.after(100, lambda: apply_window_icon(root, base_dir))

        # 3. Initialize and mount main GUI
        app = CabinAnnouncerGUI(
            root=root,
            audio_engine=audio_engine,
            pack_manager=pack_manager,
            config_manager=config_manager,
            rule_engine=rule_engine,
            udp_client=udp_client,
            base_dir=base_dir,
            detector=detector,
            auto_detect_enabled=options.get("auto_detect", True)
        )

        # 4. Apply splash-configured profile and sound pack
        selected_cfg = options.get("config")
        if selected_cfg and selected_cfg in config_manager.get_config_names():
            app.opt_config.set(selected_cfg)
            app._on_config_selected(selected_cfg)

        selected_air = options.get("airline")
        if selected_air and selected_air in pack_manager.get_available_airlines():
            app.opt_airline.set(selected_air)
            app._on_airline_selected(selected_air)

        # 5. Minimize directly to system tray if requested on splash screen
        if options.get("minimize_to_tray") or options.get("minimize_to_taskbar"):
            root.after(200, app._minimize_to_tray)

    # Mount Startup Setup & Splash Screen
    splash = SplashScreen(
        parent_root=root,
        detector=detector,
        pack_manager=pack_manager,
        config_manager=config_manager,
        base_dir=base_dir,
        on_complete=launch_flight_deck
    )

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Exiting on keyboard interrupt...")
    finally:
        audio_engine.stop_all()
        rule_engine.stop()
        udp_client.stop()
        try:
            from announcer.editor_server import stop_editor_server
            stop_editor_server()
        except Exception:
            pass
        logger.info("X-Plane Cabin Announcer closed cleanly.")

if __name__ == "__main__":
    main()
