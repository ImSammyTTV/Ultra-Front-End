"""The Linux side of the helper's Windows-only pieces (the Steam Deck first: SteamOS in Game Mode and Desktop Mode).
server.py hands over to these on Linux the way it does to plat_mac on a Mac (`if POSIX: return PLAT.<name>(...)`), so the
Windows and Mac code stay exactly as they were. Windows and macOS never import this module.

Everything here uses what a Linux desktop already has, with no Python packages: processes from /proc, windows and focus
from X11 through libX11 (the Deck's Desktop Mode, and Game Mode's Xwayland; under a plain Wayland session the window
pieces quietly do nothing), the controller from evdev (/dev/input), volume from PipeWire's wpctl or PulseAudio's pactl,
power from systemd (logind lets the person at the screen suspend and restart), file pickers from zenity or kdialog."""
import ctypes
import ctypes.util
import os
import re
import shutil
import signal
import struct
import subprocess
import threading
import time

HOME = os.path.expanduser("~")


def _xdg(var, default):
    return os.environ.get(var) or os.path.join(HOME, default)


DATA_HOME, CONFIG_HOME = _xdg("XDG_DATA_HOME", ".local/share"), _xdg("XDG_CONFIG_HOME", ".config")


# ---------- the environment children get ----------
def child_env():
    """The environment for a game, emulator, Steam or any tool started from here, without what the packaged app set up for
    itself: PyInstaller points LD_LIBRARY_PATH at its own copies of libraries (keeping the old value as LD_LIBRARY_PATH_ORIG),
    and an AppImage adds its own mount. A child given those loads our libraries instead of the system's (Steam and Flatpak
    break on them)."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("_PYI_", "PYINSTALLER_")) and k not in ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "QT_PLUGIN_PATH",
                                                                       "QTWEBENGINEPROCESS_PATH", "QTWEBENGINE_RESOURCES_PATH",
                                                                       "QML2_IMPORT_PATH", "GIO_MODULE_DIR", "GDK_PIXBUF_MODULE_FILE",
                                                                       "GI_TYPELIB_PATH", "SSL_CERT_FILE", "TCL_LIBRARY", "TK_LIBRARY")}
    # (LD_PRELOAD is left alone: Steam sets it for its overlay, which games started from here should get too)
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    elif getattr(__import__("sys"), "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)  # set only by the packaged app: none at all
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def popen(cmd, **kw):
    """subprocess.Popen with the clean environment, detached from this program's session (a game outlives the frontend)."""
    kw.setdefault("env", child_env())
    kw.setdefault("start_new_session", True)
    return subprocess.Popen(cmd, **kw)


def run(cmd, timeout=10, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=child_env(), **kw)


# ---------- processes (from /proc) ----------
def _stat(pid):
    """(state, parent pid, start time in clock ticks) from /proc/<pid>/stat, or None if it has gone."""
    try:
        with open(f"/proc/{int(pid)}/stat", "rb") as f:
            data = f.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    rest = data[data.rfind(")") + 2:].split()  # the name (field 2) can hold spaces and brackets: everything after its last ')'
    try:
        return rest[0], int(rest[1]), int(rest[19])
    except (IndexError, ValueError):
        return None


def _pids():
    try:
        return [int(n) for n in os.listdir("/proc") if n.isdigit()]
    except OSError:
        return []


def process_birth(pid):
    """When this process started (clock ticks since boot), or 0 if it has gone or is a zombie: a pid can be reused, so a pid
    alone doesn't say it's the same program."""
    s = _stat(pid)
    return 0 if not s or s[0] in ("Z", "X") else s[2] or 1


def process_tree(pid):
    """The process and its descendants still running (even if it has exited, its children may still name it as parent:
    on Linux an orphan is handed to init or a subreaper, so once the launcher is gone game_tree follows what it saw)."""
    parents = {}
    for p in _pids():
        s = _stat(p)
        if s and s[0] not in ("Z", "X"):
            parents[p] = s[1]
    tree = {pid}
    while True:
        more = {p for p, pp in parents.items() if pp in tree and p not in tree}
        if not more:
            break
        tree |= more
    return tree & set(parents)


def process_image(pid):
    """The program a process runs, or "" if it can't be read."""
    try:
        return os.readlink(f"/proc/{int(pid)}/exe").removesuffix(" (deleted)")
    except (OSError, ValueError):
        return ""


