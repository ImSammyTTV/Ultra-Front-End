"""Game Frontend.exe: the helper (server.py) and the fullscreen window in one program.

Build:  python -m PyInstaller "Game Frontend.spec"   (the exe lands in dist/; copy it next to app/ and data/)
"""
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request

import webview  # noqa: E402

import server  # noqa: E402

URL = f"http://127.0.0.1:{server.PORT}"


WEBVIEW_ARGS = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"


def webview_args():
    """Trailers start with sound, like they do in Edge, and no pinch zoom on touch screens. For this process's WebView2 only
    (games started from here inherit the environment), added to any value of the user's own. Returns the undo, for once
    WebView2 has started."""
    own = os.environ.get(WEBVIEW_ARGS)
    os.environ[WEBVIEW_ARGS] = " ".join(filter(None, [own, "--autoplay-policy=no-user-gesture-required --disable-pinch"]))

    def undo():
        if own is None:
            os.environ.pop(WEBVIEW_ARGS, None)
        else:
            os.environ[WEBVIEW_ARGS] = own
    return undo


def helper_up():
    try:
        with urllib.request.urlopen(URL + "/api/ping", timeout=1):
            return True
    except OSError:
        return False


def helper_get(path):
    try:
        with urllib.request.urlopen(URL + path, timeout=2) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def replace_old_helper():
    """After an update the old build can still be running in the tray, and reusing it would keep its old library scan and
    launch code. A helper from another build (or one too old to say) is stopped so this one can take over: True once it's
    gone. Not while it has a game going (its playtime and in-game menu would go with it), and one run from source
    (pythonw server.py) is left alone."""
    if not (server.WIN and getattr(sys, "frozen", False)):
        return False
    ping = helper_get("/api/ping")
    if not ping or ping.get("build") in (server.BUILD, "source"):
        return False
    if server.version_key(ping.get("version") or "0") > server.version_key(server.VERSION):
        return False  # a newer version than this one: an old download opened by mistake uses it
    pid = ping.get("pid") or port_owner(server.PORT)
    image = server.process_image(pid) if pid else ""
    if not image or os.path.normcase(os.path.dirname(image)) != os.path.normcase(server.ROOT):
        return False  # a copy somewhere else (dist\, another download) keeps its own helper: this one uses it
    running, menu = helper_get("/api/running"), helper_get("/api/overlay")
    if running is None or menu is None or running.get("games") or menu.get("open") or menu.get("recording"):
        if "--background" in sys.argv:
            server.note_start()  # it works, it just waits: an update that started this copy keeps it
        return False
    if pid and pid == os.getppid():  # it started this copy itself (no Steam), which then runs from its unpacked files: go round it
        if server.start_alone(sys.argv[1:]):
            if TRAY.get("mutex"):  # the new copy takes a few seconds to unpack before it looks for this
                import ctypes
                ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(TRAY["mutex"]))
            os._exit(0)
        return False
    try:
        own = os.path.samefile(server.process_image(os.getppid()), sys.executable)
    except OSError:
        own = False
    if not own:
        return False  # not unpacked by its own launcher but running from another copy's folder (handed on through Steam): that goes with the helper

    def gone(seconds):
        deadline = time.time() + seconds
        while helper_up() and time.time() < deadline:
            time.sleep(0.1)
        return not helper_up()
    if "build" in ping:  # builds from this one on leave when asked, tray icon and all
        try:
            req = urllib.request.Request(URL + "/api/quit", data=b"{}", headers={"Content-Type": "application/json", "X-Frontend": "1"})
            urllib.request.urlopen(req, timeout=2)
        except OSError:
            pass
        if gone(3):
            return True
    if pid:  # not /T: anything it started keeps running
        subprocess.run([os.path.join(server.SYSTEM32, "taskkill.exe"), "/F", "/PID", str(pid)], capture_output=True, creationflags=0x08000000)
    return gone(5)


def start_helper():
    """The helper runs as its own program in the background, like the one started at sign-in, never inside the window: Steam
    counts the window it launched as running for as long as that process lives, and then won't open the frontend again."""
    if not server.start_alone(["--background"] + (["--port", str(server.PORT)] if "--port" in sys.argv else [])):
        return False
    deadline = time.time() + 60  # a first start after an update can be slow; taking the helper in here would bring Steam's problem back
    while time.time() < deadline:
        if (helper_get("/api/ping") or {}).get("build") == server.BUILD:
            return True
        time.sleep(0.2)
    return False


