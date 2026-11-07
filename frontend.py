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

if __name__ == "__main__" and os.name == "nt":  # Setup and Uninstall (Windows): their own window, before the helper is imported (it sets up a data folder)
    import setup_ui
    if setup_ui.is_setup() or "--uninstall" in sys.argv or setup_ui.first_start_of_download():
        setup_ui.main("uninstall" if "--uninstall" in sys.argv else "install")
        sys.exit()

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
    if (server.version_key(ping.get("version") or "0") > server.version_key(server.VERSION)
            and server.load("update.json", {}).get("installing") != server.VERSION):
        return False  # a newer version than this one: an old download opened by mistake uses it (unless the update put this
        # one in: going back from a nightly build to the main release)
    pid = ping.get("pid") or port_owner(server.PORT)
    image = server.process_image(pid) if pid else ""
    older = server.version_key(ping.get("version") or "0") < server.version_key(server.VERSION)
    if not image or (os.path.normcase(os.path.dirname(image)) != os.path.normcase(server.ROOT) and not older):
        # a copy somewhere else of the same version (dist\, another download) keeps its own helper: this one uses it. An
        # older version's helper is replaced wherever it is: the installed app (Setup) next to an old download started
        # with Windows otherwise showed the old download's page under the new version's name
        return False
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
    is a gamepad in it), so this gives Steam, which starts at sign-in too, a minute to come up. With no shortcut there it
    opens at once: waiting on Steam would only hold it up."""
    deadline = time.time() + 30
    while not helper_up() and time.time() < deadline:
        time.sleep(0.5)
    deadline = time.time() + 60
    while server.steam_shortcut_id(running=False) and not server.steam_shortcut_id() and time.time() < deadline:
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
            OVL["minimized"] = True
            user32.ShowWindow(ctypes.c_void_p(game_hwnd), 4)  # SW_SHOWNOACTIVATE
            OVL["restored_at"] = time.time()
            # on top of the other windows (the frontend's among them), under the overlay: topmost and back lifts it
            user32.SetWindowPos(ctypes.c_void_p(game_hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # TOPMOST; NOSIZE|NOMOVE|NOACTIVATE
            user32.SetWindowPos(ctypes.c_void_p(game_hwnd), ctypes.c_void_p(-2), 0, 0, 0, 0, 0x0013)  # NOTOPMOST
            user32.SetWindowPos(ctypes.c_void_p(overlay_hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # the overlay above it
        if user32.GetForegroundWindow() != overlay_hwnd and user32.IsWindowVisible(ctypes.c_void_p(overlay_hwnd)):
            server.take_foreground(overlay_hwnd)
        if time.time() >= until:
            break
        time.sleep(0.02)  # often: a game that minimizes is back before it shows


def game_still(x, y, w, h):
    """The game's screen as it is now (a PIL image), for freeze_cover, or None."""
    try:
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    except Exception:
        return None


def freeze_cover(img, x, y, w, h, overlay_hwnd):
    """A still of the game over the whole screen, just under the overlay, while the focus moves to the overlay. Games that
    minimize themselves when they lose the focus (Hades II) would show the frontend behind them for a frame or two; with
    this up, what shows is the game as it was. A layered window made from the finished picture: Windows composites it
    as it is, with no painting and no fade. Returns an Event that takes it away once set, or None."""
    shown, done = threading.Event(), threading.Event()
    threading.Thread(target=cover_window, args=[img, x, y, w, h, overlay_hwnd, shown, done], daemon=True).start()
    return done if shown.wait(0.5) else None