def folder_processes(folder):
    """Running programs whose file lives in this folder or below it."""
    root, found = os.path.realpath(folder.rstrip("/")) + "/", set()
    for p in _pids():
        exe = process_image(p)
        if exe and exe.startswith(root):
            found.add(p)
    return found


def kill_tree(pid, grace=3.0):
    """Close a game: ask its whole tree to quit (SIGTERM), then end what's left."""
    tree = process_tree(pid)
    for p in tree:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + grace
    while time.time() < deadline and any(process_birth(p) for p in tree):
        time.sleep(0.1)
    for p in tree:
        if process_birth(p):
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass


# ---------- windows and focus (X11, through libX11) ----------
class _ClientMessage(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong), ("format", ctypes.c_int), ("data", ctypes.c_long * 5)]


class _XEvent(ctypes.Union):
    _fields_ = [("xclient", _ClientMessage), ("pad", ctypes.c_long * 24)]


X = {"lib": None, "d": None, "tried": False, "atoms": {}}
X_LOCK = threading.Lock()  # one connection, used from several threads: one call at a time


def _x():
    """The X display (the Deck's Desktop Mode, Game Mode's Xwayland), or None: then the window pieces do nothing."""
    if X["tried"]:
        return X["d"]
    X["tried"] = True
    if not os.environ.get("DISPLAY"):
        return None
    try:
        lib = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
    except OSError:
        return None
    vp, ul, ui, i = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_int
    lib.XOpenDisplay.restype, lib.XOpenDisplay.argtypes = vp, [ctypes.c_char_p]
    lib.XDefaultRootWindow.restype, lib.XDefaultRootWindow.argtypes = ul, [vp]
    lib.XInternAtom.restype, lib.XInternAtom.argtypes = ul, [vp, ctypes.c_char_p, i]
    lib.XGetWindowProperty.argtypes = [vp, ul, ul, ctypes.c_long, ctypes.c_long, i, ul, ctypes.POINTER(ul), ctypes.POINTER(i),
                                       ctypes.POINTER(ul), ctypes.POINTER(ul), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))]
    lib.XFree.argtypes = [vp]
    lib.XGetGeometry.argtypes = [vp, ul, ctypes.POINTER(ul), ctypes.POINTER(i), ctypes.POINTER(i), ctypes.POINTER(ui), ctypes.POINTER(ui),
                                 ctypes.POINTER(ui), ctypes.POINTER(ui)]
    lib.XTranslateCoordinates.argtypes = [vp, ul, ul, i, i, ctypes.POINTER(i), ctypes.POINTER(i), ctypes.POINTER(ul)]
    lib.XSendEvent.argtypes = [vp, ul, i, ctypes.c_long, ctypes.POINTER(_XEvent)]
    lib.XMapRaised.argtypes = [vp, ul]
    lib.XFlush.argtypes = [vp]
    lib.XDefaultScreen.argtypes = [vp]
    lib.XDisplayWidth.argtypes = lib.XDisplayHeight.argtypes = [vp, i]
    lib.XSetErrorHandler.restype = vp
    # Xlib's default error handler ends the program (a window that closed between two calls is enough): ignore errors instead
    X["on_error"] = ctypes.CFUNCTYPE(ctypes.c_int, vp, vp)(lambda d, e: 0)
    lib.XSetErrorHandler(X["on_error"])
    d = lib.XOpenDisplay(None)
    if not d:
        return None
    X["lib"], X["d"] = lib, d
    return d


def _atom(name):
    a = X["atoms"].get(name)
    if a is None:
        a = X["atoms"][name] = X["lib"].XInternAtom(X["d"], name.encode(), 0)
    return a


def _prop_longs(win, name):
    """A 32-bit property (window ids, pids, cardinals) as a list of numbers."""
    lib, d = X["lib"], X["d"]
    t, fmt, n, after = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    if lib.XGetWindowProperty(d, win, _atom(name), 0, 4096, 0, 0, ctypes.byref(t), ctypes.byref(fmt), ctypes.byref(n), ctypes.byref(after),
                              ctypes.byref(data)) != 0 or not data:
        return []
    try:
        if fmt.value != 32:
            return []
        return list(ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[:n.value])  # format 32 comes as C longs
    finally:
        lib.XFree(data)


def _geometry(win):
    lib, d = X["lib"], X["d"]
    root, x, y, w, h, bw, depth = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    if not lib.XGetGeometry(d, win, ctypes.byref(root), ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h), ctypes.byref(bw),
                            ctypes.byref(depth)):
        return None
    ax, ay, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
    lib.XTranslateCoordinates(d, win, root.value, 0, 0, ctypes.byref(ax), ctypes.byref(ay), ctypes.byref(child))
    return ax.value, ay.value, w.value, h.value


