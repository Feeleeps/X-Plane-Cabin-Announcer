"""
Modern Startup Setup & Splash Screen for X-Plane Cabin Announcer using CustomTkinter.
Displays pre-flight auto-detection results, allows full configuration of aircraft profile,
airline sound pack, and auto-detect settings, and launches when the user clicks 'Launch'.
"""

import os
import sys
import time
import customtkinter as ctk
from PIL import Image
from announcer.gui import apply_window_icon

class SplashScreen(ctk.CTkFrame):
    def __init__(self, parent_root, detector, pack_manager, config_manager, base_dir, on_complete):
        super().__init__(parent_root, fg_color="#0d1117")
        self.root = parent_root
        self.detector = detector
        self.packs = pack_manager
        self.configs = config_manager
        self.base_dir = base_dir
        self.on_complete = on_complete

        self.root.title("X-Plane Cabin Announcer - Pre-Flight Setup")
        self.root.geometry("620x640")
        self.root.resizable(False, False)
        self.root.configure(fg_color="#0d1117")

        # Set Window icon (native Win32 + CTk)
        apply_window_icon(self.root, self.base_dir)

        self._center_window()

        self.c = {
            "bg": "#0d1117",
            "card_bg": "#161b22",
            "card_border": "#30363d",
            "card_inner": "#0f141c",
            "fg": "#f0f6fc",
            "fg_muted": "#8b949e",
            "accent": "#38bdf8",
            "accent_dark": "#0284c7",
            "btn_navy": "#1e293b",
            "btn_navy_hover": "#334155",
            "green": "#10b981"
        }

        self.detected_data = {}

        self.pack(fill="both", expand=True)
        self._build_widgets()

        # Run background detection after rendering
        self.root.after(80, self._run_initialization)

    def _center_window(self):
        self.root.update_idletasks()
        w = 620
        h = 640
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_widgets(self):
        card = ctk.CTkFrame(self, fg_color=self.c["card_bg"], corner_radius=16, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. Header with Logo & Title
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(18, 8))

        png_path = os.path.join(self.base_dir, "app_icon.png")
        if os.path.exists(png_path):
            try:
                pil_img = Image.open(png_path)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(52, 52))
                lbl_icon = ctk.CTkLabel(header_frame, image=ctk_img, text="")
                lbl_icon.pack(side="left", padx=(0, 14))
            except Exception:
                pass

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left")

        lbl_title = ctk.CTkLabel(
            title_box,
            text="✈️  X-Plane Cabin Announcer",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self.c["fg"]
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            title_box,
            text="Pre-Flight Setup  •  Aircraft & Sound Pack Configuration",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.c["fg_muted"]
        )
        lbl_sub.pack(anchor="w")

        # 2. Status & Progress bar
        self.lbl_status = ctk.CTkLabel(
            card,
            text="Initializing sound packs and aircraft profiles...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.c["accent"]
        )
        self.lbl_status.pack(anchor="w", padx=24, pady=(10, 4))

        self.progress_bar = ctk.CTkProgressBar(
            card,
            progress_color=self.c["accent"],
            fg_color="#21262d",
            corner_radius=6,
            height=8
        )
        self.progress_bar.pack(fill="x", padx=24, pady=(0, 12))
        self.progress_bar.set(0.2)

        # 3. Telemetry Detection Summary Card
        detect_box = ctk.CTkFrame(card, fg_color=self.c["card_inner"], corner_radius=12, border_width=1, border_color=self.c["card_border"])
        detect_box.pack(fill="x", padx=20, pady=(0, 10))

        lbl_det_title = ctk.CTkLabel(
            detect_box,
            text="🔍  Sim Detection Telemetry",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.c["accent"]
        )
        lbl_det_title.pack(anchor="w", padx=14, pady=(8, 4))

        def _make_det_row(title):
            row = ctk.CTkFrame(detect_box, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text=title, width=145, anchor="w", text_color=self.c["fg_muted"], font=ctk.CTkFont(family="Segoe UI", size=11)).pack(side="left")
            val_lbl = ctk.CTkLabel(row, text="Scanning...", anchor="w", text_color="#cbd5e1", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
            val_lbl.pack(side="left", fill="x", expand=True)
            return val_lbl

        self.lbl_det_sim = _make_det_row("X-Plane Root:")
        self.lbl_det_acf = _make_det_row("Sim Active Aircraft:")
        self.lbl_det_livery = _make_det_row("Sim Active Livery:")

        # 4. Configurable Pre-Flight Options Card
        cfg_box = ctk.CTkFrame(card, fg_color=self.c["card_inner"], corner_radius=12, border_width=1, border_color=self.c["card_border"])
        cfg_box.pack(fill="x", padx=20, pady=(0, 12))

        lbl_cfg_title = ctk.CTkLabel(
            cfg_box,
            text="⚙️  Configurable Pre-Flight Options",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.c["fg"]
        )
        lbl_cfg_title.pack(anchor="w", padx=14, pady=(8, 8))

        # Option 1: Aircraft Profile Selection
        row_acf = ctk.CTkFrame(cfg_box, fg_color="transparent")
        row_acf.pack(fill="x", padx=14, pady=(0, 6))

        ctk.CTkLabel(
            row_acf,
            text="Aircraft Profile:",
            width=145,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self.c["fg_muted"]
        ).pack(side="left")

        configs_list = self.configs.get_config_names() or ["Generic X-Plane 12 Airliner"]
        self.opt_config = ctk.CTkOptionMenu(
            row_acf,
            values=configs_list,
            fg_color=self.c["btn_navy"],
            button_color="#334155",
            button_hover_color="#475569",
            text_color=self.c["fg"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            dynamic_resizing=False,
            height=28
        )
        self.opt_config.pack(side="left", fill="x", expand=True)
        if configs_list:
            self.opt_config.set(configs_list[0])

        # Option 2: Airline Sound Pack Selection
        row_air = ctk.CTkFrame(cfg_box, fg_color="transparent")
        row_air.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            row_air,
            text="Airline Sound Pack:",
            width=145,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self.c["fg_muted"]
        ).pack(side="left")

        airlines_list = self.packs.get_available_airlines() or ["DEFAULT"]
        self.opt_airline = ctk.CTkOptionMenu(
            row_air,
            values=airlines_list,
            fg_color=self.c["btn_navy"],
            button_color="#334155",
            button_hover_color="#475569",
            text_color=self.c["fg"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            dynamic_resizing=False,
            height=28
        )
        self.opt_airline.pack(side="left", fill="x", expand=True)
        if airlines_list:
            self.opt_airline.set("DEFAULT" if "DEFAULT" in airlines_list else airlines_list[0])

        # Option 3: Continuous Auto-Detection Switch
        self.sw_auto_detect = ctk.CTkSwitch(
            cfg_box,
            text="Enable Continuous Flight & Livery Auto-Detection in background",
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.sw_auto_detect.pack(anchor="w", padx=14, pady=(2, 4))
        self.sw_auto_detect.select()

        # Option 4: Start Minimized to System Tray Switch
        self.sw_minimize = ctk.CTkSwitch(
            cfg_box,
            text="Launch minimized to system tray (runs in background while flying)",
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.sw_minimize.pack(anchor="w", padx=14, pady=(2, 10))

        # 5. Bottom Action Buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(4, 16))

        btn_editor = ctk.CTkButton(
            btn_frame,
            text="🌐 Web Config Editor",
            fg_color=self.c["btn_navy"],
            hover_color=self.c["btn_navy_hover"],
            corner_radius=10,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._open_web_editor
        )
        btn_editor.pack(side="left", padx=(0, 10))

        self.btn_launch = ctk.CTkButton(
            btn_frame,
            text="🚀  Launch Flight Deck",
            fg_color="#0284c7",
            hover_color="#0369a1",
            corner_radius=10,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._finish_and_launch
        )
        self.btn_launch.pack(side="right", fill="x", expand=True)

    def _run_initialization(self):
        # Scan configs and sound packs
        self.progress_bar.set(0.50)
        self.lbl_status.configure(text="Scanning simulator environment and active liveries...")
        self.root.update()

        try:
            self.detected_data = self.detector.run_detection()
        except Exception as e:
            self.detected_data = {}

        # Update Sim Telemetry labels
        xplane_path = self.detected_data.get("xplane_dir") or "Not found (standalone mode)"
        self.lbl_det_sim.configure(text=xplane_path)

        acf = self.detected_data.get("matched_config")
        acf_path = self.detected_data.get("acf_path")
        if acf_path:
            acf_display = f"{acf or 'Detected'} ({os.path.basename(acf_path)})"
        elif acf:
            acf_display = acf
        else:
            acf_display = "None (ready to fly)"
        self.lbl_det_acf.configure(text=acf_display, text_color="#38bdf8")

        livery = self.detected_data.get("livery_name") or "Default"
        self.lbl_det_livery.configure(text=livery)

        # Pre-select detected values in options dropdowns if matched
        all_configs = self.configs.get_config_names()
        if acf and acf in all_configs:
            self.opt_config.set(acf)
        elif all_configs:
            self.opt_config.set(all_configs[0])

        airline = self.detected_data.get("matched_airline")
        all_airlines = self.packs.get_available_airlines()
        if airline and airline in all_airlines:
            self.opt_airline.set(airline)
        elif "DEFAULT" in all_airlines:
            self.opt_airline.set("DEFAULT")

        self.progress_bar.set(1.0)
        self.progress_bar.configure(progress_color=self.c["green"])
        self.lbl_status.configure(
            text="Ready! Configure your options above, then click 'Launch Flight Deck'.",
            text_color=self.c["green"]
        )

    def _open_web_editor(self):
        try:
            from announcer.editor_server import start_editor_server
            start_editor_server(self.base_dir, port=8765, open_browser=True, config_manager=self.configs)
        except Exception:
            import webbrowser
            webbrowser.open("http://127.0.0.1:8765")

    def _finish_and_launch(self):
        opts = {
            "config": self.opt_config.get(),
            "airline": self.opt_airline.get(),
            "auto_detect": self.sw_auto_detect.get() == 1,
            "minimize_to_tray": self.sw_minimize.get() == 1,
            "minimize_to_taskbar": self.sw_minimize.get() == 1,
            "detected": self.detected_data
        }
        self.on_complete(opts)