def cover_window(img, x, y, w, h, overlay_hwnd, shown, done):
    import ctypes
    import ctypes.wintypes as W
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                    ("biCompression", W.DWORD), ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                    ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]

    class Blend(ctypes.Structure):
        _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    user32.GetDC.restype = gdi32.CreateCompatibleDC.restype = gdi32.CreateDIBSection.restype = gdi32.SelectObject.restype = ctypes.c_void_p
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(BIH), W.UINT, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, W.DWORD]
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    user32.UpdateLayeredWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(W.POINT), ctypes.POINTER(W.SIZE), ctypes.c_void_p,
                                           ctypes.POINTER(W.POINT), W.DWORD, ctypes.POINTER(Blend), W.DWORD]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
    user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    user32.PeekMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.UINT, W.UINT, W.UINT]
    user32.TranslateMessage.argtypes = user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    hwnd = screen = mem = bmp = None
    try:
        # layered, a tool window (no taskbar button), never activated, topmost; a plain popup: no caption, no animation
        hwnd = user32.CreateWindowExW(0x80000 | 0x80 | 0x08000000 | 0x8, "Static", None, 0x80000000, x, y, w, h, None, None, None, None)
        if not hwnd:
            return
        off = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 3, ctypes.byref(off), 4)  # DWMWA_TRANSITIONS_FORCEDISABLED
        pic = img.resize((w, h)) if img.size != (w, h) else img
        r, g, b = pic.split()
        from PIL import Image
        data = Image.merge("RGBA", (b, g, r, Image.new("L", pic.size, 255))).tobytes()  # BGRA, opaque
        info = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(mem, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, data, len(data))
        old = gdi32.SelectObject(mem, bmp)
        user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(W.POINT(x, y)), ctypes.byref(W.SIZE(w, h)), mem, ctypes.byref(W.POINT(0, 0)),
                                   0, ctypes.byref(Blend(0, 0, 255, 1)), 2)  # AC_SRC_OVER, opaque, AC_SRC_ALPHA; ULW_ALPHA
        gdi32.SelectObject(mem, old)
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        user32.SetWindowPos(ctypes.c_void_p(overlay_hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # the overlay stays above it
        shown.set()
        msg = W.MSG()
        while not done.wait(0.01):  # this thread owns the window: it answers Windows while the still is up
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
    except Exception:
        pass
    finally:
        if hwnd:
            user32.DestroyWindow(hwnd)
        if bmp:
            gdi32.DeleteObject(bmp)
        if mem:
            gdi32.DeleteDC(mem)
        if screen:
            user32.ReleaseDC(None, screen)


def lift_cover(done, game_hwnd, since=0.0, longest=2.0):
    """Take the still away as soon as the game is back on screen behind the overlay and has drawn a new frame since the
    focus moved (the live capture says when): a fraction of a second, at most two."""
    import ctypes
    user32 = ctypes.windll.user32
    start, steady = time.time(), 0
    time.sleep(0.06)
    while time.time() - start < longest:
        steady = steady + 1 if not (game_hwnd and user32.IsIconic(ctypes.c_void_p(game_hwnd))) else 0
        drawn = OVL.get("frame_at", 0) > max(since, OVL.get("restored_at", 0))
        if steady >= 3 and (drawn or time.time() - start > 0.35):  # back, and drawing (or no capture to tell: a moment)
            break
        time.sleep(0.015)
    done.set()


def overlay_slide(show, ms=190):
    """Slide the overlay in from (or out to) the right edge of the game's screen, as Quick Access does in the frontend. The
    window moves and a region clips it to that screen, so no part of it shows on a monitor beside this one. Moving a window
    doesn't redraw the page, so it's smooth."""
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
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), x + (w - part), y, w, h, 0x0050)  # TOPMOST, SHOWWINDOW | NOACTIVATE
        user32.SetWindowRgn(ctypes.c_void_p(hwnd), gdi32.CreateRectRgn(0, 0, part, h), True)
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
        try:  # the closing animation first, when the window is open
            if webview.windows and webview.windows[0].evaluate_js("window.playOutro ? (playOutro(), true) : false"):
                time.sleep(1.8)
        except Exception:
            pass
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


MINIMIZERS = "overlay-games.json"  # {game program: True if it minimizes when it loses the focus}, learned as the menu opens