def _client_windows():
    """Top-level windows the window manager manages, front to back."""
    root = X["lib"].XDefaultRootWindow(X["d"])
    wins = _prop_longs(root, "_NET_CLIENT_LIST_STACKING") or _prop_longs(root, "_NET_CLIENT_LIST")
    return list(reversed(wins))


def windows():
    """Normal windows on screen, front to back: [(window id, pid, (x, y, w, h))], at least 300x200. Empty without X11."""
    with X_LOCK:
        if not _x():
            return []
        out = []
        try:
            for w in _client_windows():
                pid = (_prop_longs(w, "_NET_WM_PID") or [0])[0]
                box = _geometry(w)
                if box and box[2] >= 300 and box[3] >= 200 and "_NET_WM_STATE_HIDDEN" not in _states(w):
                    out.append((int(w), int(pid), box))
        except Exception:
            return out
        return out


def _states(win):
    names = {_atom(n): n for n in ("_NET_WM_STATE_HIDDEN", "_NET_WM_STATE_FULLSCREEN")}
    return {names[a] for a in _prop_longs(win, "_NET_WM_STATE") if a in names}


def _send(win, message, data):
    lib, d = X["lib"], X["d"]
    root = lib.XDefaultRootWindow(d)
    ev = _XEvent()
    ev.xclient.type, ev.xclient.send_event, ev.xclient.display = 33, 1, d  # ClientMessage
    ev.xclient.window, ev.xclient.message_type, ev.xclient.format = win, _atom(message), 32
    for k, v in enumerate(data[:5]):
        ev.xclient.data[k] = v
    lib.XSendEvent(d, root, 0, (1 << 20) | (1 << 19), ctypes.byref(ev))  # SubstructureRedirect | SubstructureNotify


def activate(pid):
    """Bring a program's biggest window to the front (restoring it if it was minimized). True if it had one.
    (A Flatpak program's windows name the pid it has inside its sandbox, so those aren't found by pid.)"""
    with X_LOCK:
        if not _x():
            return False
        try:
            mine = [(w, _geometry(w)) for w in _client_windows() if (_prop_longs(w, "_NET_WM_PID") or [0])[0] == int(pid)]
            mine = [(w, g) for w, g in mine if g]
            if not mine:
                return False
            win = max(mine, key=lambda m: m[1][2] * m[1][3])[0]
            X["lib"].XMapRaised(X["d"], win)
            _send(win, "_NET_ACTIVE_WINDOW", [2, 0, 0, 0, 0])  # source 2: a pager/tool acting for the user, which window managers obey
            X["lib"].XFlush(X["d"])
            return True
        except Exception:
            return False


def front_pid():
    """The program whose window is active, 0 if none, or None when that can't be known (no X11, or a window manager such as
    Game Mode's gamescope that doesn't say)."""
    with X_LOCK:
        if not _x():
            return None
        try:
            root = X["lib"].XDefaultRootWindow(X["d"])
            active = _prop_longs(root, "_NET_ACTIVE_WINDOW")
            if not active:
                return None
            return int((_prop_longs(active[0], "_NET_WM_PID") or [0])[0]) if active[0] else 0
        except Exception:
            return None


def screen_size():
    """The screen's resolution in pixels (the Deck's 1280x800 when nothing else is known)."""
    with X_LOCK:
        if _x():
            try:
                s = X["lib"].XDefaultScreen(X["d"])
                w, h = X["lib"].XDisplayWidth(X["d"], s), X["lib"].XDisplayHeight(X["d"], s)
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
    for card in sorted(os.listdir("/sys/class/drm")) if os.path.isdir("/sys/class/drm") else []:  # a connected screen's first mode
        try:
            with open(f"/sys/class/drm/{card}/status") as f:
                if f.read().strip() != "connected":
                    continue
            with open(f"/sys/class/drm/{card}/modes") as f:
                w, h = f.readline().strip().split("x")[:2]
                return int(w), int(re.match(r"\d+", h).group(0))
        except (OSError, ValueError, AttributeError):
            continue
    return 1280, 800


def fullscreen_pid():
    """The program in front, if its window covers the whole screen (a game played full screen), or 0."""
    pid = front_pid()
    if not pid:
        return 0
    sw, sh = screen_size()
    for _, owner, (x, y, w, h) in windows():
        if owner == pid:
            return pid if x <= 0 and y <= 0 and w >= sw and h >= sh else 0
    return 0


