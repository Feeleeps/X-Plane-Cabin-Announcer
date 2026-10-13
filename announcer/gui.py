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
import time
import json
import threading
import subprocess
from datetime import datetime
import tkinter as tk
import customtkinter as ctk

# Configure CustomTkinter default styling
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ToolTip:
    """
    Lightweight, dark-styled hover tooltip for CustomTkinter and Tkinter widgets.
    Binds to both widget and internal canvas/labels to guarantee smooth hover detection.
    """
    def __init__(self, widget, text, delay_ms=400):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window = None
        self._after_id = None

        targets = [self.widget]
        for attr in ("_canvas", "_text_label", "_image_label", "_check_box"):
            inner = getattr(self.widget, attr, None)
            if inner is not None:
                targets.append(inner)

        for target in targets:
            try:
                target.bind("<Enter>", self._on_enter, add="+")
                target.bind("<Leave>", self._on_leave, add="+")
                target.bind("<ButtonPress>", self._on_leave, add="+")
            except Exception:
                pass

    def _on_enter(self, event=None):
        self._schedule()

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except Exception:
            pass

    def _unschedule(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self.tip_window or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            rx = self.widget.winfo_rootx()
            ry = self.widget.winfo_rooty()
            rw = self.widget.winfo_width()
            rh = self.widget.winfo_height()
            screen_w = self.widget.winfo_screenwidth()
            screen_h = self.widget.winfo_screenheight()
        except Exception:
            return

        try:
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.attributes("-topmost", True)

            frame = tk.Frame(tw, bg="#1e293b", bd=1, relief="solid", highlightbackground="#38bdf8", highlightthickness=1)
            frame.pack()
            lbl = tk.Label(
                frame,
                text=self.text,
                justify="left",
                bg="#1e293b",
                fg="#f1f5f9",
                font=("Segoe UI", 9),
                padx=8,
                pady=4
            )
            lbl.pack()

            tw.update_idletasks()
            tip_w = tw.winfo_reqwidth()
            tip_h = tw.winfo_reqheight()

            # Default positioning: below widget
            x = rx + 8
            y = ry + rh + 6

            # Screen boundary detection: prevent overflowing monitor edges
            if x + tip_w > screen_w - 12:
                # Align tooltip's right edge with widget's right edge
                x = rx + rw - tip_w
                if x + tip_w > screen_w - 12:
                    x = screen_w - tip_w - 12
            if x < 10:
                x = 10

            # If overflowing bottom of screen, flip to display above widget
            if y + tip_h > screen_h - 12:
                y = ry - tip_h - 6
            if y < 10:
                y = 10

            tw.wm_geometry(f"+{int(x)}+{int(y)}")
        except Exception:
            self._hide()

    def _hide(self):
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None

def apply_window_icon(root, base_dir):
    """
    Applies the custom aircraft application icon to a Tk/CustomTkinter window.
    Ensures the icon stays active on Windows title bar, taskbar, and Alt-Tab switcher
    even after window resizes, state changes, or Tkinter wrapper re-creations.
    """
    ico_path = os.path.join(base_dir, "app_icon.ico")
    png_path = os.path.join(base_dir, "app_icon.png")

    if sys.platform == "win32" and os.path.exists(ico_path):
        try:
            root.wm_iconbitmap(default=ico_path)
            root.iconbitmap(ico_path)
        except Exception:
            pass

        try:
            import ctypes
            root.update_idletasks()
            wid = root.winfo_id()
            hwnd = ctypes.windll.user32.GetAncestor(wid, 2)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetParent(wid)
            if hwnd:
                user32 = ctypes.windll.user32
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                hicon_big = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                hicon_small = user32.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                if hicon_small:
                    user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)  # WM_SETICON, ICON_SMALL
                if hicon_big:
                    user32.SendMessageW(hwnd, 0x0080, 1, hicon_big)    # WM_SETICON, ICON_BIG
        except Exception:
            pass
    elif os.path.exists(png_path):
        try:
            from PIL import ImageTk, Image
            img = ImageTk.PhotoImage(Image.open(png_path))
            root.iconphoto(True, img)
        except Exception:
            pass