def minimizes(game_hwnd):
    """Whether this game minimizes itself when the menu takes the focus: None if not seen yet."""
    exe = os.path.basename(server.process_image(window_pid(game_hwnd)) or "").lower() if game_hwnd else ""
    return server.load(MINIMIZERS, {}).get(exe) if exe else None, exe


def window_pid(hwnd):
    import ctypes
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    return pid.value


def overlay():
    """The in-game overlay: a topmost side panel, so the live game stays in full view beside it. (A transparent WebView2
    window shows its own backdrop, not what is behind it, so a full-screen page can't be see-through.)
    With --warm it's made ahead, hidden, while a game runs, and waits for the helper to ask for it: opening is then only
    the slide, with no program to start (which used to hold a still of the game on screen for a second)."""
    import ctypes
    webview_args()
    warm = "--warm" in sys.argv
    scale = ctypes.windll.user32.GetDpiForSystem() / 96 or 1
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    at = {}

    def place():
        """Where the panel goes: the right of the game's screen, Quick Access's width (62% of the height)."""
        sx, sy, sw, sh = game_screen()
        ow = min(int(sh * .62), sw)  # never wider than a portrait screen
        at.update(screen=(sx, sy, sw, sh), rect=(sx + sw - ow, sy, ow, sh), game=user32.GetForegroundWindow())
    place()
    cover, still = None, None
    if not warm:  # opened cold: a still goes up first, since this program's own windows can take the focus as they're made
        still, cover = cover_up(at)
    x, y, ow, h = at["rect"]
    window = webview.create_window("Ultra Front End Overlay", URL + "/overlay.html" + ("?warm" if warm else ""),
                                   x=int(x / scale), y=int(y / scale), width=int(ow / scale), height=int(h / scale),
                                   on_top=True, frameless=True, easy_drag=False, background_color="#1c1d1f", hidden=True, js_api=Api())

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
        nonlocal cover, still
        waiting = warm
        while True:  # one program for the whole game: shown when asked for, hidden after, until the game ends
            if waiting:
                window_log("overlay: ready, waiting")
                if not wait_for_wake("open"):
                    os._exit(0)  # the game ended: nothing to open over
                t0 = time.perf_counter()
                place()
                still, cover = cover_up(at)
                window.evaluate_js("wake()")
                window_log(f"overlay: woken, still {'up' if cover else 'not needed'} after {(time.perf_counter() - t0) * 1000:.0f} ms")
            reveal(window, raw, at, still, cover)
            if not wait_for_wake("hide"):
                os._exit(0)
            put_away(window, raw)
            waiting = True
    webview.start(edge_to_edge, private_mode=True, storage_path=os.path.join(server.DATA, "webview-overlay"))
    os._exit(0)


def hud():
    """The in-game display: a small topmost card in the top-left corner of the game's screen for add-ons (the
    performance overlay has the top right). It's see-through to
    clicks and never takes the focus (WS_EX_TRANSPARENT | WS_EX_NOACTIVATE), so the game keeps the controller and the
    mouse; it isn't in the taskbar or Alt+Tab (WS_EX_TOOLWINDOW). The page sizes it to its cards, and closes it when
    there's nothing to show or the game has ended."""
    import ctypes
    webview_args()
    scale = ctypes.windll.user32.GetDpiForSystem() / 96 or 1
    sx, sy, sw, sh = game_screen()
    width = int(sh * .24)
    margin = int(sh * .025)

    class HudApi:
        def size(self, h):
            try:
                h = max(1, int(float(h) * scale))
                window.resize(int(width / scale), int(h / scale))
                window.move(int((sx + margin) / scale), int((sy + margin) / scale))
            except Exception:
                pass

        def quit(self):
            os._exit(0)

    window = webview.create_window("Ultra Front End HUD", URL + "/hud.html", x=int((sx + margin) / scale), y=int((sy + margin) / scale),
                                   width=int(width / scale), height=int(sh * .1 / scale), on_top=True, frameless=True, easy_drag=False,
                                   focus=False, background_color="#141518", hidden=True, js_api=HudApi())

    def styles():
        window.events.loaded.wait(15)
        try:
            raw = int(window.native.Handle.ToInt64())
        except Exception:
            raw = server.frontend_window("Ultra Front End HUD")
        hwnd = ctypes.c_void_p(raw)
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | 0x20 | 0x80000 | 0x8000000 | 0x80)  # transparent, layered, no-activate, tool window
        user32.SetLayeredWindowAttributes(hwnd, 0, 222, 2)  # LWA_ALPHA: a little see-through, like glass
        round = ctypes.c_int(2)  # DWMWCP_ROUND: Windows 11's rounded corners
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(round), ctypes.sizeof(round))
        no_border = ctypes.c_uint(0xFFFFFFFE)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
        try:  # shown through WinForms so the page draws (a window shown by Windows alone stays blank); with no-activate set
            from System import Func, Type  # above, it doesn't take the focus from the game
            window.native.Invoke(Func[Type](lambda: window.native.Show()))
        except Exception:
            user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # topmost, no move, no size, no activate
        window_log("hud: shown")
    webview.start(styles, private_mode=True, storage_path=os.path.join(server.DATA, "webview-hud"))
    os._exit(0)


