"""The macOS side of the helper's Windows-only pieces. server.py hands over to these on a Mac (each Windows function starts
with `if MAC: return plat_mac.<name>(...)`), so the Windows code stays exactly as it was. Windows never imports this module.

Processes come from psutil; windows and focus from macOS's own frameworks through PyObjC (pywebview's Cocoa window
already needs PyObjC); volume and power from AppleScript (osascript) and pmset, which need no permission prompts."""
import os
import subprocess
import time


def _ps():
    import psutil
    return psutil


# ---------- processes ----------
def process_birth(pid):
    """When this process started (seconds), or 0 if it has gone: a pid can be reused, so a pid alone doesn't say it's the same program."""
    psutil = _ps()
    try:
        p = psutil.Process(pid)
        return 0 if p.status() == psutil.STATUS_ZOMBIE else p.create_time()
    except (psutil.Error, OSError):
        return 0


def process_tree(pid):
    """The process and its descendants still running."""
    psutil = _ps()
    try:
        p = psutil.Process(pid)
        return {pid} | {c.pid for c in p.children(recursive=True)}
    except (psutil.Error, OSError):
        return set()


def process_image(pid):
    """The program a process runs, or "" if it can't be read."""
    psutil = _ps()
    try:
        return psutil.Process(pid).exe() or ""
    except (psutil.Error, OSError):
        return ""


def folder_processes(folder):
    """Running programs whose file lives in this folder or below it (an .app counts as a folder)."""
    psutil = _ps()
    root, found = os.path.realpath(folder.rstrip("/")) + "/", set()
    for p in psutil.process_iter(["exe"]):
        exe = p.info.get("exe") or ""
        if exe and os.path.realpath(exe).startswith(root):
            found.add(p.pid)
    return found


def kill_tree(pid, grace=3.0):
    """Close a game: ask the app to quit, then end what's left of its tree."""
    psutil = _ps()
    tree = process_tree(pid)
    app = _running_app(pid)
    if app is not None:
        app.terminate()
    procs = []
    for p in tree:
        try:
            procs.append(psutil.Process(p))
        except psutil.Error:
            pass
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=grace)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass


def child_env():
    """The environment for a game or emulator: without the frozen app's own library paths, which would make a child load
    our copies of libraries instead of its own."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI_", "DYLD_"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


# ---------- windows and focus ----------
def _running_app(pid):
    try:
        from AppKit import NSRunningApplication
        return NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
    except Exception:
        return None


def activate(pid):
    """Bring a program's windows to the front (restoring it if it was hidden). True if it could."""
    app = _running_app(pid)
    if app is None:
        return False
    try:
        app.unhide()
        return bool(app.activateWithOptions_(1 | 2))  # NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps
    except Exception:
        return False


def front_pid():
    """The program in front, or 0."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return int(app.processIdentifier()) if app else 0
    except Exception:
        return 0


def windows():
    """Normal windows on screen, front to back: [(window number, pid, (x, y, w, h))], at least 300x200."""
    try:
        import Quartz
        info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID) or []
    except Exception:
        return []
    out = []
    for w in info:
        if int(w.get("kCGWindowLayer", 1)) != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        box = (int(b.get("X", 0)), int(b.get("Y", 0)), int(b.get("Width", 0)), int(b.get("Height", 0)))
        if box[2] >= 300 and box[3] >= 200:
            out.append((int(w.get("kCGWindowNumber", 0)), int(w.get("kCGWindowOwnerPID", 0)), box))
    return out


def screen_points():
    """The main screen's size in points (window bounds are in points)."""
    try:
        import Quartz
        b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        return int(b.size.width), int(b.size.height)
    except Exception:
        return 0, 0


def fullscreen_pid():
    """The program in front, if its window covers the whole main screen (a game played full screen), or 0."""
    pid, (sw, sh) = front_pid(), screen_points()
    if not pid or not sw:
        return 0
    for _, owner, (x, y, w, h) in windows():
        if owner == pid:
            return pid if x <= 0 and y <= 0 and w >= sw and h >= sh else 0
    return 0


def screen_size():
    """The main screen's resolution in pixels."""
    try:
        from AppKit import NSScreen
        s = NSScreen.mainScreen()
        f, k = s.frame(), s.backingScaleFactor()
        return int(f.size.width * k), int(f.size.height * k)
    except Exception:
        return 1920, 1080


# ---------- system ----------
def _osa(script):
    r = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode:
        raise OSError((r.stderr or "osascript failed").strip())
    return r.stdout.strip()


def audio_volume(level=None, delta=None, mute=None):
    """The output volume: {"volume": 0-100, "muted": bool}. level, delta and mute change it first (raising it unmutes, as on Windows)."""
    # "output volume:75, input volume:44, alert volume:0, output muted:false" (volume is "missing value" with no output device)
    now = dict(part.strip().split(":", 1) for part in _osa("get volume settings").split(",") if ":" in part)
    vol = int(now.get("output volume", "0")) if now.get("output volume", "").isdigit() else 0
    muted = now.get("output muted", "false").strip() == "true"
    if level is not None or delta is not None:
        new = max(0, min(100, int(level if level is not None else vol + delta)))
        raised = new > vol
        _osa(f"set volume output volume {new}" + (" without output muted" if raised else ""))
        vol, muted = new, muted and not raised
    if mute is not None:
        _osa("set volume " + ("with" if mute else "without") + " output muted")
        muted = bool(mute)
    return {"volume": vol, "muted": muted}


def system_power(action):
    """Sleep now; restart and shut down after a few seconds, through System Events (macOS asks apps to quit first)."""
    import threading
    if action == "sleep":
        threading.Timer(1.0, lambda: subprocess.run(["/usr/bin/pmset", "sleepnow"], capture_output=True)).start()
    elif action in ("restart", "shutdown"):
        verb = "restart" if action == "restart" else "shut down"
        threading.Timer(3.0, lambda: subprocess.run(["/usr/bin/osascript", "-e", f'tell application "System Events" to {verb}'], capture_output=True)).start()
    else:
        raise ValueError("Unknown power action")


SOUND = [None]


def play_sound(path):
    stop_sound()
    if path and os.path.isfile(path):
        SOUND[0] = subprocess.Popen(["/usr/bin/afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_sound():
    p, SOUND[0] = SOUND[0], None
    if p and p.poll() is None:
        p.terminate()


def read_clipboard():
    return subprocess.run(["/usr/bin/pbpaste"], capture_output=True, text=True, timeout=5).stdout


def app_executable(path):
    """The program inside an .app bundle (Contents/MacOS/<CFBundleExecutable>), or the path itself."""
    if path.rstrip("/").endswith(".app") and os.path.isdir(path):
        import plistlib
        try:
            with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
                name = plistlib.load(f).get("CFBundleExecutable")
        except (OSError, ValueError):
            name = None
        exe = os.path.join(path, "Contents", "MacOS", name or os.path.splitext(os.path.basename(path.rstrip("/")))[0])
        if os.path.isfile(exe):
            return exe
    return path