def bring_forward():
    """The helper that asked Steam for this window would have brought it to the front, but this window replaced that helper."""
    for _ in range(150):
        time.sleep(0.2)
        hwnd = server.frontend_window()
        if hwnd:
            return server.raise_window(hwnd)


def open_at_sign_in():
    """Open the window once the helper is up. Through Steam when the frontend has a shortcut there (then a Steam Controller
    is a gamepad in it), so this gives Steam, which starts at sign-in too, a minute to come up."""
    deadline = time.time() + 30
    while not helper_up() and time.time() < deadline:
        time.sleep(0.5)
    deadline = time.time() + 60
    while server.steam_path() and not server.steam_shortcut_id() and time.time() < deadline:
        time.sleep(2)
    server.open_frontend()


def port_owner(port):
    """The process listening on the helper's port, for a helper too old to say its own."""
    try:
        out = subprocess.run([os.path.join(server.SYSTEM32, "netstat.exe"), "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace", timeout=10,
                             creationflags=0x08000000).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    for cols in (line.split() for line in out.splitlines()):
        if len(cols) == 5 and cols[1] == f"127.0.0.1:{port}" and cols[2] == "0.0.0.0:0" and cols[4].isdigit():
            return int(cols[4])
    return 0


class Api:
    """Called from the page: B on the home screen, then Exit."""
    def quit(self):
        for w in webview.windows:
            w.destroy()

    def slide(self, show):
        """The in-game overlay slides back out before it closes (or in again, if closing failed)."""
        OVL["closing"] = not show  # the focus is the game's again: take_focus stops claiming it
        OVL["gone"] = not show  # and the backdrop stops following the game
        overlay_slide(bool(show))


OVL = {}  # the overlay window: hwnd and where it sits, for overlay_slide


def take_focus(overlay_hwnd, seconds=0.0, game_hwnd=None):
    """The overlay holds the focus while it's up, so the game behind stops answering the controller: Steam hands a Steam
    Controller to the window with the focus (and types arrow keys into the overlay: the page ignores those copies), and
    games read their pad only while they have it. Windows can refuse the first try, and a game can take the focus back as
    the overlay appears, so it keeps checking for `seconds`. Back to game gives the focus back.
    Many fullscreen games minimize themselves when they lose the focus: such a game is put straight back on screen, behind
    the overlay and still without the focus, where it keeps running (and drawing) as normal."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    until = time.time() + seconds
    while not OVL.get("closing"):
        if game_hwnd and user32.IsIconic(ctypes.c_void_p(game_hwnd)):
            user32.ShowWindow(ctypes.c_void_p(game_hwnd), 4)  # SW_SHOWNOACTIVATE
            # on top of the other windows (the frontend's among them), under the overlay: topmost and back lifts it
            user32.SetWindowPos(ctypes.c_void_p(game_hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # TOPMOST; NOSIZE|NOMOVE|NOACTIVATE
            user32.SetWindowPos(ctypes.c_void_p(game_hwnd), ctypes.c_void_p(-2), 0, 0, 0, 0, 0x0013)  # NOTOPMOST
            user32.SetWindowPos(ctypes.c_void_p(overlay_hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # the overlay above it
        if user32.GetForegroundWindow() != overlay_hwnd and user32.IsWindowVisible(ctypes.c_void_p(overlay_hwnd)):
            server.take_foreground(overlay_hwnd)
        if time.time() >= until:
            break
        time.sleep(0.02)  # often: a game that minimizes is back before it shows


def overlay_slide(show, ms=190):
    """Slide the overlay in from (or out to) the left edge of the game's screen. The window moves and a region clips it to
    that screen, so no part of it shows on a monitor beside this one. Moving a window doesn't redraw the page, so it's smooth."""
    import ctypes
    hwnd = OVL.get("hwnd")
    if not hwnd:
        return
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    x, y, w, h = OVL["rect"]
    t0 = time.perf_counter()
    while True:
        t = min(1.0, (time.perf_counter() - t0) / (ms / 1000))
        ease = 1 - (1 - t) ** 3 if show else t ** 2  # in: quick then settling; out: gathering speed
        part = int(round(w * (ease if show else 1 - ease)))  # how much of the panel is on screen
        if show:  # a sliver at least: Chromium stops drawing a window that is wholly off the screen
            part = max(part, 2)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), x - (w - part), y, w, h, 0x0050)  # TOPMOST, SHOWWINDOW | NOACTIVATE
        user32.SetWindowRgn(ctypes.c_void_p(hwnd), gdi32.CreateRectRgn(w - part, 0, w, h), True)
        if t >= 1:
            break
        time.sleep(0.008)
    if show:
        user32.SetWindowRgn(ctypes.c_void_p(hwnd), None, True)  # whole again, as the page expects


# ---------- tray icon (Windows) ----------
# While the helper runs, Game Frontend sits in the notification area: double-click (or Open) brings the frontend up,
# Update library rescans, and the program only quits from Exit there. Closing the window leaves it in the tray.
TRAY = {"icon": None, "quit": threading.Event()}


def tray_icon():
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return None

    def open_(*_):
        server.open_frontend()

    def rescan():
        try:
            req = urllib.request.Request(URL + "/api/rescan", data=b"{}", headers={"Content-Type": "application/json", "X-Frontend": "1"})
            urllib.request.urlopen(req, timeout=120)
            icon.notify("The library was rescanned.", "Ultra Front End")
        except OSError:
            icon.notify("The helper didn't answer.", "Ultra Front End")

    def update(*_):  # a scan can take a while: not on the tray's own thread, which would stop answering
        threading.Thread(target=rescan, daemon=True).start()

    def autostart(*_):
        cfg = server.config()
        on = cfg.get("startup") != "off"
        mode = "off" if on else cfg.get("startupOn") or "background"  # turned back on: the choice it had before
        server.store("config.json", {**cfg, "startup": mode, **({"startupOn": cfg.get("startup")} if on else {})})
        server.set_autostart(mode)

    def quit_(*_):
        icon.stop()
        for w in webview.windows:
            w.destroy()
        import ctypes
        hwnd = server.frontend_window()  # the window, when it's a program of its own
        if hwnd:
            ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)  # WM_CLOSE
        stop_children()
        TRAY["quit"].set()
    menu = pystray.Menu(
        pystray.MenuItem("Open Ultra Front End", open_, default=True),
        pystray.MenuItem("Update library", update),
        pystray.MenuItem("Start with Windows", autostart, checked=lambda _: server.config().get("startup") != "off"),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", quit_),
    )
    icon = pystray.Icon("Ultra Front End", Image.open(os.path.join(server.shipped("app"), "icon.png")), "Ultra Front End", menu)
    TRAY["icon"] = icon

    def leave():  # a newer build is taking over: no icon left behind in the tray
        icon.visible = False
        stop_children()
        os._exit(0)
    server.QUIT[0] = leave
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def stop_children():
    """The helper is leaving: nothing it started may outlive it. An in-game menu would stay on top with nothing to close it,
    a recording would never be saved, and PresentMon would keep running."""
    proc = server.OVERLAY.get("proc")
    if proc and proc.poll() is None:
        subprocess.run([os.path.join(server.SYSTEM32, "taskkill.exe"), "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=0x08000000)
    try:
        server.stop_recording()  # finishes the file and adds it to the album
    except Exception:
        pass
    hud = sys.modules.get("hud")  # only there if the helper started it
    if hud:
        hud.stop()


def spawn_games():
    """Start the games the helper hands over. As the window Steam launched, this process passes Steam's controller on to them."""
    while True:
        try:
            with urllib.request.urlopen(URL + "/api/spawn/next", timeout=30) as r:
                job = json.load(r)
            if not job:
                continue
            pid = 0
            try:
                if "dolphin" in str(job["cmd"]).lower():
                    server.dolphin_shake_key()  # only with Wii motion on
                pid = server.local_spawn(job["cmd"], job["cwd"]).pid
            except Exception:
                pass
            body = json.dumps({"id": job["id"], "pid": pid}).encode()
            urllib.request.urlopen(urllib.request.Request(URL + "/api/spawn/done", data=body, headers={"Content-Type": "application/json", "X-Frontend": "1"}), timeout=5)
        except Exception:  # a bad reply as well: this thread must keep going for the rest of the session
            time.sleep(2)


def already_open():
    """One frontend window at a time: a second start brings the first to the front and leaves. The mutex lasts as long as this process."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    TRAY["mutex"] = k32.CreateMutexW(None, False, "GameFrontendWindow" + ("" if server.PORT == 8137 else str(server.PORT)))  # a --port test copy has its own
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return False
    user32 = ctypes.windll.user32
    hwnd = server.frontend_window()
    if hwnd:
        if user32.IsIconic(ctypes.c_void_p(hwnd)):  # restoring a fullscreen window that isn't minimized would knock it out of fullscreen
            user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    return True


def overlay():
    """The in-game overlay: a topmost side panel, so the live game stays in full view beside it. (A transparent WebView2
    window shows its own backdrop, not what is behind it, so a full-screen page can't be see-through.)"""
    import ctypes
    webview_args()
    x, y, w, h = game_screen()
    scale = ctypes.windll.user32.GetDpiForSystem() / 96 or 1
    ow = min(int(h * .46), int(w * .42))  # beside the game: 46% of the height wide, but never most of a portrait screen
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    game = user32.GetForegroundWindow()  # the game's window, for games that can't give up the focus (below)
    # A blurred snapshot of the game, taken before the overlay covers it: the backdrop wherever Windows' live glass can't be
    frost = frosted_backdrop(x, y, ow, h)
    window = webview.create_window("Ultra Front End Overlay", URL + "/overlay.html", x=int(x / scale), y=int(y / scale), width=int(ow / scale), height=int(h / scale),
                                   on_top=True, frameless=True, easy_drag=False, background_color="#1c1d1f", hidden=True, js_api=Api())

    def snapshot():
        if frost:
            window.evaluate_js(f"frost('{frost}')")

    def edge_to_edge():
        """Windows keeps a frameless window off the screen edges and rounds it: pin it to the full height, square."""
        window.events.loaded.wait(15)  # hidden until the page and its backdrop are ready, then it slides in
        try:
            raw = int(window.native.Handle.ToInt64())
        except Exception:
            raw = server.frontend_window("Ultra Front End Overlay")
        hwnd = ctypes.c_void_p(raw)
        square = ctypes.c_int(1)  # DWMWCP_DONOTROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(square), ctypes.sizeof(square))
        no_border = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE: Windows 11 draws a light edge otherwise
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
        snapshot()  # the first frame; live_frost keeps it moving with the game once the overlay is up
        OVL.update(hwnd=raw, rect=(x, y, ow, h))
        user32.SetWindowRgn(hwnd, ctypes.windll.gdi32.CreateRectRgn(0, 0, 0, 0), False)  # nothing on screen yet
        user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), x, y, ow, h, 0x0010)  # HWND_TOPMOST, SWP_NOACTIVATE, still hidden
        try:  # shown through WinForms, so the page inside starts drawing (a window shown by Windows alone stays blank);
            from System import Func, Type  # not window.show(), which would take the focus from the game
            window.native.Invoke(Func[Type](lambda: window.native.Show()))
        except Exception:
            window.show()
        window.evaluate_js("document.body.classList.add('on')")
        time.sleep(0.15)  # its first frame, with the backdrop, before any of it comes into view
        # now, so the game stops taking the controls as the panel slides in; watched for a while, alongside the slide
        threading.Thread(target=take_focus, args=[raw, 3, game], daemon=True).start()
        try:
            overlay_slide(True)
        except Exception:
            user32.SetWindowRgn(hwnd, None, True)
            user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), x, y, ow, h, 0x0050)  # HWND_TOPMOST, SWP_SHOWWINDOW | SWP_NOACTIVATE
        time.sleep(0.2)  # a game that minimized itself is back on screen by now
        try:  # the keys go to the page, not just its window: a keyboard works the menu too
            from System import Func, Type
            window.native.Invoke(Func[Type](lambda: window.native.browser.webview.Focus()))
        except Exception:
            pass
        threading.Thread(target=live_frost, args=[window, game, x, y, ow, h], daemon=True).start()
    webview.start(edge_to_edge, private_mode=True, storage_path=os.path.join(server.DATA, "webview-overlay"))
    os._exit(0)