def wait_for_wake(want):
    """The overlay waits here for the helper: True when the menu is asked for ("open") or put away ("hide"), False when
    the game has ended (or the helper has gone)."""
    while True:
        try:
            with urllib.request.urlopen(URL + f"/api/overlay/wake?want={want}", timeout=30) as r:
                answer = json.load(r)
        except (OSError, ValueError):
            if not helper_up():
                return False
            time.sleep(0.5)
            continue
        if answer.get(want):
            return True
        if answer.get("quit"):
            return False


def put_away(window, raw):
    """Hidden again (it has slid out already), its capture stopped, ready for the next time."""
    import ctypes
    OVL["closing"], OVL["gone"] = True, True
    try:
        window.evaluate_js("hidden()")
    except Exception:
        pass
    try:
        from System import Func, Type
        window.native.Invoke(Func[Type](lambda: window.native.Hide()))
    except Exception:
        ctypes.windll.user32.ShowWindow(ctypes.c_void_p(raw), 0)


def cover_up(at):
    """A still of the game over its screen, under the menu, for the moment the focus moves to the menu, if this game
    minimizes itself then (it would flash the desktop otherwise). Games known not to get none: they never stop moving.
    Returns (the still, the Event that lifts it) or (still or None, None)."""
    import ctypes
    known, _ = minimizes(at["game"])
    still = game_still(*at["screen"])
    if known is False or still is None:
        return still, None
    t0 = time.perf_counter()
    cover = freeze_cover(still, *at["screen"], 0)
    window_log(f"overlay: still {'up' if cover else 'too slow'} after {(time.perf_counter() - t0) * 1000:.0f} ms; "
               f"game {'minimized' if at['game'] and ctypes.windll.user32.IsIconic(ctypes.c_void_p(at['game'])) else 'on screen'}")
    return still, cover