class CabinAnnouncerGUI:
    def __init__(self, root, audio_engine, pack_manager, config_manager, rule_engine, udp_client, base_dir, detector=None, auto_detect_enabled=True):
        self.root = root
        self.audio = audio_engine
        self.packs = pack_manager
        self.configs = config_manager
        self.rule_engine = rule_engine
        self.udp = udp_client
        self.base_dir = base_dir
        self.detector = detector
        self.initial_auto_detect = auto_detect_enabled
        self._detect_counter = 0
        self._last_detected_livery = None
        self._last_detected_acf = None

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

        # System Tray Icon Support
        self.tray_icon = None
        self._tray_thread = None
        self._init_tray()

        # Start periodic GUI update loop
        self._update_loop()

    def _setup_window(self):
        self.root.title("X-Plane Cabin Announcer")
        self.root.geometry("1080x830")
        self.root.minsize(980, 750)
        self.root.configure(fg_color=self.c["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        apply_window_icon(self.root, self.base_dir)

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
        ToolTip(self.pill_phase, "Current flight phase tracked by the rule engine.")

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
        self.pill_conn.pack(side="left", padx=(0, 10))
        ToolTip(self.pill_conn, "Live UDP connection status with X-Plane 12 (Port 49000).")

        # Minimize to System Tray button
        btn_min = ctk.CTkButton(
            status_box,
            text="Minimize to Tray",
            width=120,
            height=28,
            corner_radius=8,
            fg_color=self.c["btn_navy"],
            hover_color=self.c["btn_navy_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._minimize_to_tray
        )
        btn_min.pack(side="left")
        ToolTip(btn_min, "Minimizes the flight deck window to the Windows System Tray.")

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
        ToolTip(self.opt_airline, "Select which airline sound pack to use for announcements.")

        btn_open_air = ctk.CTkButton(row_airline, text="📂", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._open_airlines_dir)
        btn_open_air.grid(row=0, column=2, padx=(0, 4))
        ToolTip(btn_open_air, "Open the airlines folder in Windows File Explorer.")
        btn_ref_air = ctk.CTkButton(row_airline, text="🔄", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._refresh_packs)
        btn_ref_air.grid(row=0, column=3)
        ToolTip(btn_ref_air, "Rescan the airlines folder for newly added sound packs.")

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
        ToolTip(self.opt_config, "Select the aircraft dataref trigger profile for your active aircraft.")

        btn_open_cfg = ctk.CTkButton(row_config, text="📂", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._open_configs_dir)
        btn_open_cfg.grid(row=0, column=2, padx=(0, 4))
        ToolTip(btn_open_cfg, "Open the aircraft configs folder in Windows File Explorer.")
        btn_ref_cfg = ctk.CTkButton(row_config, text="🔄", width=34, corner_radius=8, fg_color=self.c["btn_navy"], hover_color=self.c["btn_navy_hover"], command=self._refresh_configs)
        btn_ref_cfg.grid(row=0, column=3, padx=(0, 4))
        ToolTip(btn_ref_cfg, "Rescan the aircraft configs folder for profile JSON files.")
        btn_edit_cfg = ctk.CTkButton(row_config, text="✏️ Editor", width=68, corner_radius=8, fg_color="#1e3a5f", hover_color="#2563eb", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), command=self._open_web_editor)
        btn_edit_cfg.grid(row=0, column=4)
        ToolTip(btn_edit_cfg, "Open the Web Aircraft Config Editor in your default web browser.")

        self.lbl_config_info = ctk.CTkLabel(card, text="Active Profile: Generic X-Plane 12 Airliner", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=self.c["accent"])
        self.lbl_config_info.pack(anchor="w", padx=16, pady=(1, 8))

        # --- Auto Triggers, Auto-Detect & Reset button ---
        row_actions = ctk.CTkFrame(card, fg_color="transparent")
        row_actions.pack(fill="x", padx=16, pady=(4, 12))

        self.sw_auto_trigger = ctk.CTkSwitch(
            row_actions,
            text="Dataref Triggers",
            command=self._on_toggle_auto,
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.sw_auto_trigger.pack(side="left", padx=(0, 10))
        self.sw_auto_trigger.select()
        ToolTip(self.sw_auto_trigger, "Enable or disable automated announcement triggers based on aircraft altitude, speed, and datarefs.")

        self.sw_auto_detect = ctk.CTkSwitch(
            row_actions,
            text="Auto-Detect Livery/Aircraft",
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.sw_auto_detect.pack(side="left")
        if self.initial_auto_detect:
            self.sw_auto_detect.select()
        else:
            self.sw_auto_detect.deselect()
        ToolTip(self.sw_auto_detect, "Automatically detect the loaded aircraft type and livery from X-Plane and select matching profiles.")

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
        ToolTip(btn_reset, "Resets flight state and re-arms all announcement triggers for a new flight or turnaround without restarting the app.")

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
        ToolTip(self.sw_pa_filter, "Toggle the real-time cabin PA speaker acoustic DSP filter effect.")

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
        ToolTip(self.seg_mode, "Select filter acoustics: Overhead PA (cabin speaker acoustics) or Intercom (crew handset frequency curve).")

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
        ToolTip(self.slider_pa_intensity, "Adjust the wet/dry presence intensity of the cabin PA speaker effect.")

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
        ToolTip(self.slider_master, "Master volume control for all audio playback.")

        self.slider_announcement, self.lbl_announcement_vol = _make_slider("Announcements:", 100, self._on_announcement_vol_change)
        ToolTip(self.slider_announcement, "Audio volume level for cabin announcements.")

        # ACP PA Volume sync switch
        row_sync = ctk.CTkFrame(card, fg_color="transparent")
        row_sync.pack(fill="x", padx=16, pady=(1, 3))
        self.sw_sync_acp = ctk.CTkSwitch(
            row_sync,
            text="Sync Announcement Vol with Cockpit ACP PA Knob",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self.c["fg_muted"],
            progress_color=self.c["accent"],
            command=self._on_toggle_acp_sync
        )
        self.sw_sync_acp.pack(side="left")
        ToolTip(self.sw_sync_acp, "Dynamically sync announcement volume with the cockpit Audio Control Panel (ACP) PA knob in real time.")

        self.slider_music, self.lbl_music_vol = _make_slider("Boarding Music:", 50, self._on_music_vol_change)
        ToolTip(self.slider_music, "Audio volume level for background boarding music.")

        row_stop = ctk.CTkFrame(card, fg_color="transparent")
        row_stop.pack(fill="x", padx=16, pady=(8, 12))

        btn_stop_ann = ctk.CTkButton(
            row_stop,
            text="⏹  Stop Announcement",
            fg_color="#334155",
            hover_color="#475569",
            text_color="#e2e8f0",
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self.audio.stop_announcement
        )
        btn_stop_ann.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ToolTip(btn_stop_ann, "Immediately stops any announcement currently playing.")

        btn_stop_all = ctk.CTkButton(
            row_stop,
            text="⏹  Stop All Audio",
            fg_color="#5a1827",
            hover_color="#7f1d1d",
            text_color="#fca5a5",
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self.audio.stop_all
        )
        btn_stop_all.pack(side="right", fill="x", expand=True, padx=(6, 0))
        ToolTip(btn_stop_all, "Immediately halts all announcements and background boarding music.")

    def _build_telemetry_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self.c["card_bg"], corner_radius=14, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="x", pady=(0, 10))

        header_lbl = ctk.CTkLabel(
            card,
            text="📊  Flight Activity & Boarding Control",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.c["accent"]
        )
        header_lbl.pack(anchor="w", padx=16, pady=(12, 6))

        # Flight Activity / Trigger State Banner
        state_box = ctk.CTkFrame(card, fg_color=self.c["card_inner"], corner_radius=10, border_width=1, border_color="#1e3a5f")
        state_box.pack(fill="x", padx=14, pady=(0, 10))

        row_st = ctk.CTkFrame(state_box, fg_color="transparent")
        row_st.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            row_st,
            text="CURRENT ACTIVITY:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94a3b8"
        ).pack(side="left", padx=(0, 8))

        self.lbl_flight_state = ctk.CTkLabel(
            row_st,
            text="Waiting for telemetry...",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_flight_state.pack(side="left")

        # Boarding Control Button (Moved from Soundboard into Telemetry area)
        row_board = ctk.CTkFrame(card, fg_color="transparent")
        row_board.pack(fill="x", padx=14, pady=(0, 12))

        self.btn_boarding = ctk.CTkButton(
            row_board,
            text="▶ Start Boarding",
            fg_color="#065f46",
            hover_color="#059669",
            corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38,
            command=self._on_boarding_button_click
        )
        self.btn_boarding.pack(fill="x")
        ToolTip(self.btn_boarding, "Starts passenger boarding, dispatches the Boarding Welcome announcement, and begins boarding music. Click again when boarding finishes to complete boarding.")

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
            ("🎵 Boarding Music", "BoardingMusic", "#064e3b", "#059669", "Play or pause background passenger boarding music."),
            ("🚪 Arm Doors", "ArmDoors", "#312e81", "#4f46e5", "Cabin crew announcement to arm slide doors and cross-check."),
            ("🦺 Safety Briefing", "SafetyBriefing", "#1e3a5f", "#2563eb", "Standard passenger emergency equipment and safety briefing demonstration."),
            ("💺 Crew Seats Takeoff", "CrewSeatsTakeoff", "#451a03", "#d97706", "Flight deck or purser alert for cabin crew to take seats for departure."),
            ("📞 Cabin Ready", "CallCabinSecureTakeoff", "#1e3a5f", "#2563eb", "Cabin crew interphone call reporting cabin secure and ready for departure."),
            ("🌤️ After Takeoff", "AfterTakeoff", "#0c4a6e", "#0284c7", "Post-departure welcome announcement upon reaching climb-out altitude."),
            ("🔔 Fasten Seatbelt", "FastenSeatbelt", "#312e81", "#4f46e5", "Seatbelt sign chime and reminder announcement during turbulence."),
            ("🛬 Descent & Cabin Prep", "DescentSeatbelts", "#1e3a5f", "#2563eb", "Commence descent and prepare cabin and galleys for landing."),
            ("💺 Crew Seats Landing", "CrewSeatsLanding", "#451a03", "#d97706", "Flight deck chime and call for cabin crew to take seats for landing."),
            ("🛬 After Landing", "AfterLanding", "#0c4a6e", "#0284c7", "Arrival welcome announcement after runway rollout and taxi-in."),
            ("🚪 Disarm Doors", "DisarmDoors", "#312e81", "#4f46e5", "Cabin crew announcement to disarm slide doors at gate arrival."),
            ("👋 Disembarking", "DisembarkStarted", "#064e3b", "#059669", "Passenger disembarkation and farewell announcement at arrival gate.")
        ]

        for i, (label, sound_name, bg_col, hover_col, tip) in enumerate(buttons):
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
                command=lambda s=sound_name: self._on_soundboard_click(s)
            )
            btn.grid(row=r, column=c, sticky="ew", padx=4, pady=4)
            ToolTip(btn, tip)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    def _on_soundboard_click(self, sound_name):
        self.rule_engine.trigger_sound_manually(sound_name)

    def _on_boarding_button_click(self):
        if not self.rule_engine.boarding_started:
            self.rule_engine.start_boarding()
        elif not self.rule_engine.boarding_completed:
            self.rule_engine.complete_boarding()
        self._update_boarding_button()

    def _update_boarding_button(self):
        if not hasattr(self, "btn_boarding") or not self.btn_boarding.winfo_exists():
            return
        if not self.rule_engine.boarding_started:
            self.btn_boarding.configure(
                text="▶ Start Boarding",
                fg_color="#065f46",
                hover_color="#059669"
            )
        elif not self.rule_engine.boarding_completed:
            self.btn_boarding.configure(
                text="✅ Complete Boarding",
                fg_color="#1e3a8a",
                hover_color="#2563eb"
            )
        else:
            self.btn_boarding.configure(
                text="✓ Boarding Done",
                fg_color="#334155",
                hover_color="#475569"
            )

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
            # If a livery is active in X-Plane, remember this manual mapping for the user's install
            if self.detector and self.detector.detected_livery_name and choice != "DEFAULT":
                self.detector.save_mapping(self.detector.detected_livery_name, choice)
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
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.packs.base_airlines_dir])
        else:
            subprocess.Popen(["xdg-open", self.packs.base_airlines_dir])

    def _open_configs_dir(self):
        os.makedirs(self.configs.configs_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.configs.configs_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.configs.configs_dir])
        else:
            subprocess.Popen(["xdg-open", self.configs.configs_dir])

    def _open_web_editor(self):
        from announcer.editor_server import start_editor_server
        url = start_editor_server(self.base_dir, port=8765, open_browser=True, config_manager=self.configs)
        self.append_log(f"🌐 Opened Visual Config Editor: {url}")

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

    def _on_toggle_acp_sync(self):
        enabled = self.sw_sync_acp.get() == 1
        status_txt = "ENABLED" if enabled else "DISABLED"
        self.append_log(f"ACP PA Volume Knob Sync: {status_txt}")
        self._save_settings()

    def _load_settings(self):
        default_settings = {
            "selected_airline": "DEFAULT",
            "selected_config": "Generic X-Plane 12 Airliner",
            "master_volume": 80,
            "announcement_volume": 100,
            "sync_acp_volume": False,
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
            self.settings["sync_acp_volume"] = (self.sw_sync_acp.get() == 1)
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

        sync_acp = self.settings.get("sync_acp_volume", False)
        if sync_acp:
            self.sw_sync_acp.select()
        else:
            self.sw_sync_acp.deselect()

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

        # Update Flight State Summary Banner
        state_summary = getattr(self.rule_engine, "state_summary", f"Phase: {phase}")
        self.lbl_flight_state.configure(text=state_summary)

        # 3. Live Cockpit ACP PA Volume Knob Synchronization
        if self.sw_sync_acp.get() == 1 and self.udp.is_connected():
            cfg = self.rule_engine.active_config or {}
            hw = cfg.get("hardware_mappings") or {}
            dref_name = hw.get("pa_volume_dataref")
            idx = hw.get("pa_volume_index")

            acp_vol = None
            if dref_name:
                try:
                    if idx is not None and str(idx).strip() != "" and int(idx) > 0:
                        acp_vol = values.get(f"{dref_name}[{idx}]", values.get(dref_name))
                    else:
                        acp_vol = values.get(dref_name)
                except Exception:
                    acp_vol = values.get(dref_name)

            # Fallback 1: ToLiss ACP1 rotary knob index 7
            if acp_vol is None:
                acp_vol = values.get("AirbusFBW/ACP1RotaryPositions[7]", values.get("AirbusFBW/ACP1RotaryPositions"))

            # Fallback 2: Standard X-Plane COM1 Audio Volume (works on all default and 3rd-party planes)
            if acp_vol is None:
                acp_vol = values.get("sim/cockpit2/radios/actuators/audio_volume_com1")

            if acp_vol is not None:
                # Normalize float 0.0 - 1.0 to percentage 0 - 100
                knob_pct = max(0, min(100, int(float(acp_vol) * 100)))
                current_slider = int(self.slider_announcement.get())
                if abs(knob_pct - current_slider) >= 2:
                    self.slider_announcement.set(knob_pct)
                    self.lbl_announcement_vol.configure(text=f"{knob_pct}%")
                    self.audio.set_announcement_volume(knob_pct / 100.0)

        # 4. Flashing Cabin Call indicator & Cockpit Answer Detection
        if self.rule_engine.cabin_call_ringing:
            cfg = self.rule_engine.active_config or {}
            hw = cfg.get("hardware_mappings") or {}
            call_dref = hw.get("cabin_call_annunciator_dataref")

            chk_cab = 0.0
            if call_dref and call_dref in values:
                chk_cab = values.get(call_dref, 0.0)
            else:
                chk_cab = values.get("AirbusFBW/CheckCabin", values.get("AirbusFBW/CabinReady", 0.0))

            if chk_cab >= 0.5:
                self.rule_engine.answer_cabin_call()
            else:
                # Flash the activity banner to notify pilot
                now_sec = int(time.time() * 2)
                if now_sec % 2 == 0:
                    self.lbl_flight_state.configure(text="📞 [CABIN CALL CHIME] Cabin Calling Flight Deck!", text_color="#f59e0b")
                else:
                    self.lbl_flight_state.configure(text="📞 [CABIN CALL CHIME] Press Cockpit Call Button to Answer", text_color="#ef4444")

        # 5. Periodic Auto-Detection of Aircraft & Livery (every ~4 seconds)
        self._detect_counter += 1
        if self._detect_counter >= 16:
            self._detect_counter = 0
            if self.detector and self.sw_auto_detect.get() == 1:
                self._check_auto_detect()

        # 6. Keep Boarding Start / Complete button state in sync
        self._update_boarding_button()

        self.root.after(250, self._update_loop)

    def _check_auto_detect(self):
        """Checks for new aircraft or livery selection from X-Plane and automatically updates."""
        try:
            res = self.detector.run_detection(self.udp)
            new_acf = res.get("acf_path")
            new_livery = res.get("livery_name")
            matched_config = res.get("matched_config")
            matched_airline = res.get("matched_airline")

            # Update Aircraft Profile if changed
            if matched_config and matched_config != self.opt_config.get():
                if new_acf != self._last_detected_acf:
                    self._last_detected_acf = new_acf
                    self.opt_config.set(matched_config)
                    self._on_config_selected(matched_config)
                    self.append_log(f"✨ Auto-detected Aircraft Profile: '{matched_config}'")

            # Update Airline Sound Pack if changed
            if matched_airline and matched_airline != self.opt_airline.get():
                if new_livery != self._last_detected_livery:
                    self._last_detected_livery = new_livery
                    self.opt_airline.set(matched_airline)
                    self._on_airline_selected(matched_airline)
                    self.append_log(f"✨ Auto-detected Airline Pack: '{matched_airline}' (from livery '{new_livery}')")

        except Exception as e:
            pass

    # ---------------------------------------------------------
    # System Tray Integration
    # ---------------------------------------------------------
    def _init_tray(self):
        """Initializes the background system tray icon and context menu."""
        try:
            import pystray
            from PIL import Image

            png_path = os.path.join(self.base_dir, "app_icon.png")
            ico_path = os.path.join(self.base_dir, "app_icon.ico")
            img = None
            if os.path.exists(png_path):
                img = Image.open(png_path)
            elif os.path.exists(ico_path):
                img = Image.open(ico_path)

            if not img:
                return

            menu = pystray.Menu(
                pystray.MenuItem("Show Flight Deck", self._on_tray_show, default=True),
                pystray.MenuItem("Stop Current Announcement", self._on_tray_stop_ann),
                pystray.MenuItem("Stop All Audio", self._on_tray_stop_all),
                pystray.MenuItem("Open Web Config Editor", self._on_tray_web_editor),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._on_tray_quit)
            )
            self.tray_icon = pystray.Icon("CabinAnnouncer", img, "X-Plane Cabin Announcer", menu)
        except Exception:
            pass

    def _start_tray_thread(self):
        """Starts the system tray background message loop thread if not already running."""
        if self.tray_icon is None:
            self._init_tray()
        if self.tray_icon and not (self._tray_thread and self._tray_thread.is_alive()):
            self._tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self._tray_thread.start()

    def _on_tray_show(self, icon=None, item=None):
        self.root.after(0, self._restore_from_tray)

    def _on_tray_stop_ann(self, icon=None, item=None):
        self.root.after(0, self.audio.stop_announcement)
        self.append_log("⏹️ Announcement stopped from system tray.")

    def _on_tray_stop_all(self, icon=None, item=None):
        self.root.after(0, self.audio.stop_all)
        self.append_log("⏹️ All audio stopped from system tray.")

    def _on_tray_web_editor(self, icon=None, item=None):
        self.root.after(0, self._open_web_editor)

    def _on_tray_quit(self, icon=None, item=None):
        self.root.after(0, self._on_close)

    def _minimize_to_tray(self):
        """Hides the flight deck window completely from the screen and taskbar into the system tray."""
        self._start_tray_thread()
        self.root.withdraw()
        self.append_log("📌 Minimized to system tray. Double-click or right-click the tray icon to restore.")

    def _minimize_window(self):
        """Minimizes the flight deck window (routes to system tray)."""
        self._minimize_to_tray()

    def _restore_from_tray(self):
        """Restores the flight deck window from the system tray and brings it to front."""
        self.root.deiconify()
        self.root.lift()
        apply_window_icon(self.root, self.base_dir)
        if sys.platform == "win32":
            try:
                import ctypes
                wid = self.root.winfo_id()
                hwnd = ctypes.windll.user32.GetAncestor(wid, 2) or ctypes.windll.user32.GetParent(wid)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        self.append_log("✨ Restored Flight Deck from system tray.")

    def _on_close(self):
        self._save_settings()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.audio.stop_all()
        self.rule_engine.stop()
        self.udp.stop()
        self.root.destroy()
