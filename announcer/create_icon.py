"""
Generates a professional multi-resolution Windows .ico icon for X-Plane Cabin Announcer.
Features an aircraft silhouette with sound waves and an aviation dark/cyan badge.
"""

import os
from PIL import Image, ImageDraw

def create_app_icon(output_path):
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Rounded App Badge Background
    pad = 12
    badge_box = [pad, pad, size - pad, size - pad]
    # Dark blue-slate rounded square
    draw.rounded_rectangle(badge_box, radius=48, fill=(16, 22, 34, 255), outline=(56, 189, 248, 220), width=6)

    # Subtle inner gradient ring
    inner_box = [pad + 10, pad + 10, size - pad - 10, size - pad - 10]
    draw.rounded_rectangle(inner_box, radius=40, outline=(30, 41, 59, 180), width=4)

    # 2. Sound Wave Arcs (Cabin Announcement broadcast)
    arc_center = (size // 2, size // 2 + 30)
    
    # Wave 1 (outer)
    draw.arc([arc_center[0] - 80, arc_center[1] - 80, arc_center[0] + 80, arc_center[1] + 80],
             start=200, end=340, fill=(56, 189, 248, 120), width=7)
    # Wave 2 (middle)
    draw.arc([arc_center[0] - 56, arc_center[1] - 56, arc_center[0] + 56, arc_center[1] + 56],
             start=195, end=345, fill=(56, 189, 248, 200), width=8)
    # Wave 3 (inner)
    draw.arc([arc_center[0] - 32, arc_center[1] - 32, arc_center[0] + 32, arc_center[1] + 32],
             start=190, end=350, fill=(186, 230, 253, 240), width=7)

    # 3. Aircraft Silhouette (Climbing Jet)
    cx, cy = size // 2, size // 2 - 20
    # Clean modern airliner polygon
    fuselage = [
        (cx, cy - 58),       # Nose tip
        (cx + 10, cy - 35),  # Forward cabin
        (cx + 12, cy + 30),  # Mid cabin
        (cx + 8, cy + 55),   # Aft fuselage
        (cx + 28, cy + 72),  # Right tail fin tip
        (cx + 22, cy + 76),  # Right tail trailing
        (cx + 4, cy + 68),   # Tail root
        (cx, cy + 75),       # Tail cone
        (cx - 4, cy + 68),   # Tail root
        (cx - 22, cy + 76),  # Left tail trailing
        (cx - 28, cy + 72),  # Left tail fin tip
        (cx - 8, cy + 55),   # Aft fuselage
        (cx - 12, cy + 30),  # Mid cabin
        (cx - 10, cy - 35),  # Forward cabin
    ]
    draw.polygon(fuselage, fill=(240, 246, 252, 255))

    # Swept Wings
    wings = [
        (cx, cy - 10),       # Wing root leading
        (cx + 82, cy + 22),  # Right wing tip
        (cx + 78, cy + 32),  # Right wing tip trailing
        (cx + 10, cy + 18),  # Right wing root trailing
        (cx, cy + 20),       # Center
        (cx - 10, cy + 18),  # Left wing root trailing
        (cx - 78, cy + 32),  # Left wing tip trailing
        (cx - 82, cy + 22),  # Left wing tip
    ]
    draw.polygon(wings, fill=(240, 246, 252, 255))

    # Accent Engine Pods (Aviation cyan)
    draw.ellipse([cx + 26, cy + 10, cx + 36, cy + 26], fill=(56, 189, 248, 255))
    draw.ellipse([cx - 36, cy + 10, cx - 26, cy + 26], fill=(56, 189, 248, 255))

    # Cockpit Window Stripe
    draw.polygon([(cx - 7, cy - 34), (cx + 7, cy - 34), (cx + 5, cy - 30), (cx - 5, cy - 30)], fill=(30, 41, 59, 255))

    # Save as multi-resolution .ico
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    icon_images = [img.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    img.save(output_path, format="ICO", sizes=sizes)

    png_path = os.path.splitext(output_path)[0] + ".png"
    img.save(png_path, format="PNG")
    print(f"Generated icon: {output_path} and {png_path}")

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "app_icon.ico"
    create_app_icon(out)
