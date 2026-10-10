"""
Modern Startup Splash Screen for X-Plane Cabin Announcer using CustomTkinter.
Displays initialization progress, auto-detected aircraft & airline livery,
and allows pre-flight configuration before launching into the main flight deck.
"""

import os
import sys
import time
import customtkinter as ctk
from PIL import Image

class SplashScreen:
    def __init__(self, root, detector, pack_manager, config_manager, base_dir, on_complete):
        self.root = root
        self.detector = detector
        self.packs = pack_manager
        self.configs = config_manager
        self.base_dir = base_dir
        self.on_complete = on_complete

        self.root.title("X-Plane Cabin Announcer - Starting")
        self.root.geometry("560x520")
        self.root.resizable(False, False)
        self.root.configure(fg_color="#0d1117")

        # Set Window icon
        ico_path = os.path.join(self.base_dir, "app_icon.ico")
        png_path = os.path.join(self.base_dir, "app_icon.png")
        if sys.platform == "win32" and os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass
        elif os.path.exists(png_path):
            try:
                from PIL import ImageTk, Image
                img = ImageTk.PhotoImage(Image.open(png_path))
                self.root.iconphoto(False, img)
            except Exception:
                pass

        # Center on screen
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
            "green": "#10b981"
        }

        self.detected_data = {}
        self.auto_launch_seconds = 4
        self._countdown_running = True

        self._build_widgets()
        self.root.after(100, self._run_initialization)

    def _center_window(self):
        self.root.update_idletasks()
        w = 560
        h = 520
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_widgets(self):
        # Outer Card Container
        card = ctk.CTkFrame(self.root, fg_color=self.c["card_bg"], corner_radius=16, border_width=1, border_color=self.c["card_border"])
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header with Logo & Title
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        png_path = os.path.join(self.base_dir, "app_icon.png")
        if os.path.exists(png_path):
            try:
                pil_img = Image.open(png_path)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(54, 54))
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
            text="Fenix A320 Audio System  •  Auto-Detection & Setup",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.c["fg_muted"]
        )
        lbl_sub.pack(anchor="w")

        # Progress bar & status label
        self.lbl_status = ctk.CTkLabel(
            card,
            text="Initializing Audio Engine & DSP...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.c["accent"]
        )
        self.lbl_status.pack(anchor="w", padx=24, pady=(12, 4))

        self.progress_bar = ctk.CTkProgressBar(
            card,
            progress_color=self.c["accent"],
            fg_color="#21262d",
            corner_radius=6,
            height=10
        )
        self.progress_bar.pack(fill="x", padx=24, pady=(0, 14))
        self.progress_bar.set(0.15)

        # Detection Summary Card
        self.detect_frame = ctk.CTkFrame(card, fg_color=self.c["card_inner"], corner_radius=12, border_width=1, border_color=self.c["card_border"])
        self.detect_frame.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        lbl_detect_title = ctk.CTkLabel(
            self.detect_frame,
            text="🔍  Pre-Flight Detection Results",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.c["fg"]
        )
        lbl_detect_title.pack(anchor="w", padx=16, pady=(10, 8))

        # Result Rows
        def _make_row(parent, title):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(row, text=title, width=135, anchor="w", text_color=self.c["fg_muted"], font=ctk.CTkFont(family="Segoe UI", size=11)).pack(side="left")
            val_lbl = ctk.CTkLabel(row, text="Searching...", anchor="w", text_color="#cbd5e1", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
            val_lbl.pack(side="left", fill="x", expand=True)
            return val_lbl

        self.lbl_res_sim = _make_row(self.detect_frame, "X-Plane Installation:")
        self.lbl_res_acf = _make_row(self.detect_frame, "Detected Aircraft:")
        self.lbl_res_livery = _make_row(self.detect_frame, "Detected Livery:")
        self.lbl_res_airline = _make_row(self.detect_frame, "Matched Sound Pack:")

        # Auto-detect checkbox
        self.sw_auto_detect = ctk.CTkSwitch(
            self.detect_frame,
            text="Enable Continuous Flight & Livery Auto-Detection",
            progress_color=self.c["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.sw_auto_detect.pack(anchor="w", padx=16, pady=(10, 10))
        self.sw_auto_detect.select()

        # Action Button & Auto-Launch Countdown
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        self.btn_launch = ctk.CTkButton(
            btn_frame,
            text="🚀  Launch Flight Deck",
            fg_color="#0284c7",
            hover_color="#0369a1",
            corner_radius=10,
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._finish_and_launch
        )
        self.btn_launch.pack(fill="x")

    def _run_initialization(self):
        # Step 1: Scan packs and configs
        self.progress_bar.set(0.35)
        self.lbl_status.configure(text="Scanning airline sound packs and aircraft profiles...")
        self.root.update()
        time.sleep(0.15)

        # Step 2: Auto-Detection
        self.progress_bar.set(0.70)
        self.lbl_status.configure(text="Scanning active X-Plane 12 flight and liveries...")
        self.root.update()

        self.detected_data = self.detector.run_detection()

        # Update UI with detected values
        xplane_path = self.detected_data.get("xplane_dir") or "Not found"
        self.lbl_res_sim.configure(text=xplane_path)

        acf = self.detected_data.get("matched_config") or "Generic X-Plane 12 Airliner"
        acf_path = self.detected_data.get("acf_path")
        acf_display = f"{acf}"
        if acf_path:
            acf_display += f" ({os.path.basename(acf_path)})"
        self.lbl_res_acf.configure(text=acf_display, text_color="#38bdf8")

        livery = self.detected_data.get("livery_name") or "Default Livery"
        self.lbl_res_livery.configure(text=livery)

        airline = self.detected_data.get("matched_airline") or "DEFAULT"
        self.lbl_res_airline.configure(text=f"✈️ {airline}", text_color=self.c["green"])

        self.progress_bar.set(1.0)
        self.lbl_status.configure(text="System ready! Launching flight deck...", text_color=self.c["green"])

        # Start auto-countdown
        self._countdown_loop()

    def _countdown_loop(self):
        if not self._countdown_running:
            return
        if self.auto_launch_seconds > 0:
            self.btn_launch.configure(text=f"🚀  Launch Flight Deck ({self.auto_launch_seconds}s)")
            self.auto_launch_seconds -= 1
            self.root.after(1000, self._countdown_loop)
        else:
            self._finish_and_launch()

    def _finish_and_launch(self):
        self._countdown_running = False
        auto_detect_enabled = self.sw_auto_detect.get() == 1
        self.on_complete(self.detected_data, auto_detect_enabled)