# ---------- opening things ----------
def steam_command():
    """How to reach Steam: its own command (a Steam Deck, or Steam from the distribution), or Flatpak Steam."""
    s = shutil.which("steam")
    if s:
        return [s]
    if any(os.path.exists(os.path.join(d, "com.valvesoftware.Steam")) for d in FLATPAK_BIN):
        return ["flatpak", "run", "com.valvesoftware.Steam"]
    return None


def open_target(target):
    """Open a link, folder or file with the system. steam:// links go to Steam itself: in Game Mode there is no desktop to
    hand a link to, and a running Steam takes the link from a second `steam` call."""
    if target.startswith("steam://") and steam_command():
        return popen(steam_command() + [target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if not opener:
        raise ValueError("Nothing on this computer opens links (xdg-open is missing)")
    return popen([opener] + (["open"] if opener.endswith("gio") else []) + [target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def has_picker():
    return bool(shutil.which("zenity") or shutil.which("kdialog"))


def pick(kind, title, filetypes=None):
    """A native file or folder picker: zenity (GNOME, and SteamOS has it) or kdialog (KDE, the Deck's Desktop Mode).
    Returns the path, None if cancelled, or raises if neither is there."""
    start = HOME + "/"
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--title", title, "--filename", start] + (["--directory"] if kind == "dir" else [])
    elif shutil.which("kdialog"):
        cmd = ["kdialog", "--title", title] + (["--getexistingdirectory", start] if kind == "dir" else ["--getopenfilename", start])
    else:
        raise ValueError("No file picker on this computer: install zenity or kdialog")
    r = subprocess.run(cmd, capture_output=True, text=True, env=child_env())
    path = r.stdout.strip()
    return path.rstrip("/") or "/" if r.returncode == 0 and path else None


# ---------- system ----------
def _wpctl():
    return shutil.which("wpctl")


def audio_volume(level=None, delta=None, mute=None):
    """The default speakers: {"volume": 0-100, "muted": bool}. level, delta and mute change it first (raising it unmutes, as on
    Windows). PipeWire (wpctl: SteamOS and most new desktops), else PulseAudio (pactl). A sound server that doesn't answer
    is an OSError, like no sound output, rather than a wait that holds up the in-game menu."""
    try:
        return _audio_volume(level, delta, mute)
    except subprocess.SubprocessError as e:
        raise OSError("The sound system didn't answer") from e


def _audio_volume(level=None, delta=None, mute=None):
    if _wpctl():
        sink = "@DEFAULT_AUDIO_SINK@"
        out = run(timeout=4, cmd=["wpctl", "get-volume", sink]).stdout  # "Volume: 0.45" or "Volume: 0.45 [MUTED]"
        m = re.search(r"([\d.]+)", out)
        if not m:
            raise OSError("No sound output was found")
        vol, muted = round(float(m.group(1)) * 100), "MUTED" in out
        if level is not None or delta is not None:
            new = max(0, min(100, int(level if level is not None else vol + delta)))
            run(timeout=4, cmd=["wpctl", "set-volume", sink, f"{new / 100:.2f}"])
            if new > vol and muted:
                run(timeout=4, cmd=["wpctl", "set-mute", sink, "0"])
                muted = False
            vol = new
        if mute is not None:
            run(timeout=4, cmd=["wpctl", "set-mute", sink, "1" if mute else "0"])
            muted = bool(mute)
        return {"volume": vol, "muted": muted}
    if shutil.which("pactl"):
        sink = "@DEFAULT_SINK@"
        m = re.search(r"(\d+)%", run(timeout=4, cmd=["pactl", "get-sink-volume", sink]).stdout)
        if not m:
            raise OSError("No sound output was found")
        vol, muted = int(m.group(1)), "yes" in run(timeout=4, cmd=["pactl", "get-sink-mute", sink]).stdout
        if level is not None or delta is not None:
            new = max(0, min(100, int(level if level is not None else vol + delta)))
            run(timeout=4, cmd=["pactl", "set-sink-volume", sink, f"{new}%"])
            if new > vol and muted:
                run(timeout=4, cmd=["pactl", "set-sink-mute", sink, "0"])
                muted = False
            vol = new
        if mute is not None:
            run(timeout=4, cmd=["pactl", "set-sink-mute", sink, "1" if mute else "0"])
            muted = bool(mute)
        return {"volume": vol, "muted": muted}
    raise OSError("The volume can't be changed here: neither PipeWire's wpctl nor PulseAudio's pactl is installed")


def system_power(action):
    """Sleep now; restart and shut down after a few seconds (so the frontend can say what's happening), through systemd."""
    verb = {"sleep": "suspend", "restart": "reboot", "shutdown": "poweroff"}.get(action)
    if not verb:
        raise ValueError("Unknown power action")
    if not shutil.which("systemctl"):
        raise ValueError("This computer can't be put to sleep or restarted from here")
    threading.Timer(1.0 if action == "sleep" else 3.0, lambda: run(["systemctl", verb], timeout=30)).start()


SOUND = [None]


def play_sound(path):
    stop_sound()
    player = next((p for p in ("pw-play", "paplay", "aplay") if shutil.which(p)), None)
    if player and path and os.path.isfile(path):
        SOUND[0] = popen([player] + (["-q"] if player == "aplay" else []) + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_sound():
    p, SOUND[0] = SOUND[0], None
    if p and p.poll() is None:
        p.terminate()


def read_clipboard():
    """The clipboard's text, or "" (Wayland's wl-paste, else X11's xclip or xsel)."""
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-o", "-selection", "clipboard"], ["xsel", "-b", "-o"]):
        if shutil.which(cmd[0]) and (cmd[0] != "wl-paste" or os.environ.get("WAYLAND_DISPLAY")):
            try:
                r = run(cmd, timeout=5)
                if r.returncode == 0:
                    return r.stdout
            except (OSError, subprocess.SubprocessError):
                pass
    return ""


def trash(path):
    """To the desktop's Trash (the freedesktop.org one KDE and GNOME share), so anything deleted from the album can come back."""
    import urllib.parse
    files, info = os.path.join(DATA_HOME, "Trash", "files"), os.path.join(DATA_HOME, "Trash", "info")
    os.makedirs(files, exist_ok=True)
    os.makedirs(info, exist_ok=True)
    name, ext = os.path.splitext(os.path.basename(path))
    dest, n = name + ext, 1
    while os.path.exists(os.path.join(files, dest)) or os.path.exists(os.path.join(info, dest + ".trashinfo")):
        n += 1
        dest = f"{name}.{n}{ext}"
    try:
        with open(os.path.join(info, dest + ".trashinfo"), "w", encoding="utf-8") as f:
            f.write(f"[Trash Info]\nPath={urllib.parse.quote(os.path.abspath(path))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        shutil.move(path, os.path.join(files, dest))
        return True
    except OSError:
        return False


# ---------- open at sign-in ----------
AUTOSTART = os.path.join(CONFIG_HOME, "autostart", "ultra-front-end.desktop")


def set_autostart(command):
    """Open at sign-in through the desktop's autostart folder (KDE, GNOME and the rest read it), or stop doing so (None).
    On a Steam Deck that's Desktop Mode: Game Mode opens what you add to Steam."""
    if command:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Ultra Front End\nComment=Opens Ultra Front End when you sign in\n"
                    f"Exec={desktop_quote(command)}\nIcon=ultra-front-end\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
    else:
        try:
            os.remove(AUTOSTART)
        except OSError:
            pass


def autostart_command():
    """The program the autostart entry opens, or None if there's no entry."""
    try:
        with open(AUTOSTART, encoding="utf-8") as f:
            m = re.search(r"^Exec=(.*)$", f.read(), re.M)
            return m and m.group(1).strip().strip('"').replace('\\"', '"')
    except OSError:
        return None


def desktop_quote(path):
    """A program path as a .desktop file's Exec= wants it: quoted, with its own quotes, backslashes and $ escaped."""
    return '"' + re.sub(r'(["`$\\])', r"\\\1", path) + '"'


# ---------- Steam ----------
def steam_paths():
    """Where Steam keeps its files: the native install (~/.steam/steam is a link to it on most systems, ~/.local/share/Steam
    on a Steam Deck and newer installs) and Flatpak Steam's."""
    return [os.path.join(HOME, ".steam", "steam"), os.path.join(HOME, ".steam", "root"), os.path.join(DATA_HOME, "Steam"),
            os.path.join(HOME, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"),
            os.path.join(HOME, ".var", "app", "com.valvesoftware.Steam", ".steam", "steam")]


def steam_path():
    for p in steam_paths():
        if os.path.isdir(os.path.join(p, "steamapps")) or os.path.isfile(os.path.join(p, "config", "config.vdf")):
            return os.path.realpath(p)
    return None


# ---------- emulators: Flatpak, AppImages and installed commands ----------
FLATPAK_BIN = [os.path.join(DATA_HOME, "flatpak", "exports", "bin"), "/var/lib/flatpak/exports/bin"]
# Flathub emulators by app id, as the program name the emulator tables in server.py know (Windows' exe names, so EMU_FIND,
# EMU_ARGS and CONSOLE_ARGS apply as they are)
FLATPAK_EMUS = {
    "org.libretro.RetroArch": "retroarch.exe", "org.DolphinEmu.dolphin-emu": "dolphin.exe", "net.pcsx2.PCSX2": "pcsx2.exe",
    "org.duckstation.DuckStation": "duckstation.exe", "org.ppsspp.PPSSPP": "ppsspp.exe", "org.azahar_emu.Azahar": "azahar.exe",
    "io.github.lime3ds.Lime3DS": "lime3ds.exe", "org.citra_emu.citra": "citra.exe", "net.kuribo64.melonDS": "melonds.exe",
    "org.desmume.DeSmuME": "desmume.exe", "io.mgba.mGBA": "mgba.exe", "net.rpcs3.RPCS3": "rpcs3.exe", "info.cemu.Cemu": "cemu.exe",
    "app.xemu.xemu": "xemu.exe", "org.flycast.Flycast": "flycast.exe", "dev.ares.ares": "ares.exe", "org.mamedev.MAME": "mame.exe",
    "org.scummvm.ScummVM": "scummvm.exe", "io.github.dosbox-staging": "dosbox.exe", "com.snes9x.Snes9x": "snes9x.exe",
    "io.github.simple64.simple64": "simple64.exe", "io.github.shadps4emu.shadPS4": "shadps4.exe", "org.vita3k.Vita3K": "vita3k.exe",
    "org.ryujinx.Ryujinx": "ryujinx.exe", "io.github.ryubing.Ryujinx": "ryujinx.exe", "io.github.stella_emu.Stella": "stella.exe",
    "org.openmsx.openMSX": "openmsx.exe", "rs.ruffle.Ruffle": "ruffle.exe", "com.blitterstudio.amiberry": "amiberry.exe",
    "org.tuxfamily.hatari": "hatari.exe", "io.github.mesen2.Mesen2": "mesen.exe",
}
# AppImages and programs are looked for here (EmuDeck keeps its AppImages in ~/Applications); never Downloads or the
# Desktop, which are slow to look through and where apps don't belong
APP_DIRS = [os.path.join(HOME, "Applications"), os.path.join(HOME, "AppImages"), os.path.join(HOME, "Emulators"),
            os.path.join(HOME, ".local", "bin"), os.path.join(HOME, "Emulation", "tools")]
BIN_DIRS = ["/usr/bin", "/usr/games", "/usr/local/bin", "/usr/local/games"]


def emu_name(path):
    """The name server.py's emulator tables match a program by, written as on Windows (dolphin.exe): a Flathub app's known
    name, an AppImage's file name with .exe for .AppImage, a program's name with .exe added."""
    base = os.path.basename(path.rstrip("/"))
    if base in FLATPAK_EMUS:
        return FLATPAK_EMUS[base]
    low = base.lower()
    if low.endswith(".appimage"):
        return low[:-9] + ".exe"
    return low if low.endswith(".exe") else low + ".exe"


def emulator_candidates():
    """Every program that might be an emulator: [(name as emu_name gives it, path to run)]. Flatpak apps run through the
    launcher Flatpak exports for each (a small script that runs `flatpak run <id>`), so they start like any program."""
    found = []
    for d in FLATPAK_BIN:
        for app in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if app in FLATPAK_EMUS:
                found.append((FLATPAK_EMUS[app], os.path.join(d, app)))
    for root in APP_DIRS:
        if not os.path.isdir(root):
            continue
        base = root.rstrip("/").count(os.sep)
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [] if dirpath.count(os.sep) - base >= 2 else [d for d in dirs if not d.startswith(".")]
            for f in sorted(files, key=str.lower):
                p = os.path.join(dirpath, f)
                if (f.lower().endswith(".appimage") or "." not in f) and os.access(p, os.X_OK):
                    found.append((emu_name(p), p))
    for d in BIN_DIRS:
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f not in NOT_EMULATORS:
                found.append((emu_name(f), os.path.join(d, f)))
    return found


NOT_EMULATORS = {"dolphin"}  # KDE's file manager (the Deck's Desktop Mode has it): the emulator's program is dolphin-emu


def is_flatpak(path):
    return os.path.basename(path.rstrip("/")) in FLATPAK_EMUS or "/flatpak/exports/bin/" in path


def retroarch_core_dirs(retroarch):
    """Where this RetroArch looks for cores: Flatpak RetroArch keeps them in its own folder; an AppImage or the distribution's
    in ~/.config/retroarch/cores, and Debian's and Arch's libretro packages under /usr/lib."""
    if is_flatpak(retroarch):
        return [os.path.join(HOME, ".var", "app", "org.libretro.RetroArch", "config", "retroarch", "cores")]
    import sysconfig
    multiarch = sysconfig.get_config_var("MULTIARCH") or ""
    return [os.path.join(CONFIG_HOME, "retroarch", "cores")] + [d for d in (f"/usr/lib/{multiarch}/libretro" if multiarch else "",
                                                                            "/usr/lib/libretro", "/usr/lib64/libretro", "/usr/local/lib/libretro") if d]


def retroarch_core(retroarch, core):
    """The installed core's file, or None."""
    return next((p for d in retroarch_core_dirs(retroarch) for p in [os.path.join(d, f"{core}_libretro.so")] if os.path.isfile(p)), None)


def retroarch_core_dest(retroarch, core):
    return retroarch_core(retroarch, core) or os.path.join(retroarch_core_dirs(retroarch)[0], f"{core}_libretro.so")


def core_url():
    import platform
    if platform.machine() not in ("x86_64", "AMD64"):
        raise ValueError("RetroArch cores can only be installed from here on an x86-64 computer (a Steam Deck or a PC)")
    return "https://buildbot.libretro.com/nightly/linux/x86_64/latest/{}_libretro.so.zip"


def flatpak_install(app_id, progress=None):
    """Install a Flathub app for this user (no password prompt): Flathub is added for the user first if it isn't yet.
    progress(percent) as Flatpak reports it. Returns the path of its launcher."""
    if not shutil.which("flatpak"):
        raise ValueError("Flatpak isn't installed on this computer")
    run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"], timeout=120)
    proc = subprocess.Popen(["flatpak", "install", "--user", "--noninteractive", "-y", "flathub", app_id], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=child_env())
    out, buf = [], b""
    while True:
        chunk = proc.stdout.read1(4096)
        if not chunk:
            break
        out.append(chunk)
        buf = (buf + chunk)[-300:]
        m = re.findall(rb"(\d{1,3})%", buf)
        if m and progress:
            progress(min(100, int(m[-1])))
    code = proc.wait()
    text = b"".join(out).decode("utf-8", "replace")
    launcher = next((os.path.join(d, app_id) for d in FLATPAK_BIN if os.path.exists(os.path.join(d, app_id))), None)
    if code and not launcher:
        last = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()][-1:] or ["no details"]
        raise ValueError(f"Flatpak couldn't install {app_id}: {last[0][:200]}")
    return launcher or os.path.join(FLATPAK_BIN[0], app_id)


def is_steam_deck():
    try:
        with open("/sys/devices/virtual/dmi/id/board_vendor") as v, open("/sys/devices/virtual/dmi/id/product_name") as p:
            return v.read().strip() == "Valve" and p.read().strip() in ("Jupiter", "Galileo")
    except OSError:
        return False


def game_mode():
    """Whether this runs in the Deck's Game Mode (gamescope), where Steam is the desktop."""
    return bool(os.environ.get("GAMESCOPE_WAYLAND_DISPLAY")) or os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope"


def removable_roots():
    """Mounted SD cards and USB drives (SteamOS mounts the SD card under /run/media/<user>/ or /run/media/)."""
    out = []
    user = os.environ.get("USER") or os.path.basename(HOME)
    for base in (f"/run/media/{user}", "/run/media", f"/media/{user}", "/media"):
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            p = os.path.join(base, name)
            if os.path.ismount(p) and p not in out:
                out.append(p)
    return out


# ---------- the controller (evdev) ----------
EV_KEY, EV_ABS = 1, 3
BTN = {"a": 0x130, "b": 0x131, "north": 0x133, "west": 0x134, "l1": 0x136, "r1": 0x137, "view": 0x13a, "menu": 0x13b, "home": 0x13c}
DPAD = {"up": 0x220, "down": 0x221, "left": 0x222, "right": 0x223}
ABS_X, ABS_Y, HAT_X, HAT_Y = 0, 1, 16, 17
EVENT = struct.Struct("llHHi")  # struct input_event: a timeval, then type, code and value
# Pads whose top face button is BTN_NORTH (PlayStation, Nintendo); Xbox-style drivers (xpad, Steam's virtual pad, the Deck
# itself) report their top button, Y, as BTN_Y, which is BTN_WEST's number
NORTH_TOP = re.compile(r"sony|playstation|dualsense|dualshock|wireless controller|nintendo|pro controller|joy-?con", re.I)


def _ioc_read(nr, size):
    return (2 << 30) | (size << 16) | (ord("E") << 8) | nr


def _has_bit(text, bit):
    words = text.split()
    width = struct.calcsize("l") * 2
    try:
        return bool(int("".join(w.zfill(width) for w in words), 16) >> bit & 1)
    except ValueError:
        return False


class Pads:
    """Every game controller readable in /dev/input (any pad the kernel knows, and the one Steam Input presents for a game it
    started), read without blocking. states() gives each one's buttons and directions."""
    def __init__(self):
        self.devs, self.checked = {}, 0.0

    def refresh(self):
        if time.time() - self.checked < 2:
            return
        self.checked = time.time()
        try:
            names = [n for n in os.listdir("/dev/input") if n.startswith("event")]
        except OSError:
            names = []
        for n in names:
            path = "/dev/input/" + n
            if path in self.devs:
                continue
            try:
                with open(f"/sys/class/input/{n}/device/capabilities/key") as f:
                    if not _has_bit(f.read(), BTN["a"]):
                        continue
                with open(f"/sys/class/input/{n}/device/name") as f:
                    name = f.read().strip()
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue  # not a pad, or not ours to read
            axes = {}
            for code in (ABS_X, ABS_Y):
                buf = bytearray(24)
                try:
                    import fcntl
                    fcntl.ioctl(fd, _ioc_read(0x40 + code, 24), buf)
                    _, lo, hi, _, _, _ = struct.unpack("6i", buf)
                    axes[code] = (lo, hi) if hi > lo else (-32768, 32767)
                except OSError:
                    axes[code] = (-32768, 32767)
            self.devs[path] = {"fd": fd, "name": name, "keys": set(), "abs": {}, "range": axes,
                               "top": BTN["north"] if NORTH_TOP.search(name) else BTN["west"]}

    def read(self):
        self.refresh()
        for path, dev in list(self.devs.items()):
            try:
                while True:
                    data = os.read(dev["fd"], EVENT.size * 64)
                    if not data:
                        break
                    for k in range(0, len(data) - EVENT.size + 1, EVENT.size):
                        _, _, typ, code, value = EVENT.unpack_from(data, k)
                        if typ == EV_KEY:
                            (dev["keys"].add if value else dev["keys"].discard)(code)
                        elif typ == EV_ABS:
                            dev["abs"][code] = value
            except BlockingIOError:
                pass
            except OSError:  # unplugged
                os.close(dev["fd"])
                del self.devs[path]

    def states(self):
        """[(name, buttons {a b y menu view home l1 r1: bool}, directions {up down left right: bool})] for each pad."""
        self.read()
        out = []
        for dev in self.devs.values():
            keys, ab = dev["keys"], dev["abs"]

            def axis(code):
                lo, hi = dev["range"][code]
                v = ab.get(code, (lo + hi) / 2)
                return (2 * (v - lo) / (hi - lo)) - 1 if hi > lo else 0
            lx, ly = axis(ABS_X), axis(ABS_Y)
            b = {k: BTN[k] in keys for k in ("a", "b", "l1", "r1", "view", "menu", "home")}
            b["y"] = dev["top"] in keys
            d = {"up": DPAD["up"] in keys or ab.get(HAT_Y, 0) < 0 or ly < -.55, "down": DPAD["down"] in keys or ab.get(HAT_Y, 0) > 0 or ly > .55,
                 "left": DPAD["left"] in keys or ab.get(HAT_X, 0) < 0 or lx < -.55, "right": DPAD["right"] in keys or ab.get(HAT_X, 0) > 0 or lx > .55}
            out.append((dev["name"], b, d))
        return out


# ---------- the AppImage this runs from, for updates ----------
def appimage():
    """The AppImage file this copy runs from, or "" (a source run, or a plain folder build)."""
    path = os.environ.get("APPIMAGE", "")
    import sys
    return path if path and os.path.isfile(path) and getattr(sys, "frozen", False) else ""


def update_asset():
    import platform
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine().lower())
    return f"UltraFrontEnd-linux-{arch}.AppImage"
