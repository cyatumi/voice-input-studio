"""Generate app icons for Voice Input Studio.

App icon  (assets/app.ico):
  White microphone on deep blue→indigo gradient circle, cyan sound waves,
  red REC dot. Used by the running application (tray, taskbar, window title).

Installer icon  (assets/installer.ico):
  White download arrow + small mic on orange→amber gradient circle, green
  checkmark badge. Used only by VoiceInputStudio-Setup.exe so users can
  instantly tell the setup file apart from the running app.

Run once before building: `python scripts\\make_icon.py`
Outputs:
  - assets\\app.ico        (multi-res: 16, 24, 32, 48, 64, 128, 256)
  - assets\\app.png        (256×256 preview)
  - assets\\installer.ico  (same resolutions)
  - assets\\installer.png  (256×256 preview)
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def _draw_icon(size: int) -> Image.Image:
    """Render the app icon at a single resolution. Returns an RGBA image."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    # --- Background: gradient circle ---------------------------------------
    # Pillow has no built-in gradient fill, so render a vertical gradient onto
    # a temp layer, then mask it to a circle.
    grad = Image.new("RGBA", (size, size))
    top = (30, 64, 175)        # deep blue
    bottom = (49, 46, 129)     # indigo
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        ImageDraw.Draw(grad).line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Circular mask (slightly inset so we get a soft edge)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    img.paste(grad, (0, 0), mask)

    # Subtle inner highlight on top half for depth
    if size >= 48:
        highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hd = ImageDraw.Draw(highlight)
        hd.ellipse(
            (size * 0.12, size * 0.06, size * 0.88, size * 0.55),
            fill=(255, 255, 255, 35),
        )
        highlight = highlight.filter(ImageFilter.GaussianBlur(radius=size * 0.04))
        img.alpha_composite(highlight)

    # --- Sound waves (left & right) ----------------------------------------
    wave_color = (125, 211, 252, 255)  # sky-300
    wave_w = max(2, int(size * 0.025))
    cx, cy = size / 2, size / 2
    for i, radius_factor in enumerate((0.30, 0.40)):
        r = size * radius_factor
        bbox = (cx - r, cy - r, cx + r, cy + r)
        # Left arc
        draw.arc(bbox, start=135, end=225, fill=wave_color, width=wave_w)
        # Right arc
        draw.arc(bbox, start=-45, end=45, fill=wave_color, width=wave_w)

    # --- Microphone --------------------------------------------------------
    mic_color = (245, 250, 255, 255)
    mic_shadow = (15, 20, 50, 90)

    mic_w = size * 0.30
    mic_h = size * 0.42
    mic_x = (size - mic_w) / 2
    mic_y = size * 0.18

    # Drop shadow
    if size >= 48:
        shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle(
            (mic_x + 2, mic_y + 4, mic_x + mic_w + 2, mic_y + mic_h + 4),
            radius=int(mic_w * 0.45),
            fill=mic_shadow,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=size * 0.012))
        img.alpha_composite(shadow)

    # Mic body
    draw.rounded_rectangle(
        (mic_x, mic_y, mic_x + mic_w, mic_y + mic_h),
        radius=int(mic_w * 0.45),
        fill=mic_color,
    )

    # Grille lines (only on bigger icons)
    if size >= 48:
        grille_color = (30, 64, 175, 170)
        line_w = max(1, int(size * 0.012))
        for fraction in (0.30, 0.45, 0.60):
            ly = mic_y + mic_h * fraction
            draw.line(
                (mic_x + mic_w * 0.20, ly, mic_x + mic_w * 0.80, ly),
                fill=grille_color,
                width=line_w,
            )

    # Stand: curve + stem + base
    stand_color = mic_color
    stem_w = max(2, int(size * 0.035))
    # Stem from mic bottom down to base
    stem_top = mic_y + mic_h + size * 0.04
    stem_bottom = size * 0.82
    draw.line((cx, stem_top, cx, stem_bottom), fill=stand_color, width=stem_w)
    # Horizontal base
    base_half = size * 0.13
    draw.line(
        (cx - base_half, stem_bottom, cx + base_half, stem_bottom),
        fill=stand_color,
        width=stem_w,
    )
    # Yoke arc under the mic (the curved bracket)
    yoke_r = mic_w * 0.62
    yoke_bbox = (cx - yoke_r, mic_y + mic_h * 0.45,
                 cx + yoke_r, mic_y + mic_h + yoke_r * 0.9)
    draw.arc(yoke_bbox, start=0, end=180, fill=stand_color, width=stem_w)

    # --- REC dot (upper-right) --------------------------------------------
    if size >= 32:
        dot_r = size * 0.13
        dot_cx = size * 0.78
        dot_cy = size * 0.22
        # White ring
        draw.ellipse(
            (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
            fill=(255, 255, 255, 255),
        )
        # Red core
        inner = dot_r * 0.72
        draw.ellipse(
            (dot_cx - inner, dot_cy - inner, dot_cx + inner, dot_cy + inner),
            fill=(239, 68, 68, 255),
        )

    return img


def _draw_installer_icon(size: int) -> Image.Image:
    """Installer icon: orange→amber gradient circle, download arrow, small mic,
    green checkmark badge in the lower-right corner."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    # --- Background: orange→amber gradient circle ----------------------------
    grad = Image.new("RGBA", (size, size))
    top_c = (234, 88, 12)      # orange-600
    bot_c = (217, 119, 6)      # amber-600
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(top_c[0] * (1 - t) + bot_c[0] * t)
        g = int(top_c[1] * (1 - t) + bot_c[1] * t)
        b = int(top_c[2] * (1 - t) + bot_c[2] * t)
        ImageDraw.Draw(grad).line([(0, y), (size, y)], fill=(r, g, b, 255))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    img.paste(grad, (0, 0), mask)

    # Subtle highlight
    if size >= 48:
        hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(hl).ellipse(
            (size * 0.12, size * 0.06, size * 0.88, size * 0.55),
            fill=(255, 255, 255, 30),
        )
        hl = hl.filter(ImageFilter.GaussianBlur(radius=size * 0.04))
        img.alpha_composite(hl)

    # --- Download arrow (↓) --------------------------------------------------
    arrow_color = (255, 255, 255, 255)
    cx = size / 2
    shaft_w = max(2, int(size * 0.12))
    shaft_top = size * 0.12
    shaft_bot = size * 0.52
    # Vertical shaft
    draw.rectangle(
        (cx - shaft_w / 2, shaft_top, cx + shaft_w / 2, shaft_bot),
        fill=arrow_color,
    )
    # Arrowhead (triangle pointing down)
    head_half = size * 0.22
    head_tip_y = size * 0.68
    head_base_y = size * 0.50
    draw.polygon(
        [
            (cx - head_half, head_base_y),
            (cx + head_half, head_base_y),
            (cx, head_tip_y),
        ],
        fill=arrow_color,
    )
    # Horizontal base line under arrow
    base_y = size * 0.72
    base_half = size * 0.26
    line_w = max(2, int(size * 0.06))
    draw.rectangle(
        (cx - base_half, base_y, cx + base_half, base_y + line_w),
        fill=arrow_color,
    )

    # --- Small mic silhouette below base line (only on larger sizes) ---------
    if size >= 48:
        mic_w = size * 0.14
        mic_h = size * 0.10
        mic_x = cx - mic_w / 2
        mic_y = base_y + line_w + size * 0.03
        draw.rounded_rectangle(
            (mic_x, mic_y, mic_x + mic_w, mic_y + mic_h),
            radius=int(mic_w * 0.45),
            fill=(255, 255, 255, 200),
        )

    # --- Green checkmark badge (lower-right) ---------------------------------
    if size >= 32:
        badge_r = size * 0.20
        bx = size * 0.76
        by = size * 0.76
        # White ring
        draw.ellipse(
            (bx - badge_r, by - badge_r, bx + badge_r, by + badge_r),
            fill=(255, 255, 255, 255),
        )
        # Green fill
        inner_r = badge_r * 0.80
        draw.ellipse(
            (bx - inner_r, by - inner_r, bx + inner_r, by + inner_r),
            fill=(34, 197, 94, 255),   # green-500
        )
        # Check mark (two lines)
        if size >= 48:
            ck_w = max(2, int(size * 0.025))
            # Left leg of check
            draw.line(
                (bx - inner_r * 0.55, by,
                 bx - inner_r * 0.10, by + inner_r * 0.50),
                fill=(255, 255, 255, 255), width=ck_w,
            )
            # Right leg
            draw.line(
                (bx - inner_r * 0.10, by + inner_r * 0.50,
                 bx + inner_r * 0.55, by - inner_r * 0.40),
                fill=(255, 255, 255, 255), width=ck_w,
            )

    return img


def _save_ico(images: list, path: "Path", sizes: tuple) -> None:
    """Save a list of RGBA images as a multi-resolution .ico file."""
    images[-1].save(
        path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    sizes = (16, 24, 32, 48, 64, 128, 256)

    # --- App icon (blue mic) -------------------------------------------------
    app_images = [_draw_icon(s) for s in sizes]
    ico_path = out_dir / "app.ico"
    _save_ico(app_images, ico_path, sizes)
    app_images[-1].save(out_dir / "app.png", format="PNG")
    print(f"Wrote {ico_path}  (sizes: {', '.join(str(s) for s in sizes)})")
    print(f"Wrote {out_dir / 'app.png'}")

    # --- Installer icon (orange arrow) ---------------------------------------
    inst_images = [_draw_installer_icon(s) for s in sizes]
    inst_ico_path = out_dir / "installer.ico"
    _save_ico(inst_images, inst_ico_path, sizes)
    inst_images[-1].save(out_dir / "installer.png", format="PNG")
    print(f"Wrote {inst_ico_path}")
    print(f"Wrote {out_dir / 'installer.png'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