FROST_SCALE = 6  # the frost is worked on at a sixth of the size: blurred anyway, and quick


def frost_url(img):
    """A frosted version of the game behind the overlay, as a small data URL the page stretches over its background:
    blurred, and darkened only a little, so the game shows through while white text stays readable."""
    import base64
    import io
    from PIL import ImageFilter
    w, h = img.size
    small = img.convert("RGB").resize((max(1, w // FROST_SCALE), max(1, h // FROST_SCALE)))
    small = small.filter(ImageFilter.GaussianBlur(4)).point(lambda v: int(v * .72 + 6))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def frosted_backdrop(x, y, w, h):
    """The screen where the overlay opens, frosted, taken before the overlay covers it. None when the capture is blank."""
    try:
        from PIL import ImageGrab, ImageStat
        shot = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
        return None if max(ImageStat.Stat(shot).stddev) < 4 else frost_url(shot)  # one flat colour: nothing worth frosting
    except Exception:
        return None


def game_frame(hwnd, x, y, w, h):
    """The part of the game's window under the overlay, drawn by the game itself (PrintWindow), so the overlay on top
    isn't in it. None if the game can't be drawn this way (exclusive fullscreen, minimized: black or flat)."""
    import ctypes
    import ctypes.wintypes as W
    from PIL import Image, ImageStat
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    r = W.RECT()
    if user32.IsIconic(ctypes.c_void_p(hwnd)) or not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r)):
        return None
    ox, oy = max(0, x - r.left), max(0, y - r.top)  # where the overlay's area starts inside the game's window
    bw, bh = ox + w, oy + h
    screen = user32.GetDC(None)
    dc, bmp = gdi32.CreateCompatibleDC(screen), gdi32.CreateCompatibleBitmap(screen, bw, bh)
    try:
        gdi32.SelectObject(dc, bmp)
        if not user32.PrintWindow(ctypes.c_void_p(hwnd), dc, 2):  # PW_RENDERFULLCONTENT: DirectX games too
            return None

        class Header(ctypes.Structure):
            _fields_ = [("size", ctypes.c_uint32), ("w", ctypes.c_int32), ("h", ctypes.c_int32), ("planes", ctypes.c_uint16),
                        ("bits", ctypes.c_uint16), ("compression", ctypes.c_uint32), ("rest", ctypes.c_uint32 * 5)]
        buf = ctypes.create_string_buffer(bw * bh * 4)
        gdi32.GetDIBits(dc, bmp, 0, bh, buf, ctypes.byref(Header(40, bw, -bh, 1, 32, 0)), 0)
        img = Image.frombuffer("RGBX", (bw, bh), buf, "raw", "BGRX").crop((ox, oy, bw, bh))
        return None if max(ImageStat.Stat(img.resize((32, 64))).stddev) < 3 else img
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, screen)


