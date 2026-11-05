"""Draws the picture behind the Mac installer window (UltraFrontEnd.dmg): the app on the left, an arrow, Applications on the right.

    python tools/make_dmg_background.py OUT_DIR      ->  OUT_DIR/background.png (640x420) and background@2x.png

build-mac.sh runs it, and dmg-settings.py puts the icons where this picture expects them (ICONS below).
Finder writes the icon names in white in Dark Mode and in black in Light Mode, on top of this picture, so the strip
under the icons is a middle tone where both can be read.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 640, 420
ICONS = {"app": (170, 190), "apps": (470, 190)}  # icon centres, in window points (dmg-settings.py uses the same)
FONTS = ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/segoeui.ttf"]
BOLD = ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/segoeuib.ttf"]


def font(size, names, weight=None):
    for n in names:
        if os.path.exists(n):
            f = ImageFont.truetype(n, size)
            if weight and n.endswith("SFNS.ttf"):
                try:
                    f.set_variation_by_axes([weight])
                except Exception:
                    pass
            return f
    return ImageFont.load_default(size)


def draw(scale):
    s = lambda v: int(round(v * scale))
    w, h = s(W), s(H)
    img = Image.new("RGB", (w, h))
    px = img.load()
    top, bottom = (13, 22, 44), (7, 12, 26)  # the app's navy
    for y in range(h):
        t = y / (h - 1)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    # soft blue glow behind the app icon
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse([s(ICONS["app"][0] - 120), s(ICONS["app"][1] - 110), s(ICONS["app"][0] + 120), s(ICONS["app"][1] + 110)], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(s(50)))
    img = Image.composite(Image.new("RGB", (w, h), (56, 189, 248)), img, glow)
    d = ImageDraw.Draw(img, "RGBA")
    # the strip the icon names sit on: readable with white (Dark Mode) and black (Light Mode) names
    y0, y1 = ICONS["app"][1] + 68, ICONS["app"][1] + 98
    for cx in (ICONS["app"][0], ICONS["apps"][0]):
        d.rounded_rectangle([s(cx - 82), s(y0), s(cx + 82), s(y1)], radius=s(15), fill=(122, 134, 156, 255))
    # title
    title = font(s(24), BOLD, 700)
    text = "Drag to Applications to install"
    tw = d.textlength(text, font=title)
    d.text(((w - tw) / 2, s(34)), text, font=title, fill=(255, 255, 255))
    # arrow from the app to Applications
    ax0, ax1, ay = ICONS["app"][0] + 92, ICONS["apps"][0] - 92, ICONS["app"][1]
    d.rounded_rectangle([s(ax0), s(ay - 4), s(ax1 - 14), s(ay + 4)], radius=s(4), fill=(56, 189, 248, 255))
    d.polygon([(s(ax1), s(ay)), (s(ax1 - 24), s(ay - 17)), (s(ax1 - 24), s(ay + 17))], fill=(56, 189, 248, 255))
    # first-open note (the app isn't from an identified developer)
    small = font(s(12.5), FONTS, 400)
    for i, line in enumerate(["First time: if macOS says it can't check the app, open System Settings ›",
                              "Privacy & Security and choose Open Anyway. You'll only need to do this once."]):
        lw = d.textlength(line, font=small)
        d.text(((w - lw) / 2, s(352 + i * 19)), line, font=small, fill=(176, 188, 210))
    return img


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    draw(1).save(os.path.join(out, "background.png"))
    draw(2).save(os.path.join(out, "background@2x.png"))
