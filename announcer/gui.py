"""
Modern Flight-Deck Styled GUI for X-Plane Cabin Announcer using CustomTkinter.
Features:
- Solid two-column grid layout with uniform column widths (prevents any stretching or UI distortion).
- Fixed-width dropdowns with dynamic_resizing=False and profile info labels (handles long aircraft profile names cleanly).
- True real-time Cabin PA speaker DSP filter controls (instant chunk-level audio updates).
- Real-time connection badge and flight phase indicator.
- Independent volume controls (Master, Announcements, Boarding Music).
- Categorized manual announcement soundboard.
- Live dataref telemetry table and live event log.
- Settings auto-save and restore.
"""

import os
import sys
import json
import subprocess
from datetime import datetime
import customtkinter as ctk

# Configure CustomTkinter default styling
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class CabinAnnouncerGUI:
    def __init__(self, root, audio_engine, pack_manager, config_manager, rule_engine, udp_client, base_dir):
        self.root = root
        self.audio = audio_engine
        self.packs = pack_manager
        self.configs = config_manager
        self.rule_engine = rule_engine
        self.udp = udp_client
        self.base_dir = base_dir

        self.settings_file = os.path.join(self.base_dir, "settings.json")
        self.settings = self._load_settings()

        # Consistent Cool Flight-Deck Palette
        self.c = {
            "bg": "#0d1117",
            "card_bg": "#161b22",
            "card_border": "#30363d",
            "card_inner": "#0f141c",
            "fg": "#f0f6fc",
            "fg_muted": "#8b949e",
            "accent": "#38bdf8",
            "accent_hover": "#0ea5e9",
            "accent_dark": "#0369a1",
            "btn_navy": "#1e293b",
            "btn_navy_hover": "#334155",
            "green": "#10b981",
            "green_bg": "#064e3b",
            "red": "#f87171",
            "red_bg": "#450a0a",
            "pill_blue_bg": "#0c2d48"
        }

        self._setup_window()
        self._build_widgets()

        # Connect rule engine logging
        self.rule_engine.add_log_callback(self.append_log)

        # Restore saved settings
        self._restore_settings()

        # Start periodic GUI update loop
        self._update_loop()

    def _setup_window(self):
        self.root.title("X-Plane Cabin Announcer")
        self.root.geometry("1080x830")
        self.root.minsize(980, 750)
        self.root.configure(fg_color=self.c["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self):
        # 1. Top Header Bar
        header = ctk.CTkFrame(self.root, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        header.pack(fill="x", padx=16, pady=(14, 10))

        # Title & Subtitle
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", padx=18, pady=12)

        lbl_title = ctk.CTkLabel(
            title_box,
            text="✈️  X-Plane Cabin Announcer",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self.c["fg"]
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            title_box,
            text="Fenix A320 Audio Format  •  Real-Time Cabin PA Filter  •  Aircraft Dataref Triggers",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.c["fg_muted"]
        )
        lbl_sub.pack(anchor="w")

        # Status Pills
        status_box = ctk.CTkFrame(header, fg_color="transparent")
        status_box.pack(side="right", padx=18, pady=12)

        self.pill_phase = ctk.CTkLabel(
            status_box,
            text="PHASE: BOARDING",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.c["accent"],
            fg_color=self.c["pill_blue_bg"],
            corner_radius=20,
            padx=14,
            pady=6
        )
        self.pill_phase.pack(side="left", padx=(0, 10))

        self.pill_conn = ctk.CTkLabel(
            status_box,
            text="🔴 WAITING FOR X-PLANE (UDP 49000)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.c["red"],
            fg_color=self.c["red_bg"],
            corner_radius=20,
            padx=14,
            pady=6
        )
        self.pill_conn.pack(side="left")

        # 2. Main Body Grid (Two Strictly Equal Columns)
        main_body = ctk.CTkFrame(self.root, fg_color="transparent")
        main_body.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        main_body.grid_columnconfigure(0, weight=1, uniform="main_cols")
        main_body.grid_columnconfigure(1, weight=1, uniform="main_cols")
        main_body.grid_rowconfigure(0, weight=1)

        left_col = ctk.CTkFrame(main_body, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right_col = ctk.CTkFrame(main_body, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Build cards
        self._build_profile_card(left_col)
        self._build_dsp_filter_card(left_col)
        self._build_volume_card(left_col)
        self._build_telemetry_card(left_col)

        self._build_soundboard_card(right_col)
        self._build_log_card(right_col)

    def _build_profile_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="x", pady=(0, 10))

        header_lbl = ctk.CTkLabel(
            card,
            text="📁  Profile & Sound Pack Selection",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        # --- Airline Picker (Grid Layout) ---
        row_airline = ctk.CTkFrame(card, fg_color="transparent")
        row_airline.pack(fill="x", padx=16, pady=3)
        row_airline.grid_columnconfigure(0, weight=0)
        row_airline.grid_columnconfigure(1, weight=1)
        row_airline.grid_columnconfigure(2, weight=0)
        row_airline.grid_columnconfigure(3, weight=0)

        ctk.CTkLabel(row_airline, text="Airline Sound Pack:", width=145, anchor="w", text_color=self.c["fg_muted"]).grid(row=0, column=0, sticky="w")
        
        self.opt_airline = ctk.CTkOptionMenu(
            row_airline,
            values=["DEFAULT"],
            command=self._on_airline_selected,
            corner_radius=8,
            width=210,
            dynamic_resizing=False,
            fg_color=self.c["btn_navy"],
            button_color=self.c["accent_dark"],
            button_hover_color=self.c["accent_hover"],
            dropdown_fg_color=self.c["card_inner"]
        )
        self.opt_airline.grid(row=0, column=1, sticky="ew", padx=(4, 6))

        btn_open_air = ctk.CTkButton(row_airline, text="📂", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._open_airlines_dir)
        btn_open_air.grid(row=0, column=2, padx=(0, 4))
        btn_ref_air = ctk.CTkButton(row_airline, text="🔄", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._refresh_packs)
        btn_ref_air.grid(row=0, column=3)

        self.lbl_airline_info = ctk.CTkLabel(card, text="Active Pack: DEFAULT (15 audio files)", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=self.c["accent"])
        self.lbl_airline_info.pack(anchor="w", padx=16, pady=(1, 6))

        # --- Aircraft Config Picker (Grid Layout) ---
        row_config = ctk.CTkFrame(card, fg_color="transparent")
        row_config.pack(fill="x", padx=16, pady=3)
        row_config.grid_columnconfigure(0, weight=0)
        row_config.grid_columnconfigure(1, weight=1)
        row_config.grid_columnconfigure(2, weight=0)
        row_config.grid_columnconfigure(3, weight=0)

        ctk.CTkLabel(row_config, text="Aircraft Dataref Profile:", width=145, anchor="w", text_color=self.c["fg_muted"]).grid(row=0, column=0, sticky="w")

        self.opt_config = ctk.CTkOptionMenu(
            row_config,
            values=["Generic X-Plane 12 Airliner"],
            command=self._on_config_selected,
            corner_radius=8,
            width=210,
            dynamic_resizing=False,
            fg_color=self.c["btn_navy"],
            button_color=self.c["accent_dark"],
            button_hover_color=self.c["accent_hover"],
            dropdown_fg_color=self.c["card_inner"]
        )
        self.opt_config.grid(row=0, column=1, sticky="ew", padx=(4, 6))

        btn_open_cfg = ctk.CTkButton(row_config, text="📂", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._open_configs_dir)
        btn_open_cfg.grid(row=0, column=2, padx=(0, 4))
        btn_ref_cfg = ctk.CTkButton(row_config, text="🔄", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._refresh_configs)
        btn_ref_cfg.grid(row=0, column=3)

        self.lbl_config_info = ctk.CTkLabel(card, text="Active Profile: Generic X-Plane 12 Airliner", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=self.c["accent"])
        self.lbl_config_info.pack(anchor="w", padx=16, pady=(1, 8))

        # --- Auto Triggers Switch & Reset button ---
        row_actions = ctk.CTkFrame(card, fg_color="transparent")
        row_actions.pack(fill="x", padx=16, pady=(4, 12))

        self.sw_auto_trigger = ctk.CTkSwitch(
            row_actions,
            text="Automatic Dataref Triggers",
            command=self._on_toggle_auto,
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        self.sw_auto_trigger.pack(side="left")
        self.sw_auto_trigger.select()

        btn_reset = ctk.CTkButton(
            row_actions,
            text="🔄 Re-Arm Flight",
            width=115,
            height=28,
            corner_radius=8,
            fg_color="#1e3a5f",
            hover_color="#2563eb",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self.rule_engine.reset_flight_state
        )
        btn_reset.pack(side="right")

    def _build_dsp_filter_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="x", pady=(0, 10))

        header_lbl = ctk.CTkLabel(
            card,
            text="🎙️  Cabin PA Speaker Effect (Real-Time DSP)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        # Switch & Profile
        row_top = ctk.CTkFrame(card, fg_color="transparent")
        row_top.pack(fill="x", padx=16, pady=4)

        self.sw_pa_filter = ctk.CTkSwitch(
            row_top,
            text="Cabin Speaker Filter",
            command=self._on_dsp_change,
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.sw_pa_filter.pack(side="left")
        self.sw_pa_filter.select()

        self.seg_mode = ctk.CTkSegmentedButton(
            row_top,
            values=["Overhead PA", "Intercom"],
            command=self._on_dsp_change,
            corner_radius=8,
            selected_color=self.c["accent_dark"],
            selected_hover_color=self.c["accent_hover"],
            unselected_color=self.c["btn_navy"]
        )
        self.seg_mode.pack(side="right")
        self.seg_mode.set("Overhead PA")

        # Filter Intensity Slider
        row_slider = ctk.CTkFrame(card, fg_color="transparent")
        row_slider.pack(fill="x", padx=16, pady=(6, 12))

        ctk.CTkLabel(row_slider, text="Filter Presence:", width=110, anchor="w", text_color=self.c["fg_muted"]).pack(side="left")
        self.slider_pa_intensity = ctk.CTkSlider(
            row_slider,
            from_=0,
            to=100,
            command=self._on_dsp_change,
            progress_color=self.c["accent"],
            button_color=self.c["accent"],
            button_hover_color=self.c["accent_hover"]
        )
        self.slider_pa_intensity.pack(side="left", fill="x", expand=True, padx=(4, 10))
        self.slider_pa_intensity.set(90)

        self.lbl_dsp_val = ctk.CTkLabel(row_slider, text="90%", width=40, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self.lbl_dsp_val.pack(side="right")

    def _build_volume_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="x", pady=(0, 10))

        header_lbl = ctk.CTkLabel(
            card,
            text="🔊  Volume Control",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        def _make_slider(label_text, default_val, on_change):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=label_text, width=130, anchor="w", text_color=self.c["fg_muted"]).pack(side="left")
            slider = ctk.CTkSlider(
                row,
                from_=0,
                to=100,
                command=on_change,
                progress_color=self.c["accent"],
                button_color=self.c["accent"],
                button_hover_color=self.c["accent_hover"]
            )
            slider.pack(side="left", fill="x", expand=True, padx=(4, 10))
            slider.set(default_val)
            lbl = ctk.CTkLabel(row, text=f"{int(default_val)}%", width=40, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
            lbl.pack(side="right")
            return slider, lbl

        self.slider_master, self.lbl_master_vol = _make_slider("Master Volume:", 80, self._on_master_vol_change)
        self.slider_announcement, self.lbl_announcement_vol = _make_slider("Announcements:", 100, self._on_announcement_vol_change)
        self.slider_music, self.lbl_music_vol = _make_slider("Boarding Music:", 50, self._on_music_vol_change)

        btn_stop = ctk.CTkButton(
            card,
            text="⏹  Stop All Audio",
            fg_color="#5a1827",
            hover_color="#7f1d1d",
            text_color="#fca5a5",
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.audio.stop_all
        )
        btn_stop.pack(fill="x", padx=16, pady=(8, 12))

    def _build_telemetry_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="both", expand=True)

        header_lbl = ctk.CTkLabel(
            card,
            text="📊  Live Dataref Telemetry",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        grid = ctk.CTkFrame(card, fg_color=self.c["card_inner"], corner_radius=10)
        grid.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self.telem_labels = {}
        items = [
            ("onground", "On Ground Status:"),
            ("groundspeed", "Ground Speed:"),
            ("alt_agl", "Altitude (AGL):"),
            ("alt_msl", "Altitude (MSL):"),
            ("beacon", "Beacon Light:"),
            ("parkbrake", "Parking Brake:"),
            ("seatbelts", "Seatbelt Signs:")
        ]

        for i, (k, title) in enumerate(items):
            r = i // 2
            c_base = (i % 2) * 2
            lbl_title = ctk.CTkLabel(grid, text=title, font=ctk.CTkFont(family="Segoe UI", size=11), text_color=self.c["fg_muted"])
            lbl_title.grid(row=r, column=c_base, sticky="w", padx=(12, 4), pady=5)

            lbl_val = ctk.CTkLabel(grid, text="--", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#38bdf8")
            lbl_val.grid(row=r, column=c_base + 1, sticky="e", padx=(4, 16), pady=5)
            self.telem_labels[k] = lbl_val

        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

    def _build_soundboard_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="x", pady=(0, 10))

        header_lbl = ctk.CTkLabel(
            card,
            text="🎙️  Manual Cabin Announcement Soundboard",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 8))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 12))

        buttons = [
            ("🛫 Boarding Welcome", "BoardingWelcome", "#0c4a6e", "#0284c7"),
            ("🎵 Boarding Music", "BoardingMusic", "#064e3b", "#059669"),
            ("🚪 Arm Doors", "ArmDoors", "#312e81", "#4f46e5"),
            ("🦺 Safety Briefing", "SafetyBriefing", "#1e3a5f", "#2563eb"),
            ("💺 Crew Seats Takeoff", "CrewSeatsTakeoff", "#451a03", "#d97706"),
            ("🌤️ After Takeoff", "AfterTakeoff", "#0c4a6e", "#0284c7"),
            ("🔔 Fasten Seatbelt", "FastenSeatbelt", "#312e81", "#4f46e5"),
            ("⛰️ Top of Climb", "TopOfClimbPilot", "#1e3a5f", "#2563eb"),
            ("📉 Top of Descent", "TopOfDescentPilot", "#1e3a5f", "#2563eb"),
            ("🛬 Prepare for Landing", "Descent", "#451a03", "#d97706"),
            ("🛬 After Landing", "AfterLanding", "#0c4a6e", "#0284c7"),
            ("🚪 Disarm Doors", "DisarmDoors", "#312e81", "#4f46e5")
        ]

        for i, (label, sound_name, bg_col, hover_col) in enumerate(buttons):
            r = i // 2
            c = i % 2
            btn = ctk.CTkButton(
                grid,
                text=label,
                fg_color=bg_col,
                hover_color=hover_col,
                corner_radius=10,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                height=36,
                command=lambda s=sound_name: self.rule_engine.trigger_sound_manually(s)
            )
            btn.grid(row=r, column=c, sticky="ew", padx=4, pady=4)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    def _build_log_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="both", expand=True)

        header_lbl = ctk.CTkLabel(
            card,
            text="📜  Real-Time Event & Announcement Log",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        self.txt_log = ctk.CTkTextbox(
            card,
            fg_color=self.c["card_inner"],
            text_color="#cbd5e1",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=10,
            border_width=1,
            border_color=self.c["card_border"]
        )
        self.txt_log.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def append_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        def _insert():
            self.txt_log.insert("end", line)
            self.txt_log.see("end")

        self.root.after(0, _insert)

    def _on_dsp_change(self, *args):
        enabled = self.sw_pa_filter.get() == 1
        seg_choice = self.seg_mode.get()
        mode_map = {
            "Overhead PA": "cabin",
            "Intercom": "intercom"
        }
        mode = mode_map.get(seg_choice, "cabin")
        intensity = self.slider_pa_intensity.get() / 100.0

        self.lbl_dsp_val.configure(text=f"{int(self.slider_pa_intensity.get())}%")
        # Updates audio filter immediately in real time on active streaming chunk
        self.audio.set_pa_filter(enabled=enabled, mode=mode, intensity=intensity)
        self._save_settings()

    def _on_master_vol_change(self, val):
        self.lbl_master_vol.configure(text=f"{int(float(val))}%")
        self.audio.set_master_volume(float(val) / 100.0)

    def _on_announcement_vol_change(self, val):
        self.lbl_announcement_vol.configure(text=f"{int(float(val))}%")
        self.audio.set_announcement_volume(float(val) / 100.0)

    def _on_music_vol_change(self, val):
        self.lbl_music_vol.configure(text=f"{int(float(val))}%")
        self.audio.set_music_volume(float(val) / 100.0)

    def _on_airline_selected(self, choice):
        if choice:
            self.rule_engine.set_airline(choice)
            count = len(self.packs.get_sound_files_in_pack(choice))
            self.lbl_airline_info.configure(text=f"Active Pack: {choice} ({count} audio files)")
            self.append_log(f"Selected Airline Sound Pack: {choice} ({count} files)")
            self._save_settings()

    def _on_config_selected(self, choice):
        if choice:
            config_data = self.configs.get_config(choice)
            if config_data:
                self.rule_engine.set_config(config_data)
                filename = config_data.get("_filename", "")
                self.lbl_config_info.configure(text=f"Active Profile: {choice} [{filename}]")
                needed_drefs = self.configs.extract_required_datarefs(choice)
                self.udp.unsubscribe_all()
                for d in needed_drefs:
                    self.udp.subscribe(d, frequency=5)
                self.append_log(f"Active Aircraft Profile: '{choice}' ({len(needed_drefs)} datarefs subscribed)")
                self._save_settings()

    def _on_toggle_auto(self):
        enabled = self.sw_auto_trigger.get() == 1
        self.rule_engine.auto_triggers_enabled = enabled
        status_txt = "ENABLED" if enabled else "DISABLED"
        self.append_log(f"Automatic dataref triggers: {status_txt}")
        self._save_settings()

    def _open_airlines_dir(self):
        os.makedirs(self.packs.base_airlines_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.packs.base_airlines_dir)
        else:
            subprocess.Popen(["xdg-open", self.packs.base_airlines_dir])

    def _open_configs_dir(self):
        os.makedirs(self.configs.configs_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.configs.configs_dir)
        else:
            subprocess.Popen(["xdg-open", self.configs.configs_dir])

    def _refresh_packs(self):
        self.packs.rescan()
        available = self.packs.get_available_airlines()
        self.opt_airline.configure(values=available)
        saved = self.settings.get("selected_airline", "DEFAULT")
        target = saved if saved in available else (available[0] if available else "DEFAULT")
        self.opt_airline.set(target)
        self._on_airline_selected(target)

    def _refresh_configs(self):
        self.configs.rescan()
        available = self.configs.get_config_names()
        self.opt_config.configure(values=available)
        saved = self.settings.get("selected_config")
        target = saved if saved in available else (available[0] if available else "Generic X-Plane 12 Airliner")
        self.opt_config.set(target)
        self._on_config_selected(target)

    def _load_settings(self):
        default_settings = {
            "selected_airline": "DEFAULT",
            "selected_config": "Generic X-Plane 12 Airliner",
            "master_volume": 80,
            "announcement_volume": 100,
            "music_volume": 50,
            "auto_triggers": True,
            "dsp_filter_enabled": True,
            "dsp_filter_mode": "Overhead PA",
            "dsp_filter_intensity": 90
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_settings.update(data)
            except Exception:
                pass
        return default_settings

    def _save_settings(self):
        try:
            self.settings["selected_airline"] = self.opt_airline.get()
            self.settings["selected_config"] = self.opt_config.get()
            self.settings["master_volume"] = int(self.slider_master.get())
            self.settings["announcement_volume"] = int(self.slider_announcement.get())
            self.settings["music_volume"] = int(self.slider_music.get())
            self.settings["auto_triggers"] = (self.sw_auto_trigger.get() == 1)
            self.settings["dsp_filter_enabled"] = (self.sw_pa_filter.get() == 1)
            self.settings["dsp_filter_mode"] = self.seg_mode.get()
            self.settings["dsp_filter_intensity"] = int(self.slider_pa_intensity.get())

            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            pass

    def _restore_settings(self):
        self._refresh_packs()
        self._refresh_configs()

        m_vol = self.settings.get("master_volume", 80)
        self.slider_master.set(m_vol)
        self._on_master_vol_change(m_vol)

        a_vol = self.settings.get("announcement_volume", 100)
        self.slider_announcement.set(a_vol)
        self._on_announcement_vol_change(a_vol)

        mu_vol = self.settings.get("music_volume", 50)
        self.slider_music.set(mu_vol)
        self._on_music_vol_change(mu_vol)

        auto_trig = self.settings.get("auto_triggers", True)
        if auto_trig:
            self.sw_auto_trigger.select()
        else:
            self.sw_auto_trigger.deselect()
        self.rule_engine.auto_triggers_enabled = auto_trig

        # Restore DSP
        dsp_en = self.settings.get("dsp_filter_enabled", True)
        if dsp_en:
            self.sw_pa_filter.select()
        else:
            self.sw_pa_filter.deselect()

        dsp_mode = self.settings.get("dsp_filter_mode", "Overhead PA")
        if dsp_mode not in ["Overhead PA", "Intercom"]:
            dsp_mode = "Overhead PA"
            dsp_en = False
            self.sw_pa_filter.deselect()
        self.seg_mode.set(dsp_mode)

        dsp_int = self.settings.get("dsp_filter_intensity", 90)
        self.slider_pa_intensity.set(dsp_int)
        self._on_dsp_change()

    def _update_loop(self):
        """Periodic loop to update UI connection state and telemetry."""
        if self.udp.is_connected():
            self.pill_conn.configure(
                text=f"🟢 CONNECTED ({self.udp.xplane_ip}:{self.udp.xplane_port})",
                fg_color=self.c["green_bg"],
                text_color=self.c["green"]
            )
        else:
            self.pill_conn.configure(
                text="🔴 WAITING FOR X-PLANE (UDP 49000)",
                fg_color=self.c["red_bg"],
                text_color=self.c["red"]
            )

        phase = self.rule_engine.flight_phase
        self.pill_phase.configure(text=f"PHASE: {phase}")

        values = self.udp.get_all_values()
        
        onground = values.get("sim/flightmodel/failures/onground_any")
        if onground is not None:
            txt = "YES (Ground)" if onground >= 0.5 else "NO (Airborne)"
            self.telem_labels["onground"].configure(text=txt, text_color=self.c["green"] if onground >= 0.5 else "#38bdf8")

        gs = values.get("sim/flightmodel/position/groundspeed")
        if gs is not None:
            kts = gs * 1.94384
            self.telem_labels["groundspeed"].configure(text=f"{kts:.1f} kts")

        agl = values.get("sim/flightmodel/position/y_agl")
        if agl is not None:
            ft = agl * 3.28084
            self.telem_labels["alt_agl"].configure(text=f"{ft:,.0f} ft")

        msl = values.get("sim/flightmodel/position/elevation")
        if msl is not None:
            ft = msl * 3.28084
            self.telem_labels["alt_msl"].configure(text=f"{ft:,.0f} ft")

        beacon = values.get("sim/cockpit2/switches/beacon_on", values.get("AirbusFBW/BeaconLightsOn"))
        if beacon is not None:
            self.telem_labels["beacon"].configure(text="ON" if beacon >= 0.5 else "OFF")

        prk = values.get("sim/cockpit2/controls/parking_brake_ratio", values.get("AirbusFBW/ParkBrake"))
        if prk is not None:
            self.telem_labels["parkbrake"].configure(text=f"{prk * 100:.0f}%")

        belts = values.get("sim/cockpit2/switches/fasten_seat_belts", values.get("AirbusFBW/SeatBeltSignsOn"))
        if belts is not None:
            self.telem_labels["seatbelts"].configure(text="ON" if belts >= 0.5 else "OFF")

        self.root.after(250, self._update_loop)

    def _on_close(self):
        self._save_settings()
        self.audio.stop_all()
        self.rule_engine.stop()
        self.udp.stop()
        self.root.destroy()