def live_frost(window, game, x, y, w, h):
    """Keep the overlay's backdrop following the game: a fresh frosted frame several times a second while it's open. Stops
    (keeping the last frame) if the game can't be drawn, so a game it doesn't work with keeps the opening snapshot."""
    misses = 0
    while not OVL.get("gone"):
        started = time.perf_counter()
        try:
            img = game_frame(game, x, y, w, h) if game else None
        except Exception:
            img = None
        if img is None:
            misses += 1
            if misses >= 3:
                return
        else:
            misses = 0
            window.evaluate_js(f"frost('{frost_url(img)}')")
        time.sleep(max(0.08, (time.perf_counter() - started) * 2))  # about 8 a second, less if the machine is slow


def game_screen():
    """The screen the game is on (the window in front, as the overlay opens), in pixels: x, y, width, height."""
    import ctypes
    import ctypes.wintypes as W

    class Info(ctypes.Structure):
        _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT), ("flags", W.DWORD)]
    user32 = ctypes.WinDLL("user32")
    user32.SetProcessDPIAware()  # as pywebview does when it starts: real pixels
    user32.GetForegroundWindow.restype = user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, W.DWORD]
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    info = Info(ctypes.sizeof(Info))
    if user32.GetMonitorInfoW(user32.MonitorFromWindow(user32.GetForegroundWindow(), 1), ctypes.byref(info)):  # MONITOR_DEFAULTTOPRIMARY
        r = info.monitor
        if r.right > r.left and r.bottom > r.top:
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    return (0, 0) + tuple(server.screen_size())