def reveal(window, raw, at, still, cover):
    """Show the menu and slide it in over the game, with the game's frosted frame behind it from the first moment."""
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = ctypes.c_void_p(raw)
    x, y, ow, h = at["rect"]
    game = at["game"]
    if True:
        sx, sy = at["screen"][:2]
        if still is not None:  # the first frame from the still just taken; the live capture takes over within a frame or two
            try:
                window.evaluate_js(f"frost('{frost_url(still.crop((x - sx, y - sy, x - sx + ow, y - sy + h)), scale=3)}')")
            except Exception:
                pass
        OVL.update(hwnd=raw, rect=(x, y, ow, h), closing=False, gone=False, minimized=False, frame_at=0.0)
        threading.Thread(target=live_backdrop, args=[window, game, x, y, ow, h], daemon=True).start()  # frames from now on
        # at the screen's right edge with only a sliver in its region: showing it (below) can't put a dark, still empty
        # panel in view; the slide brings it in once the page has drawn (a window wholly off screen wouldn't draw at all)
        user32.SetWindowRgn(hwnd, ctypes.windll.gdi32.CreateRectRgn(0, 0, 2, h), False)
        user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), x + ow - 2, y, ow, h, 0x0010)  # HWND_TOPMOST, SWP_NOACTIVATE, still hidden
        try:  # shown through WinForms, so the page inside starts drawing (a window shown by Windows alone stays blank);
            from System import Func, Type  # not window.show(), which would take the focus from the game
            window.native.Invoke(Func[Type](lambda: window.native.Show()))
        except Exception:
            window.show()
        # from now: the game stops taking the controls, and if it minimized it goes straight back behind the still
        focus_at = time.time()
        threading.Thread(target=take_focus, args=[raw, 3, game], daemon=True).start()
        window.evaluate_js("document.body.classList.add('on')")
        deadline = time.time() + 0.8  # drawn, frosted and faded in before any of it comes into view (else a dark block shows)
        while time.time() < deadline:
            try:
                if window.evaluate_js("(!document.body.style.backgroundImage || document.body.classList.contains('glass')) && getComputedStyle(document.body).opacity === '1'"):
                    break
            except Exception:
                break
            time.sleep(0.03)
        time.sleep(0.05)  # that frame on screen
        if cover:  # away as soon as the game is back on screen and drawing behind the menu
            threading.Thread(target=lift_cover, args=[cover, game, focus_at], daemon=True).start()
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
        threading.Thread(target=note_minimizes, args=[game], daemon=True).start()


def note_minimizes(game):
    """Remember whether this game minimized itself when the menu took the focus: one that doesn't needs no still next time."""
    time.sleep(3.2)  # take_focus has watched for 3 seconds by then
    known, exe = minimizes(game)
    seen = bool(OVL.get("minimized"))
    if exe and known is not seen:
        try:
            server.store(MINIMIZERS, {**server.load(MINIMIZERS, {}), exe: seen})
        except OSError:
            pass
        window_log(f"overlay: {exe} {'minimizes' if seen else 'stays on screen'} when the menu opens")


FROST_SCALE = 6  # the frost is worked on at a sixth of the size: blurred anyway, and quick


FROST_BLUR = 24  # the blur's reach in screen pixels, whatever size the frost is worked on at


def frost_url(img, scale=None):
    """A frosted version of the game behind the overlay, as a small data URL the page stretches over its background:
    blurred, and darkened only a little, so the game shows through while white text stays readable. Shrunk by averaging
    (no blocks), blurred to the same reach at any size, and saved well enough that the blur shows no JPEG banding."""
    import base64
    import io
    from PIL import ImageFilter
    scale = scale or FROST_SCALE
    small = img.convert("RGB").reduce(scale)
    small = small.filter(ImageFilter.GaussianBlur(FROST_BLUR / scale)).point(lambda v: int(v * .72 + 6))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=90)
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


def wgc_module():
    """Windows Graphics Capture (the windows-capture project's native module, loaded on its own: its Python wrapper would
    pull in OpenCV). None if it isn't there or won't load."""
    import importlib.machinery
    import importlib.util
    try:
        if getattr(sys, "frozen", False):
            pyd = os.path.join(sys._MEIPASS, "windows_capture.pyd")
        else:
            spec = importlib.util.find_spec("windows_capture")
            pyd = os.path.join(list(spec.submodule_search_locations)[0], "windows_capture.pyd") if spec else ""
        if not os.path.isfile(pyd):
            return None
        loader = importlib.machinery.ExtensionFileLoader("windows_capture", pyd)
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader("windows_capture", loader))
        loader.exec_module(module)
        return module
    except Exception:
        return None


LIVE_FPS = 30  # backdrop frames a second: smooth behind a blur, and light (about 5 ms of work each)


