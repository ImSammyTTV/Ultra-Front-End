"""On-screen performance display: a see-through, click-through layer in the top right corner, Off, Compact or Full.

CPU, memory and GPU come from Windows' own performance counters. FPS and frame times need PresentMon (data/tools), which
reads them from Windows' graphics events without touching the game; without it those lines show "--". Temperatures aren't
shown, because Windows has no standard way to read them. It won't draw over a game in true exclusive fullscreen.
"""
import ctypes
import ctypes.wintypes as W
import glob
import os
import re
import subprocess
import threading
import time
from collections import deque

MODES = ["off", "compact", "full"]
STATS = {"cpu": 0.0, "cores": [], "gpu": 0.0, "vram": 0.0, "ram": 0.0, "ram_total": 0.0}
TIMES = deque(maxlen=20000)  # (when, milliseconds) of each frame from the game in front: ten seconds even at 2000 fps
PROC = [None]  # the running PresentMon, so the helper can stop it when it quits
MODE = ["off"]


class _Value(ctypes.Structure):
    _fields_ = [("status", W.DWORD), ("value", ctypes.c_double)]


class _Item(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar_p), ("data", _Value)]


class _Memory(ctypes.Structure):
    _fields_ = [("length", W.DWORD), ("load", W.DWORD), ("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("page", ctypes.c_ulonglong),
                ("pagefree", ctypes.c_ulonglong), ("virtual", ctypes.c_ulonglong), ("virtualfree", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]


def _counters(pdh, query, handle):
    size, count = W.DWORD(0), W.DWORD(0)
    pdh.PdhGetFormattedCounterArrayW(handle, 0x200 | 0x8000, ctypes.byref(size), ctypes.byref(count), None)  # double, no cap at 100
    if not size.value:
        return {}
    buf = ctypes.create_string_buffer(size.value)
    if pdh.PdhGetFormattedCounterArrayW(handle, 0x200 | 0x8000, ctypes.byref(size), ctypes.byref(count), buf):
        return {}
    items = ctypes.cast(buf, ctypes.POINTER(_Item))
    return {items[i].name: items[i].data.value for i in range(count.value) if items[i].data.status in (0, 1)}


def _sample_loop():
    pdh = ctypes.windll.pdh
    pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
    pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
    pdh.PdhCollectQueryData.argtypes = pdh.PdhCloseQuery.argtypes = [ctypes.c_void_p]
    pdh.PdhGetFormattedCounterArrayW.argtypes = [ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD), ctypes.c_void_p]
    query, handles, opened = None, {}, 0.0
    while True:
        if MODE[0] == "off":
            time.sleep(0.5)
            continue
        if not query or time.time() - opened > 20:  # games add new GPU counters as they start
            if query:
                pdh.PdhCloseQuery(query)
            q = ctypes.c_void_p()
            pdh.PdhOpenQueryW(None, 0, ctypes.byref(q))
            query, handles, opened = q, {}, time.time()
            for key, path in (("cpu", r"\Processor(*)\% Processor Time"), ("gpu", r"\GPU Engine(*engtype_3D)\Utilization Percentage"),
                              ("vram", r"\GPU Adapter Memory(*)\Dedicated Usage")):
                h = ctypes.c_void_p()
                if pdh.PdhAddEnglishCounterW(query, path, 0, ctypes.byref(h)) == 0:
                    handles[key] = h
            pdh.PdhCollectQueryData(query)
            time.sleep(0.5)
        pdh.PdhCollectQueryData(query)
        cpu = _counters(pdh, query, handles["cpu"]) if "cpu" in handles else {}
        STATS["cpu"] = cpu.get("_Total", 0.0)
        STATS["cores"] = [cpu[k] for k in sorted((k for k in cpu if k.isdigit()), key=int)]
        adapters = {}
        for name, value in (_counters(pdh, query, handles["gpu"]) if "gpu" in handles else {}).items():
            m = re.search(r"luid_\w+?_phys", name)
            if m:
                adapters[m.group(0)] = adapters.get(m.group(0), 0.0) + value
        STATS["gpu"] = min(100.0, max(adapters.values(), default=0.0))
        memory = _counters(pdh, query, handles["vram"]) if "vram" in handles else {}
        STATS["vram"] = max(memory.values(), default=0.0) / 2 ** 30
        m = _Memory()
        m.length = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        STATS["ram"], STATS["ram_total"] = (m.total - m.free) / 2 ** 30, m.total / 2 ** 30
        time.sleep(1)


def presentmon(data):
    """The newest PresentMon in data/tools, by version number (2.10 after 2.9)."""
    hits = glob.glob(os.path.join(data, "tools", "PresentMon*.exe"))
    return max(hits, key=lambda p: [int(n) for n in re.findall(r"\d+", os.path.basename(p))], default=None)


def _read_frames(proc, user32):
    pid_col = time_col = None
    front, checked = 0, 0.0
    for line in proc.stdout:
        cols = line.strip().split(",")
        if pid_col is None:
            if "ProcessID" in cols:
                pid_col = cols.index("ProcessID")
                time_col = next((cols.index(n) for n in ("FrameTime", "msBetweenPresents", "MsBetweenPresents") if n in cols), None)
            continue
        now = time.time()
        if now - checked > 0.5:
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(p))
            front, checked = p.value, now
        try:
            if time_col is not None and int(cols[pid_col]) == front:
                TIMES.append((now, float(cols[time_col])))
        except (ValueError, IndexError):
            pass