LOG_CAP = 512 * 1024


def trim_log(path, cap=LOG_CAP):
    """Past the cap, keep the newer half (from a line start)."""
    try:
        if os.path.getsize(path) <= cap:
            return
        with open(path, "rb") as f:
            f.seek(-(cap // 2), 2)
            keep = f.read().split(b"\n", 1)[-1]
        with open(path, "wb") as f:
            f.write(keep)
    except OSError:
        pass


def window_log(line):
    """data/window.log: how each start went, and anything the WebView2 window reports."""
    path = os.path.join(server.DATA, "window.log")
    trim_log(path)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')} [{os.getpid()}] {line}\n")
    except OSError:
        pass


class WindowLogHandler(logging.Handler):
    def emit(self, record):
        window_log(f"pywebview {record.levelname.lower()}: {self.format(record)}")


def serving(helper):
    """Wait until the helper thread answers on the port: False if it gave up because the port was taken."""
    deadline = time.time() + 30
    while helper.is_alive() and time.time() < deadline:
        if (helper_get("/api/ping") or {}).get("pid") == os.getpid():
            return True
        time.sleep(0.2)
    return helper.is_alive()


def main():
    logging.getLogger("pywebview").addHandler(WindowLogHandler(logging.WARNING))
    window_log(f"start {' '.join(sys.argv[1:]) or '(window)'} from parent {os.getppid()}")
    if "--overlay" in sys.argv:
        return overlay()
    if "--background" in sys.argv:  # started at sign-in: the helper only, so the Xbox button or the tray can open the window
        if not helper_up() or replace_old_helper():
            helper = threading.Thread(target=server.main, daemon=True)
            helper.start()
            if not serving(helper):
                return window_log("helper: the port is taken, leaving")
            server.note_start()
            if "--open" in sys.argv:  # started at sign-in to open the frontend too
                threading.Thread(target=open_at_sign_in, daemon=True).start()
            if server.WIN and tray_icon():
                TRAY["quit"].wait()
            else:
                threading.Event().wait()
        return
    if server.WIN and already_open():
        return
    took_over = helper_up() and replace_old_helper()
    own = not helper_up()  # one already running (in the background, or pythonw server.py) is reused, unless it was an older build
    if own and server.WIN and getattr(sys, "frozen", False) and (start_helper() or helper_up()):
        own = False
    window_log(f"helper: {'took over from an older build, ' if took_over else ''}{'in this process' if own else 'its own program'}; opening the window")
    if own:  # the helper lives in this process (from source, on a Mac, or if it couldn't start on its own)
        threading.Thread(target=server.main, daemon=True).start()
        deadline = time.time() + 15
        while not helper_up() and time.time() < deadline:
            time.sleep(0.1)
        if server.WIN:
            tray_icon()
    if server.WIN:
        threading.Thread(target=spawn_games, daemon=True).start()
        if took_over:
            threading.Thread(target=bring_forward, daemon=True).start()
    undo_args = webview_args()
    full = "--windowed" not in sys.argv
    if server.MAC and full:
        # macOS full screen leaves the strip beside the notch black, so cover the whole screen with a borderless window instead
        window = webview.create_window("Ultra Front End", URL, frameless=True, easy_drag=False, background_color="#070c1a", js_api=Api())
        webview.start(cover_screen_mac, window, private_mode=False, storage_path=os.path.join(server.DATA, "webview"))
    else:
        window = webview.create_window("Ultra Front End", URL, fullscreen=full, background_color="#070c1a", js_api=Api())
        window.events.loaded += lambda: (undo_args(), window_log("page loaded"))
        webview.start(private_mode=False, storage_path=os.path.join(server.DATA, "webview"))
    window_log("window closed")
    if server.WIN and TRAY.get("mutex"):  # window closed: if this stays in the tray, the next start must be free to open one
        import ctypes
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(TRAY["mutex"]))
    if own and TRAY["icon"] and not TRAY["quit"].is_set():  # window closed: stay in the tray until Exit there
        TRAY["quit"].wait()
    elif own and server.config().get("guideOpens"):  # keep listening for the Xbox button after the window closes
        threading.Event().wait()
    os._exit(0)  # window closed: stop the helper threads too


def cover_screen_mac(window):
    """Hide the menu bar and Dock and stretch the window over the whole screen, notch strip included."""
    import AppKit
    from PyObjCTools import AppHelper

    window.events.shown.wait(15)

    def apply():
        w, app = window.native, AppKit.NSApplication.sharedApplication()
        app.setPresentationOptions_(AppKit.NSApplicationPresentationHideDock | AppKit.NSApplicationPresentationHideMenuBar)
        w.setStyleMask_(AppKit.NSWindowStyleMaskBorderless)
        w.setFrame_display_((w.screen() or AppKit.NSScreen.mainScreen()).frame(), True)
        app.activateIgnoringOtherApps_(True)
        w.makeKeyAndOrderFront_(None)
        window_log(f"window {w.frame()}; screen {(w.screen() or AppKit.NSScreen.mainScreen()).frame()}; key {w.isKeyWindow()}")  # for checking the result remotely
    AppHelper.callAfter(apply)


if __name__ == "__main__":
    main()
