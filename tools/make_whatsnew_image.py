"""Makes a release's What's new picture: the intro's wave glow (app/assets/intro-wave.jpg) in a colour of its own.

    python tools/make_whatsnew_image.py 1.2.4            -> assets/whatsnew/1.2.4.jpg, the next colour round the wheel
    python tools/make_whatsnew_image.py 1.2.4 --hue 140  -> that hue (0-360) instead

Each release takes the next hue from a hand-picked list of strong colours (PALETTE) whose neighbours are far apart;
after the list it steps a golden angle (about 137.5 degrees) at a time. The order is the releases' version order. tools/release.py checks the picture is
there.
"""
import argparse
import os
import re

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAVE = os.path.join(ROOT, "app", "assets", "intro-wave.jpg")
OUT = os.path.join(ROOT, "assets", "whatsnew")
WAVE_HUE = 223  # the wave's own blue
# Hand-picked strong hues, in an order where neighbours are always far apart (1.0.0 keeps the blue). Past the list we
# carry on by golden-angle steps. Hues in the dark-red / olive / brown range are left out: they look dirty on black.
PALETTE = [220, 0, 130, 270, 30, 190, 310, 78, 165, 55, 245, 345]  # blue red green violet orange cyan magenta lime teal yellow indigo rose
STEP = 137.508


def key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def hue_for(version):
    """The version's place among the releases with a picture (and itself), turned into a hue."""
    known = {f[:-4] for f in os.listdir(OUT) if f.endswith(".jpg")} if os.path.isdir(OUT) else set()
    order = sorted(known | {version}, key=key)
    i = order.index(version)
    if i < len(PALETTE):
        return PALETTE[i]
    return (PALETTE[-1] + STEP * (i - len(PALETTE) + 1)) % 360


def make(version, hue):
    im = Image.open(WAVE).convert("RGB")
    h, s, v = im.convert("HSV").split()
    shift = round((hue - WAVE_HUE) % 360 * 255 / 360)
    h = h.point(lambda x: (x + shift) % 256)
    out = Image.merge("HSV", (h, s, v)).convert("RGB").resize((1280, 549), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{version}.jpg")
    out.save(path, quality=88, optimize=True, progressive=True)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version")
    ap.add_argument("--hue", type=float, help="0-360; default: the next colour round the wheel")
    a = ap.parse_args()
    hue = a.hue if a.hue is not None else hue_for(a.version)
    print(f"{make(a.version, hue)} (hue {hue:.0f})")


if __name__ == "__main__":
    main()
