"""The card over the game for add-ons (api.hud), drawn here and put on screen as a picture with see-through pixels.

A layered window (UpdateLayeredWindow, per-pixel alpha) is the one way Windows shows a soft-edged, see-through panel
over a game: no browser, so its rounded ends are smooth, the glass is see-through and the shadow is soft. It never takes
the focus or the clicks (WS_EX_TRANSPARENT | WS_EX_NOACTIVATE) and isn't in the taskbar or Alt+Tab (WS_EX_TOOLWINDOW).

It asks the helper for its cards every two seconds (/api/addon-hud) and redraws the bar about 30 times a second while
a light sweeps along it. It goes once there's nothing to show or the game has ended.
"""
import ctypes
import ctypes.wintypes as W
import io
import json
import math
import os
import threading
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32


def font(name, size):
    for f in (name, "segoeui.ttf"):
        try:
            return ImageFont.truetype(os.path.join(FONTS, f), size)
        except OSError:
            pass
    return ImageFont.load_default()


def ease(t):
    return 1 - (1 - t) ** 3


class Card:
    """Draws the pill: a soft shadow, frosted glass, a round picture, one line of words and a thin glowing bar."""

    def __init__(self, url):
        self.url = url
        self.pics = {}

    def picture(self, path, d):
        key = (path, d)
        if key not in self.pics:
            pic = None
            if path:
                try:
                    with urllib.request.urlopen(self.url + path, timeout=5) as r:
                        pic = Image.open(io.BytesIO(r.read())).convert("RGBA")
                except Exception:
                    pic = None
            tile = Image.new("RGBA", (d, d), (0, 0, 0, 0))
            light = Image.new("RGBA", (d, d))
            ImageDraw.Draw(light).ellipse((0, 0, d - 1, d - 1), fill=(232, 236, 242, 255))
            if pic:  # the print on a light round tile, so dark filament shows
                pic.thumbnail((int(d * .86), int(d * .86)), Image.LANCZOS)
                light.alpha_composite(pic, ((d - pic.width) // 2, (d - pic.height) // 2))
            else:  # no picture: a printer drawn in lines on a glass tile
                light = Image.new("RGBA", (d, d))
                g = ImageDraw.Draw(light)
                g.ellipse((0, 0, d - 1, d - 1), fill=(255, 255, 255, 40))
                w = max(2, d // 18)
                g.rectangle((d * .32, d * .24, d * .68, d * .4), outline=(255, 255, 255, 235), width=w)
                g.rounded_rectangle((d * .2, d * .4, d * .8, d * .66), radius=d * .06, outline=(255, 255, 255, 235), width=w)
                g.rectangle((d * .32, d * .56, d * .68, d * .78), outline=(255, 255, 255, 235), width=w)
            mask = Image.new("L", (d, d), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
            tile.paste(light, (0, 0), mask)
            self.pics[key] = tile
        return self.pics[key]

    def layout(self, items, rem):
        """The parts that don't move (drawn at twice the size, then halved, for smooth edges), and where the bar goes."""
        S = 2
        h, pad = int(6.2 * rem), int(1.6 * rem)  # pad: room for the shadow
        title, rest = font("seguisb.ttf", int(2.0 * rem * S)), font("segoeui.ttf", int(2.0 * rem * S))
        cards = []
        for it in items:
            t, sub = it.get("text") or "", f"  ·  {it['sub']}" if it.get("sub") else ""
            tw, sw = title.getlength(t) / S, rest.getlength(sub) / S
            w = int(.9 * rem + 4.4 * rem + 1.2 * rem + tw + sw + 2.4 * rem)
            cards.append((it, t, sub, w))
        W_ = max(c[3] for c in cards) + pad * 2
        H_ = len(cards) * h + (len(cards) - 1) * int(.8 * rem) + pad * 2
        base = Image.new("RGBA", (W_ * S, H_ * S), (0, 0, 0, 0))
        shadow = Image.new("L", base.size, 0)
        bars, y = [], pad
        for it, t, sub, w in cards:
            box = (pad * S, y * S, (pad + w) * S, (y + h) * S)
            ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + int(.5 * rem * S), box[2], box[3] + int(.5 * rem * S)), radius=h * S // 2, fill=150)
            y += h + int(.8 * rem)
        base.putalpha(shadow.filter(ImageFilter.GaussianBlur(rem * S * .9)))
        base = Image.merge("RGBA", (*Image.new("RGB", base.size, (0, 0, 0)).split(), base.getchannel("A")))
        y = pad
        for it, t, sub, w in cards:
            x0, y0, x1, y1 = pad * S, y * S, (pad + w) * S, (y + h) * S
            r = (y1 - y0) // 2
            mask = Image.new("L", base.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1, y1), radius=r, fill=255)
            # frosted glass: a dark see-through fill with a soft blue glow at the left and green at the right
            glass = Image.new("RGBA", base.size, (24, 26, 32, 196))
            glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            gd.ellipse((x0 - r, y0 - r * 2, x0 + r * 4, y1 + r), fill=(110, 150, 255, 60))
            gd.ellipse((x1 - r * 4, y0, x1 + r, y1 + r * 2), fill=(80, 240, 190, 40))
            glass.alpha_composite(glow.filter(ImageFilter.GaussianBlur(r)))
            shine = Image.new("RGBA", base.size, (0, 0, 0, 0))  # light along the top half
            for i in range((y1 - y0) // 2):
                ImageDraw.Draw(shine).line((x0, y0 + i, x1, y0 + i), fill=(255, 255, 255, int(26 * (1 - i / ((y1 - y0) / 2)))))
            glass.alpha_composite(shine)
            base.paste(glass, (0, 0), mask)
            edge = Image.new("RGBA", base.size, (0, 0, 0, 0))  # a fine light edge, brighter at the top
            ImageDraw.Draw(edge).rounded_rectangle((x0, y0, x1, y1), radius=r, outline=(255, 255, 255, 46), width=S)
            ImageDraw.Draw(edge).arc((x0, y0, x0 + 2 * r, y1), 200, 270, fill=(255, 255, 255, 110), width=S)
            ImageDraw.Draw(edge).line((x0 + r, y0, x1 - r, y0), fill=(255, 255, 255, 90), width=S)
            base.alpha_composite(edge)
            d = int(4.4 * rem * S)
            px = x0 + int(.9 * rem * S)
            base.alpha_composite(self.picture(it.get("image"), d), (px, y0 + ((y1 - y0) - d) // 2))
            g = ImageDraw.Draw(base)
            tx = px + d + int(1.2 * rem * S)
            ty = y0 + (y1 - y0) // 2
            g.text((tx, ty), t, font=title, fill=(246, 247, 250, 255), anchor="lm")
            g.text((tx + title.getlength(t), ty), sub, font=rest, fill=(255, 255, 255, 185), anchor="lm")
            if it.get("progress") is not None:
                bars.append({"box": (pad, y, pad + w, y + h), "target": float(it["progress"])})
            y += h + int(.8 * rem)
        base = base.resize((W_, H_), Image.LANCZOS)
        return base, bars

    def frame(self, base, bars, shown, t, rem):
        """The bar on top of the still parts: it grows to its new width and a light sweeps along it."""
        img = base.copy()
        for i, b in enumerate(bars):
            x0, y0, x1, y1 = b["box"]
            bh = max(3, int(.45 * rem))
            full = x1 - x0
            w = int(full * shown[i] / 100)
            if w <= 0:
                continue
            strip = Image.new("RGBA", (full, bh), (255, 255, 255, 30))
            fill = Image.linear_gradient("L").rotate(90).resize((max(1, w), bh))
            a, c = (127, 178, 255), (127, 240, 200)
            col = Image.merge("RGB", [fill.point(lambda v, k=k: int(a[k] + (c[k] - a[k]) * v / 255)) for k in range(3)])
            bar = col.convert("RGBA")
            if shown[i] < 100:  # the light sweeping along
                sx = int((t % 2.2) / 2.2 * (w + w // 2)) - w // 4
                hl = Image.new("RGBA", bar.size, (0, 0, 0, 0))
                hd = ImageDraw.Draw(hl)
                for dx in range(-w // 6, w // 6):
                    v = int(170 * (1 - abs(dx) / (w / 6 or 1)))
                    hd.line((sx + dx, 0, sx + dx, bh), fill=(255, 255, 255, max(0, v)))
                bar.alpha_composite(hl)
            strip.alpha_composite(bar, (0, 0))
            # cut to the pill, so the bar follows its rounded bottom edge
            mask = Image.new("L", (full, y1 - y0), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, full - 1, y1 - y0 - 1), radius=(y1 - y0) // 2, fill=255)
            layer = Image.new("RGBA", (full, y1 - y0), (0, 0, 0, 0))
            layer.alpha_composite(strip, (0, y1 - y0 - bh))
            glow = layer.filter(ImageFilter.GaussianBlur(bh))
            out = Image.new("RGBA", (full, y1 - y0), (0, 0, 0, 0))
            out.alpha_composite(glow)
            out.alpha_composite(layer)
            img.paste(out, (x0, y0), Image.composite(out, Image.new("RGBA", out.size, (0, 0, 0, 0)), mask).getchannel("A"))
        return img


class BLEND(ctypes.Structure):
    _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("format", ctypes.c_byte)]


class BMI(ctypes.Structure):
    _fields_ = [("size", W.DWORD), ("w", W.LONG), ("h", W.LONG), ("planes", W.WORD), ("bits", W.WORD), ("comp", W.DWORD),
                ("img", W.DWORD), ("xpm", W.LONG), ("ypm", W.LONG), ("used", W.DWORD), ("imp", W.DWORD)]


def show(hwnd, img, x, y):
    """Puts the picture on screen at x, y: each pixel's own alpha decides how see-through it is."""
    w, h = img.size
    from PIL import ImageChops
    r, g, b, a = img.split()
    data = Image.merge("RGBA", [ImageChops.multiply(ch, a) for ch in (b, g, r)] + [a]).tobytes()  # BGRA, premultiplied
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    ctypes.memmove(bits, data, len(data))
    old = gdi32.SelectObject(mem, dib)
    pt, size, src = W.POINT(x, y), W.SIZE(w, h), W.POINT(0, 0)
    user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(pt), ctypes.byref(size), mem, ctypes.byref(src), 0, ctypes.byref(BLEND(0, 0, 255, 1)), 2)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(dib)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, screen)


def run(url, screen, log=lambda m: None):
    """The card's own loop: makes the window, then draws until there's nothing to show."""
    user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor: real pixels
    except Exception:
        pass
    sx, sy, sw, sh = screen
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    proc = WNDPROC(lambda h, m, wp, lp: user32.DefWindowProcW(h, m, wp, lp))

    class WC(ctypes.Structure):
        _fields_ = [("style", W.UINT), ("proc", WNDPROC), ("cls", ctypes.c_int), ("wnd", ctypes.c_int), ("inst", W.HINSTANCE),
                    ("icon", W.HICON), ("cursor", W.HANDLE), ("bg", W.HBRUSH), ("menu", W.LPCWSTR), ("name", W.LPCWSTR)]
    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WC(0, proc, 0, 0, inst, None, None, None, None, "UltraFrontEndHUD")
    user32.RegisterClassW(ctypes.byref(wc))
    user32.CreateWindowExW.restype = W.HWND
    ex = 0x80000 | 0x20 | 0x8 | 0x80 | 0x8000000  # layered, transparent to clicks, topmost, tool window, no-activate
    hwnd = user32.CreateWindowExW(ex, "UltraFrontEndHUD", "Ultra Front End HUD", 0x80000000, sx, sy, 1, 1, None, None, inst, None)
    card, state = Card(url), {"items": [], "size": 1.0, "place": "top-left", "hidden": False, "quit": False, "v": 0}

    def poll():
        while True:
            try:
                with urllib.request.urlopen(url + "/api/addon-hud", timeout=5) as r:
                    v = json.load(r)
                if v.get("quit"):
                    state["quit"] = True
                    return
                key = json.dumps([v.get("items"), v.get("size"), v.get("place"), v.get("hidden")], sort_keys=True)
                if key != state.get("key"):
                    state.update(items=v.get("items") or [], size=v.get("size") or 1, place=v.get("place") or "top-left",
                                 hidden=bool(v.get("hidden")), key=key, v=state["v"] + 1)
            except Exception:
                pass
            time.sleep(2)
    threading.Thread(target=poll, daemon=True).start()
    shown_v, base, bars, shown, visible = -1, None, [], [], False
    msg = W.MSG()
    log("hud: drawing")
    while not state["quit"]:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        rem = sh / 118 * float(state["size"])
        if state["v"] != shown_v:
            shown_v = state["v"]
            if state["items"] and not state["hidden"]:
                old = {i: s for i, s in enumerate(shown)}
                base, bars = card.layout(state["items"], rem)
                shown = [old.get(i, b["target"]) for i, b in enumerate(bars)]
            else:
                base = None
        if base is None:
            if visible:
                user32.ShowWindow(hwnd, 0)
                visible = False
            time.sleep(.2)
            continue
        for i, b in enumerate(bars):  # the bar glides to its new width
            shown[i] += (b["target"] - shown[i]) * .12 if abs(b["target"] - shown[i]) > .05 else b["target"] - shown[i]
        img = card.frame(base, bars, shown, time.time(), rem)
        m = int(sh * .025)
        place = state["place"]
        x = sx + m if "left" in place else sx + sw - img.width - m if "right" in place else sx + (sw - img.width) // 2
        y = sy + sh - img.height - m * 2 if place.startswith("bottom") else sy + m
        show(hwnd, img, x, y)
        if not visible:
            user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
            visible = True
        time.sleep(1 / 30 if bars and any(s < 100 for s in shown) else .5)
    user32.DestroyWindow(hwnd)
