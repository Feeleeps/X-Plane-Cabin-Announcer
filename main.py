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

    # 1. Initialize Audio Engine
    audio_engine = AudioEngine()

    # 2. Initialize Sound Pack Manager (Fenix A320 format)
    pack_manager = PackManager(airlines_dir)

    # 3. Initialize Aircraft Dataref Config Manager
    config_manager = ConfigManager(configs_dir)

    # 4. Initialize X-Plane UDP Client
    udp_client = XPlaneUDP(xplane_ip="127.0.0.1", xplane_port=49000)
    udp_client.start()

    # 5. Initialize Rule Engine
    rule_engine = RuleEngine(udp_client, pack_manager, audio_engine)
    rule_engine.start()

    # 6. Initialize GUI
    if sys.platform == "win32":
        try:
            import ctypes
            # Unique App ID so Windows displays custom taskbar icon instead of generic Python icon
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xplane.cabinannouncer.app.1")
        except Exception:
            pass

    root = ctk.CTk()
    icon_path = os.path.join(base_dir, "app_icon.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    app = CabinAnnouncerGUI(
        root=root,
        audio_engine=audio_engine,
        pack_manager=pack_manager,
        config_manager=config_manager,
        rule_engine=rule_engine,
        udp_client=udp_client,
        base_dir=base_dir
    )

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Exiting on keyboard interrupt...")
    finally:
        audio_engine.stop_all()
        rule_engine.stop()
        udp_client.stop()
        logger.info("X-Plane Cabin Announcer closed cleanly.")

if __name__ == "__main__":
    main()