def live_backdrop(window, game, x, y, w, h):
    """The overlay's backdrop, live: the game's own frames from Windows Graphics Capture (as OBS and the Xbox Game Bar get
    them, from the graphics card, without touching the game), cut to the panel, blurred small and sent to the page about
    30 times a second. Games it can't capture (exclusive fullscreen) keep the older way: a frame drawn a few times a second."""
    import ctypes
    import ctypes.wintypes as W
    from PIL import Image
    wc = wgc_module() if game else None
    if not wc:
        return live_frost(window, game, x, y, w, h)
    r = W.RECT()
    ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(game), ctypes.byref(r))
    latest, ready, frames = [None], threading.Event(), [0]

    def on_frame(frame, buf_len, width, height, stop_list, _timespan):
        if OVL.get("gone"):
            stop_list.append(True)
            return
        try:
            k = width / max(1, r.right - r.left)  # the frame's pixels per screen pixel (DPI, a window bigger than its frame)
            fx, fy = max(0, int((x - r.left) * k)), max(0, int((y - r.top) * k))
            fw, fh = min(width - fx, int(w * k)), min(height - fy, int(h * k))
            if fw < 8 or fh < 8:
                return
            pitch = int(frame.bytes_per_row)
            view = memoryview(frame.buffer_view())[fy * pitch + fx * 4:]  # only the panel's strip is read
            strip = Image.frombuffer("RGB", (fw, fh), view, "raw", "BGRX", pitch, 1)
            latest[0] = frost_url(strip, scale=3)
            frames[0] += 1
            OVL["frame_at"] = time.time()
            ready.set()
        except Exception:
            pass

    try:
        cap = wc.NativeWindowsCapture(on_frame, lambda: None, False, False, None, 1000 // LIVE_FPS, None, None, None, int(game))
        control = cap.start_free_threaded()
    except Exception:
        return live_frost(window, game, x, y, w, h)
    if not ready.wait(1.5):  # nothing comes from a game in exclusive fullscreen
        try:
            control.stop()
        except Exception:
            pass
        window_log("overlay: live capture gave no frames, using drawn frames")
        return live_frost(window, game, x, y, w, h)
    window_log("overlay: live capture")
    try:
        while not OVL.get("gone"):  # the newest frame only: a slow page skips frames rather than falling behind
            if ready.wait(1):
                ready.clear()
                window.evaluate_js(f"frost('{latest[0]}')")
    except Exception:
        pass
    finally:
        try:
            control.stop()
        except Exception:
            pass


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


def move_to_applications_mac():
    """Opened straight from the disk image (macOS then runs it from a hidden read-only copy), it couldn't update itself:
    offer to copy it to Applications and open it from there. True when it did, so this copy leaves."""
    import glob
    import shutil
    bundle = server.mac_bundle()
    if not (bundle.startswith("/Volumes/") or "/AppTranslocation/" in bundle):
        return False
    name = os.path.basename(bundle)
    source = bundle if bundle.startswith("/Volumes/") else next(iter(glob.glob(os.path.join("/Volumes", "*", name))), "")
    if not source:
        return False
    from AppKit import NSAlert, NSApplication
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    alert = NSAlert.alloc().init()
    alert.setMessageText_("Move Ultra Front End to Applications?")
    alert.setInformativeText_("It's running from the disk image, so it can't update itself and won't be in your Applications "
                              "folder next time. It's moved, then opens from there.")
    alert.addButtonWithTitle_("Move to Applications")
    alert.addButtonWithTitle_("Not Now")
    if alert.runModal() != 1000:  # NSAlertFirstButtonReturn
        return False
    apps = "/Applications" if os.access("/Applications", os.W_OK) else os.path.expanduser("~/Applications")
    dest = os.path.join(apps, name)
    try:
        os.makedirs(apps, exist_ok=True)
        if os.path.exists(dest):  # an older copy: to the Trash, so it can be put back
            from Foundation import NSFileManager, NSURL
            NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(NSURL.fileURLWithPath_(dest), None, None)
            if os.path.exists(dest):
                shutil.rmtree(dest)
        subprocess.run(["/usr/bin/ditto", source, dest], check=True, capture_output=True)
        # the person already allowed this app to open; the copy shouldn't ask again
        subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", dest], capture_output=True)
    except (OSError, subprocess.CalledProcessError) as e:
        window_log(f"move to Applications failed: {e}")
        return False
    window_log(f"moved to {dest}")
    subprocess.Popen(["/bin/sh", "-c", 'sleep 1; open -n "$0"', dest], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def main():
    logging.getLogger("pywebview").addHandler(WindowLogHandler(logging.WARNING))
    window_log(f"start {' '.join(sys.argv[1:]) or '(window)'} from parent {os.getppid()}")
    if "--overlay" in sys.argv:
        return overlay()
    if "--hud" in sys.argv:
        return hud()
    if "--install-broker" in sys.argv:  # the elevated install helper for setup (one administrator prompt): no window, no tray
        i = sys.argv.index("--install-broker")
        return server.install_broker(sys.argv[i + 1], sys.argv[i + 2])
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
    if server.MAC and move_to_applications_mac():
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
        # hidden until it covers the screen: shown at its first size it flashes a light border
        window = webview.create_window("Ultra Front End", URL, frameless=True, easy_drag=False, background_color="#070c1a", hidden=True, js_api=Api())
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
    elif own and server.config().get("guideOpens") and not server.MAC:  # keep listening for the Xbox button after the window closes (a Mac app just quits)
        threading.Event().wait()
    os._exit(0)  # window closed: stop the helper threads too


def cover_screen_mac(window):
    """Hide the menu bar and Dock and stretch the window over the whole screen, notch strip included."""
    import AppKit
    from PyObjCTools import AppHelper

    window.events.loaded.wait(20)  # the window is hidden until this has run, so "shown" never comes first

    def apply():
        w, app = window.native, AppKit.NSApplication.sharedApplication()
        app.setPresentationOptions_(AppKit.NSApplicationPresentationHideDock | AppKit.NSApplicationPresentationHideMenuBar)
        w.setStyleMask_(AppKit.NSWindowStyleMaskBorderless)
        w.setHasShadow_(False)
        w.setBackgroundColor_(AppKit.NSColor.colorWithRed_green_blue_alpha_(7 / 255, 12 / 255, 26 / 255, 1))
        w.setFrame_display_((w.screen() or AppKit.NSScreen.mainScreen()).frame(), True)
        content = w.contentView()
        for view in content.subviews():  # the page keeps its first size unless it's told to fill the window
            view.setFrame_(content.bounds())
            view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        app.activateIgnoringOtherApps_(True)
        if hasattr(app, "activate"):  # macOS 14 and later ignore the call above
            app.activate()
        w.makeKeyAndOrderFront_(None)
        window_log(f"window {w.frame().size.width:.0f}x{w.frame().size.height:.0f}; page {[f'{v.frame().size.width:.0f}x{v.frame().size.height:.0f}' for v in content.subviews()]}; "
                   f"screen {(w.screen() or AppKit.NSScreen.mainScreen()).frame().size.height:.0f} high; key {w.isKeyWindow()}")  # for checking the result remotely
    AppHelper.callAfter(apply)
    time.sleep(3)
    try:  # what the page itself measures, for checking the result remotely (the web view can size its page apart from the window)
        window_log("page sees " + str(window.evaluate_js(
            "JSON.stringify({inner: innerWidth + 'x' + innerHeight, doc: document.documentElement.clientHeight, screen: screen.width + 'x' + screen.height,"
            " dpr: devicePixelRatio, body: getComputedStyle(document.body).height, layers: [...document.querySelectorAll('#sky,#far,#near,#water,#buttons')]"
            ".map(e => e.id + ':' + Math.round(e.getBoundingClientRect().bottom)).join(' ')})")))
    except Exception as e:
        window_log(f"page size: couldn't ask ({e})")


if __name__ == "__main__":
    main()