def stop():
    proc, PROC[0] = PROC[0], None
    if proc and proc.poll() is None:
        try:
            proc.kill()
            proc.wait(2)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _frames_loop(data, should_show):
    """Keep PresentMon running while the display is on over a game, and note the frames of whichever game is in front."""
    user32 = ctypes.WinDLL("user32")  # its own copy, as in _window_loop
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    wait = 1
    while True:
        try:
            exe = presentmon(data)
            if MODE[0] == "off" or not exe or not should_show():
                time.sleep(1)
                continue
            started = time.time()
            proc = PROC[0] = subprocess.Popen([exe, "--output_stdout", "--no_console_stats", "--stop_existing_session", "--session_name", "UltraFrontEndHud"],
                                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, errors="replace",
                                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            reader = threading.Thread(target=_read_frames, args=[proc, user32], daemon=True)
            reader.start()
            hidden = 0.0
            while proc.poll() is None:
                time.sleep(0.5)
                hidden = 0.0 if should_show() else hidden or time.time()
                if MODE[0] == "off" or (hidden and time.time() - hidden > 30):  # off, or no game for a while (not just the in-game menu)
                    break
            died = proc.poll() is not None
            stop()
            reader.join(2)
            # one that quits by itself straight away (no rights to Windows' graphics events) is tried less and less often
            wait = min(wait * 2, 300) if died and time.time() - started < 10 else 1
            time.sleep(wait)
        except Exception:
            time.sleep(5)


def frame_stats():
    """FPS over the last second, the 1% low over the last ten, and recent frame times for the graph."""
    now, frames = time.time(), list(TIMES)
    recent = [ms for t, ms in frames if now - t < 1 and ms > 0]
    if len(recent) < 2:
        return None
    wide = sorted((ms for t, ms in frames if now - t < 10 and ms > 0), reverse=True)
    low = wide[max(0, len(wide) // 100 - 1)]
    return {"fps": 1000 * len(recent) / sum(recent), "ms": sum(recent) / len(recent), "low": 1000 / low, "graph": [ms for t, ms in frames if now - t < 6 and ms > 0]}


FONTS = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in FONTS:
        from PIL import ImageFont
        try:
            FONTS[key] = ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf", size)
        except OSError:  # not on this Windows: Pillow's own
            FONTS[key] = ImageFont.load_default(size)
    return FONTS[key]


def unit(screen_h, screen_w=None):
    """1% of the screen height, like the rest of the frontend; a portrait screen's width limits it, and small screens keep
    the text readable."""
    return max(min(screen_h, (screen_w or 2 * screen_h) * 1.16) / 100, 7.2)


def draw(mode, stats, frames, screen_h, clock="", screen_w=None):
    """The panel as a picture with transparency: Windows blends it over the game."""
    from PIL import Image, ImageDraw
    u = unit(screen_h, screen_w)
    white, quiet, blue, faint = (255, 255, 255, 255), (255, 255, 255, 165), (56, 189, 248, 255), (255, 255, 255, 34)
    pad, width = round(1.6 * u), round((24 if mode == "compact" else 31) * u)
    fps = f"{frames['fps']:.0f}" if frames else "--"
    ms = f"{frames['ms']:.1f} ms" if frames else "-- ms"
    pct = lambda v: f"{v:.0f}%"
    if mode == "compact":
        height = round(9.4 * u)
    else:
        rows = (len(stats["cores"]) + 7) // 8 or 1
        height = round((36.6 + rows * 2.4) * u)
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=round(1.2 * u), fill=(12, 13, 15, 178))
    if mode == "compact":
        big = round(4.4 * u)
        while big > 2 * u and pad + d.textlength(fps, font=font(big, True)) + .8 * u + d.textlength("FPS", font=font(round(1.7 * u))) > 12.8 * u:
            big -= 1  # 1000+ in uncapped menus: smaller, clear of the CPU and GPU labels
        d.text((pad, round(.7 * u)), fps, font=font(big, True), fill=white)
        left = pad + d.textlength(fps, font=font(big, True)) + .8 * u
        d.text((left, round(2.7 * u)), "FPS", font=font(round(1.7 * u)), fill=quiet)
        d.text((pad, round(6.2 * u)), ms, font=font(round(1.8 * u)), fill=quiet)
        for i, (label, value) in enumerate((("CPU", stats["cpu"]), ("GPU", stats["gpu"]))):
            y = round((1.5 + i * 3.4) * u)
            d.text((round(13 * u), y), label, font=font(round(1.9 * u)), fill=quiet)
            text = pct(value)
            d.text((width - pad - d.textlength(text, font=font(round(2.2 * u), True)), y - round(.1 * u)), text, font=font(round(2.2 * u), True), fill=white)
        return im
    y = round(1.2 * u)
    d.text((pad, y), "Performance", font=font(round(2 * u), True), fill=white)
    if clock:
        d.text((width - pad - d.textlength(clock, font=font(round(1.8 * u))), y + round(.1 * u)), clock, font=font(round(1.8 * u)), fill=quiet)
    y += round(3.4 * u)
    d.text((pad, y), fps, font=font(round(6 * u), True), fill=white)
    d.text((pad + d.textlength(fps, font=font(round(6 * u), True)) + .8 * u, y + round(3.3 * u)), "FPS", font=font(round(1.8 * u)), fill=quiet)
    for i, (label, value) in enumerate((("Frame time", ms), ("1% low", f"{frames['low']:.0f} FPS" if frames else "-- FPS"))):
        ry = y + round((1 + i * 2.7) * u)
        d.text((width - pad - round(14.4 * u), ry), label, font=font(round(1.5 * u)), fill=quiet)
        d.text((width - pad - d.textlength(value, font=font(round(1.7 * u), True)), ry), value, font=font(round(1.7 * u), True), fill=white)
    y += round(8.2 * u)
    gh = round(6.4 * u)
    d.rounded_rectangle((pad, y, width - pad, y + gh), radius=round(.5 * u), fill=(255, 255, 255, 14))
    points = (frames or {}).get("graph") or []
    if len(points) > 1:
        top = max(max(points), 16.7) * 1.15
        step = (width - 2 * pad) / (len(points) - 1)
        d.line([(pad + i * step, y + gh - min(ms_, top) / top * gh) for i, ms_ in enumerate(points)], fill=blue, width=max(1, round(.16 * u)))
    y += gh + round(1.1 * u)

    def line(label, value):
        nonlocal y
        d.text((pad, y), label, font=font(round(1.8 * u)), fill=quiet)
        d.text((width - pad - d.textlength(value, font=font(round(1.9 * u), True)), y), value, font=font(round(1.9 * u), True), fill=white)
        y += round(2.7 * u)

    def bar(value):
        nonlocal y
        d.rounded_rectangle((pad, y, width - pad, y + round(.4 * u)), radius=round(.2 * u), fill=faint)
        d.rounded_rectangle((pad, y, pad + (width - 2 * pad) * min(value, 100) / 100, y + round(.4 * u)), radius=round(.2 * u), fill=white)
        y += round(1.2 * u)

    line("CPU", pct(stats["cpu"]))
    bar(stats["cpu"])
    cols, gap = 8, round(.5 * u)
    cell = (width - 2 * pad - gap * (cols - 1)) / cols
    for i, value in enumerate(stats["cores"]):
        x, ry = pad + (i % cols) * (cell + gap), y + (i // cols) * round(2.4 * u)
        d.rectangle((x, ry, x + cell, ry + round(1.8 * u)), fill=faint)
        d.rectangle((x, ry + round(1.8 * u) * (1 - min(value, 100) / 100), x + cell, ry + round(1.8 * u)), fill=blue)
    y += ((len(stats["cores"]) + cols - 1) // cols) * round(2.4 * u) + round(.6 * u)
    line("GPU", pct(stats["gpu"]))
    bar(stats["gpu"])
    line("Video memory", f"{stats['vram']:.1f} GB")
    line("System memory", f"{stats['ram']:.1f} of {stats['ram_total']:.0f} GB")
    return im


def _window_loop(should_show):
    from PIL import Image  # noqa: F401
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")  # its own copies: the call types set here must not reach other code
    user32.SetProcessDPIAware()
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.CreateWindowExW.argtypes = [W.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(W.MSG), ctypes.c_void_p, W.UINT, W.UINT, W.UINT]
    user32.GetDC.restype = ctypes.c_void_p
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.UpdateLayeredWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, W.DWORD]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.UINT, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, W.DWORD]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

    class Info(ctypes.Structure):
        _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG), ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
                    ("image", W.DWORD), ("xppm", W.LONG), ("yppm", W.LONG), ("used", W.DWORD), ("important", W.DWORD)]

    class Blend(ctypes.Structure):
        _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]

    # WS_EX_LAYERED | TRANSPARENT (clicks pass through) | TOPMOST | TOOLWINDOW | NOACTIVATE (never takes focus)
    hwnd = user32.CreateWindowExW(0x080800A8, "Static", "Ultra Front End Stats", 0x80000000, 0, 0, 10, 10, None, None, None, None)
    if not hwnd:
        return
    msg, shown = W.MSG(), False
    while True:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            show = MODE[0] != "off" and should_show()
            if show != shown:
                user32.ShowWindow(hwnd, 4 if show else 0)  # SW_SHOWNOACTIVATE
                shown = show
            if not show:
                time.sleep(0.25)
                continue
            sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            im = draw(MODE[0], STATS, frame_stats(), sh, time.strftime("%H:%M"), sw)
        except Exception:  # skip this frame rather than lose the display until a restart
            time.sleep(1)
            continue
        w, h = im.size
        raw = im.convert("RGBa").tobytes("raw", "BGRa")
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        info = Info(ctypes.sizeof(Info), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(mem, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(mem, bitmap)
        ctypes.memmove(bits, raw, len(raw))
        margin = int(2 * unit(sh, sw))
        place = W.POINT(sw - w - margin, margin)
        size, origin, blend = W.SIZE(w, h), W.POINT(0, 0), Blend(0, 0, 255, 1)
        user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(place), ctypes.byref(size), mem, ctypes.byref(origin), 0, ctypes.byref(blend), 2)
        user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # stays above the game, without taking focus
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)
        time.sleep(0.25)


def start(data, should_show, mode):
    MODE[0] = mode if mode in MODES else "off"
    for target, args in ((_sample_loop, []), (_frames_loop, [data, should_show]), (_window_loop, [should_show])):
        threading.Thread(target=target, args=args, daemon=True).start()
