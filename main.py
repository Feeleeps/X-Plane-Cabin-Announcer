"""
X-Plane Cabin Announcer - Main Entry Point.
Launches the background UDP telemetry client, audio engine, trigger engine, and GUI.
"""

import os
import sys
import logging
import customtkinter as ctk

from announcer.audio_engine import AudioEngine
from announcer.pack_manager import PackManager
from announcer.config_manager import ConfigManager
from announcer.xplane_udp import XPlaneUDP
from announcer.rule_engine import RuleEngine
from announcer.detector import AutoDetector
from announcer.splash import SplashScreen
from announcer.gui import CabinAnnouncerGUI

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

    # App User Model ID on Windows for custom taskbar grouping
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xplane.cabinannouncer.app.1")
        except Exception:
            pass

    # Launch Startup Splash Screen
    splash_root = ctk.CTk()
    splash_results = {}

    def on_splash_finish(detected_info, auto_detect_enabled):
        splash_results["detected"] = detected_info
        splash_results["auto_detect"] = auto_detect_enabled
        splash_root.destroy()

    splash = SplashScreen(
        root=splash_root,
        detector=detector,
        pack_manager=pack_manager,
        config_manager=config_manager,
        base_dir=base_dir,
        on_complete=on_splash_finish
    )

    try:
        splash_root.mainloop()
    except Exception as e:
        logger.debug(f"Splash exit: {e}")

    # Launch Main Flight Deck GUI
    # Window Icon (Windows .ico vs Mac/Linux .png)
    ico_path = os.path.join(base_dir, "app_icon.ico")
    png_path = os.path.join(base_dir, "app_icon.png")
    if sys.platform == "win32" and os.path.exists(ico_path):
        try:
            main_root.iconbitmap(ico_path)
        except Exception:
            pass
    elif os.path.exists(png_path):
        try:
            from PIL import ImageTk, Image
            img = ImageTk.PhotoImage(Image.open(png_path))
            main_root.iconphoto(False, img)
        except Exception:
            pass

    auto_detect_setting = splash_results.get("auto_detect", True)
    app = CabinAnnouncerGUI(
        root=main_root,
        audio_engine=audio_engine,
        pack_manager=pack_manager,
        config_manager=config_manager,
        rule_engine=rule_engine,
        udp_client=udp_client,
        base_dir=base_dir,
        detector=detector,
        auto_detect_enabled=auto_detect_setting
    )

    # Apply splash detected settings if found
    detected_data = splash_results.get("detected", {})
    if detected_data.get("matched_config"):
        cfg = detected_data["matched_config"]
        if cfg in config_manager.get_config_names():
            app.opt_config.set(cfg)
            app._on_config_selected(cfg)

    if detected_data.get("matched_airline"):
        air = detected_data["matched_airline"]
        if air in pack_manager.get_available_airlines():
            app.opt_airline.set(air)
            app._on_airline_selected(air)

    try:
        main_root.mainloop()
    except KeyboardInterrupt:
        logger.info("Exiting on keyboard interrupt...")
    finally:
        audio_engine.stop_all()
        rule_engine.stop()
        udp_client.stop()
        logger.info("X-Plane Cabin Announcer closed cleanly.")

if __name__ == "__main__":
    main()
