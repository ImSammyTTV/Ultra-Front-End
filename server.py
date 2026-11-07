"""Local helper for the game frontend.

Scans game libraries (Steam install, linked Steam/Epic accounts, folders the user adds),
serves the UI in app/, serves cover art, and launches games. Listens on 127.0.0.1 only.

Run: python server.py [--auto-exit]   then open http://127.0.0.1:8137
User data (libraries, accounts, play log) lives in data/ and is never committed.
"""
import base64
import glob
import hashlib
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Run as Game Frontend.exe, data/ sits beside the exe; app/ and metadata/ beside it win over the exe's own copies (so edits show without a rebuild)
ROOT = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
BUNDLE = getattr(sys, "_MEIPASS", ROOT)


def shipped(name):
    here = os.path.join(ROOT, name)
    return here if os.path.isdir(here) else os.path.join(BUNDLE, name)


WIN, MAC = os.name == "nt", sys.platform == "darwin"
# Games made with SDL (Hades II, many ports and emulators) minimize when they lose the focus, which the in-game menu takes:
# every program started from here is told not to (Steam too, when started from here, and so its games). A value you set
# yourself stays.
if WIN:
    os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
# Everything in one place on Windows: C:\Ultra-Front-End\App (Setup), \ROMs (a new ROMs folder) and \Emulators (installs)
UFE_HOME = os.path.join((os.environ.get("SystemDrive") or "C:") + os.sep, "Ultra-Front-End") if WIN else os.path.expanduser("~")
EMU_HOME = os.path.join(UFE_HOME, "Emulators")  # (on a Mac, ~/Emulators: apps themselves go in Applications)
OLD_EMU_HOME = os.path.join(os.path.expanduser("~"), "Emulators")  # where installs went before 1.2.5
if MAC:
    import plat_mac  # the Mac side of every Windows-only piece below
if WIN and not getattr(subprocess.Popen.__init__, "no_window", False):
    # No console window flashing over the frontend or a game: a child started with no flags of its own (subprocess.run and
    # check_output too) gets CREATE_NO_WINDOW. One that sets any (DETACHED_PROCESS, CREATE_NEW_CONSOLE...) keeps them.
    # frontend.py and hud.py are covered too: frontend.py imports this before it starts anything, and hud is imported from here.
    _popen_init = subprocess.Popen.__init__

    def _popen_no_window(self, *args, **kwargs):
        if len(args) < 14 and not kwargs.get("creationflags"):  # (args[13] is creationflags given by position: left alone)
            kwargs["creationflags"] = 0x08000000
        _popen_init(self, *args, **kwargs)

    _popen_no_window.no_window = True
    subprocess.Popen.__init__ = _popen_no_window
APP = shipped("app")


# Where the settings in use live, noted in the user's app data, so a new copy of the exe saved somewhere else (a fresh
# download in Downloads) finds them instead of starting over
DATA_NOTE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Ultra Front End", "settings-folder.txt")


def set_up_in(folder):
    """Whether a data folder holds a finished setup."""
    try:
        with open(os.path.join(folder, "config.json"), encoding="utf-8") as f:
            return bool((json.load(f).get("profile") or {}).get("setupDone"))
    except (OSError, ValueError, AttributeError):
        return False


def note_data_folder(folder):
    if WIN and getattr(sys, "frozen", False) and "--port" not in sys.argv and set_up_in(folder):  # (not a test copy's)
        try:
            os.makedirs(os.path.dirname(DATA_NOTE), exist_ok=True)
            with open(DATA_NOTE, "w", encoding="utf-8") as f:
                f.write(os.path.abspath(folder))
        except OSError:
            pass


def older_copy_data(here):
    """The settings of a copy from before 1.1.4 (which noted nowhere where they were): a set-up data folder beside an
    UltraFrontEnd exe in Downloads, the Desktop or Documents, or one folder down. The most recently used one wins, so a person
    moving from an old download to the installed app keeps everything."""
    home, found = os.path.expanduser("~"), []
    for base in (os.path.join(home, d) for d in ("Downloads", "Desktop", "Documents")):
        try:
            subs = [base] + [os.path.join(base, n) for n in os.listdir(base) if os.path.isdir(os.path.join(base, n))][:200]
        except OSError:
            continue
        for folder in subs:
            data = os.path.join(folder, "data")
            if os.path.normcase(os.path.abspath(data)) == os.path.normcase(os.path.abspath(here)) or not set_up_in(data):
                continue
            try:
                if any(n.lower().startswith(("ultrafrontend", "ultra front end", "game frontend")) and n.lower().endswith(".exe") for n in os.listdir(folder)):
                    found.append((os.path.getmtime(os.path.join(data, "config.json")), data))
            except OSError:
                pass
    return max(found)[1] if found else None


def data_folder():
    """Beside the exe, so a copy and its settings stay together, unless Windows won't let it write there (Program Files):
    then the user's own app data. A copy with no finished setup beside it uses the settings the last copy used, when they
    still exist (the same person with a new download). The Mac app runs from a read-only disk image or /Applications:
    Application Support."""
    if MAC and getattr(sys, "frozen", False):
        return os.path.expanduser("~/Library/Application Support/Ultra Front End")
    here = os.path.join(ROOT, "data")
    if WIN and getattr(sys, "frozen", False) and "--port" not in sys.argv and not set_up_in(here):
        try:
            with open(DATA_NOTE, encoding="utf-8") as f:
                before = f.read().strip()
        except OSError:
            before = ""
        if before and os.path.normcase(os.path.abspath(before)) != os.path.normcase(os.path.abspath(here)) and set_up_in(before):
            return before
        if not before:  # no note: copies before 1.1.4 never wrote one. Their settings are beside the old download
            found = older_copy_data(here)
            if found:
                return found
    try:
        import tempfile
        os.makedirs(here, exist_ok=True)
        tempfile.TemporaryFile(dir=here).close()
        return here
    except OSError:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Ultra Front End", "data")


DATA = data_folder()
note_data_folder(DATA)
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8137  # --port: a second copy for testing
# This copy's build, noted at start: an update swaps the exe while the old build can still be running in the tray
BUILD = "%d-%d" % (int(os.path.getmtime(sys.executable)), os.path.getsize(sys.executable)) if getattr(sys, "frozen", False) else "source"
QUIT = [lambda: os._exit(0)]  # how this helper leaves when a newer build takes over; Game Frontend.exe takes its tray icon down too
VERSION = "1.2.7"  # the release this is; tools/release.py publishes it as tag v<VERSION>
UPDATE_REPO = "ImSammyTTV/Ultra-Front-End"  # whose GitHub releases a copy of the exe keeps itself current from
os.makedirs(DATA, exist_ok=True)


# ---------------------------------------------------------------- storage
def load(name, default):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


STORE_LOCK = threading.Lock()


def secrets_equal(a, b):
    import hmac
    return hmac.compare_digest(str(a), str(b))


def store(name, obj):
    # Each write gets its own temp file (lookups for several games finish at once), and Windows briefly refuses the
    # swap while another thread is reading the file, so it retries instead of failing the whole request.
    path = os.path.join(DATA, name)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with STORE_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1)
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 19:
                    os.remove(tmp)
                    raise
                time.sleep(0.05)


DEFAULT_CONFIG = {"guideOpens": True, "startup": "background", "steamLocal": True, "onlineCovers": True, "showUninstalled": True, "artBackground": False, "libraries": [],
                  "eaLocal": True, "ubisoftLocal": True, "battlenetLocal": True, "wiiMotion": False}


def config():
    return {**DEFAULT_CONFIG, **load("config.json", {})}


# ---------------------------------------------------------------- helpers
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GameFrontend/0.1"


def http_json(url, data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def vdf(text):
    """Parse Valve's text KeyValues format into nested dicts."""
    root, stack, key = {}, [], None
    cur = root
    for m in re.finditer(r'"((?:\\.|[^"\\])*)"|([{}])', text):
        if m.group(2) == "{":
            new = {}
            cur[key] = new
            stack.append(cur)
            cur, key = new, None
        elif m.group(2) == "}":
            cur = stack.pop() if stack else root
        elif key is None:
            key = m.group(1)
        else:
            cur[key] = m.group(1).replace("\\\\", "\\")
            key = None
    return root


def ci(d, *path):
    """Case-insensitive nested dict lookup."""
    for p in path:
        if not isinstance(d, dict):
            return None
        d = next((v for k, v in d.items() if k.lower() == p.lower()), None)
    return d


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def open_target(target):
    """Open a link, folder or file with the system (steam:// links start games)."""
    if WIN:
        os.startfile(target)
    else:
        subprocess.Popen(["open", target])


def program(path):
    """The file to run for a program: on a Mac, the executable inside an .app bundle."""
    if MAC and path.lower().rstrip("/").endswith(".app") and os.path.isdir(path):
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


def gid(prefix, value):
    return prefix + "-" + hashlib.sha1(value.lower().encode()).hexdigest()[:12]


IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def find_image(folders, stems):
    stems = {s.lower() for s in stems}
    for folder in folders:
        try:
            for name in os.listdir(folder):
                stem, ext = os.path.splitext(name.lower())
                if ext in IMG_EXT and stem in stems:
                    return os.path.join(folder, name)
        except OSError:
            pass
    return None


# Local art files the UI may fetch, by game id. Rebuilt on every scan so /api/art only serves known files: the old
# entries stay until the scan is done (emptied at the start, a cover asked for mid-scan was "not found" and stayed a
# name card), then the ones the scan didn't see again go.
ART, ART_SEEN = {}, set()


def local_art(game_id, path):
    ART[game_id] = path
    ART_SEEN.add(game_id)
    return f"/api/art/{game_id}?v={int(os.path.getmtime(path))}"


# Animated covers from SteamGridDB can be huge (animated PNG or WebP of 15-50 MB, up to 170 full-size frames): one takes
# seconds to load and decode, so a cover that only animates while it's selected never got going. Each gets a light copy
# made once, sized for the tiles: animated WebP, 400 px wide, at most 20 frames a second and 150 frames. A cover is only
# offered as animated once its light copy exists (scan), so the originals are never played; the files are kept as they are.
LIGHT_W, LIGHT_FRAMES, LIGHT_MS = 400, 150, 50
LIGHT_VERSION = 2  # raised when the copies are made differently, so they're made again
LIGHT_LOCK = threading.Lock()
LIGHT_TODO = []
LIGHT_FAILED = set()


def light_anim_path(src):
    st = os.stat(src)
    tag = hashlib.sha1(f"{os.path.abspath(src)}|{st.st_size}|{int(st.st_mtime)}|{LIGHT_VERSION}".encode()).hexdigest()[:16]
    return os.path.join(DATA, "art", "playing", f"{tag}.webp")


def light_anim(src):
    """The light copy of an animated cover if it's ready, else None, after asking for it to be made."""
    try:
        out = light_anim_path(src)
    except OSError:
        return None
    if os.path.isfile(out):
        return out
    with LIGHT_LOCK:
        if src not in LIGHT_TODO and src not in LIGHT_FAILED:
            LIGHT_TODO.append(src)
            if len(LIGHT_TODO) == 1:
                threading.Thread(target=light_anim_worker, daemon=True).start()
    return None


def light_anim_worker():
    made, last_scan = 0, time.time()
    while True:
        with LIGHT_LOCK:
            if not LIGHT_TODO:
                if made:
                    threading.Thread(target=scan, daemon=True).start()  # the new ones show as animated
                    prune_light()
                return
            src = LIGHT_TODO[0]
        if made and time.time() - last_scan > 60:  # a long batch: what's ready so far shows now and then
            made, last_scan = 0, time.time()
            threading.Thread(target=scan, daemon=True).start()
        try:
            make_light_anim(src, light_anim_path(src))
            made += 1
        except Exception:
            LIGHT_FAILED.add(src)  # (the original is served instead)
            log_error()
        with LIGHT_LOCK:
            LIGHT_TODO.remove(src)


def prune_light():
    """Light copies no animated cover uses any more (a changed cover, older settings) are deleted."""
    keep = set()
    for o in load("overrides.json", {}).values():
        f = o.get("coverStill") and o.get("cover") and os.path.join(ART_DIR, o["cover"])
        if f and os.path.isfile(f):
            keep.add(os.path.normcase(light_anim_path(f)))
    for f in glob.glob(os.path.join(DATA, "art", "playing", "*.webp")):
        if os.path.normcase(f) not in keep:
            try:
                os.remove(f)
            except OSError:
                pass


def make_light_anim(src, out):
    from PIL import Image, ImageSequence
    with Image.open(src) as im:
        size = (LIGHT_W, max(1, round(im.height * LIGHT_W / im.width)))
        frames, times = [], []
        try:
            for frame in ImageSequence.Iterator(im):
                frame.load()  # (a WebP frame's duration is only known once it's loaded)
                ms = float(frame.info.get("duration") or im.info.get("duration") or 40)
                if frames and times[-1] < LIGHT_MS:  # too soon after the last one kept: this frame's time joins it
                    times[-1] += ms
                    continue
                frames.append(frame.convert("RGBA").resize(size, Image.LANCZOS))
                times.append(ms)
        except (OSError, EOFError):  # a file cut short (a download that didn't finish): the frames it has
            if len(frames) < 2:
                raise
        if len(frames) > LIGHT_FRAMES:  # a long loop: frames spread evenly over it, the timing kept
            target, kept, kept_ms = sum(times) / LIGHT_FRAMES, [], []
            for frame, ms in zip(frames, times):
                if kept_ms and kept_ms[-1] < target:
                    kept_ms[-1] += ms
                    continue
                kept.append(frame)
                kept_ms.append(ms)
            frames, times = kept, kept_ms
        times = [max(20, round(t)) for t in times]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    part = out + ".part"
    frames[0].save(part, "WEBP", save_all=True, append_images=frames[1:], duration=times, loop=0, quality=75, method=4)
    os.replace(part, out)


# ---------------------------------------------------------------- Steam
def steam_path():
    if MAC:
        p = os.path.expanduser("~/Library/Application Support/Steam")
        return p if os.path.isdir(p) else None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            p = os.path.normpath(winreg.QueryValueEx(k, "SteamPath")[0])
            return p if os.path.isdir(p) else None
    except OSError:
        return None


STEAM_SKIP = re.compile(r"redistributable|proton|steam linux runtime|steamvr|dedicated server|\bsdk\b|soundtrack|steamworks|wallpaper engine", re.I)
STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/{}/library_600x900_2x.jpg"


def steam_cover(appid):
    sp = steam_path()
    if sp:
        cache = os.path.join(sp, "appcache", "librarycache")
        for pat in (f"{appid}/*/library_capsule.jpg", f"{appid}/library_600x900.jpg", f"{appid}/*/library_600x900.jpg", f"{appid}_library_600x900.jpg"):
            hits = glob.glob(os.path.join(cache, pat))
            if hits:
                return local_art(f"steam-{appid}", hits[0])
    return STEAM_CDN.format(appid)


def steam_game(appid, name, installed, minutes=0, last=0):
    return {"id": f"steam-{appid}", "appid": str(appid), "title": name, "group": "Steam", "source": "Steam", "installed": installed,
            "minutes": int(minutes or 0), "lastPlayed": int(last or 0), "cover": steam_cover(appid),
            "launch": {"type": "uri", "uri": f"steam://rungameid/{appid}" if installed else f"steam://install/{appid}"}}


STEAM_ASSETS = "https://shared.steamstatic.com/store_item_assets/"


def steam_store_art(appids):
    """Tall library art URLs from Steam's store service (newer games keep it under hashed paths). Cached."""
    cache = load("steam-art.json", {})
    missing = [a for a in appids if a not in cache]
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        q = json.dumps({"ids": [{"appid": int(a)} for a in chunk], "context": {"language": "english", "country_code": "US"},
                        "data_request": {"include_assets": True}})
        try:
            items = http_json("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/?" + urllib.parse.urlencode({"input_json": q}))["response"].get("store_items", [])
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            break
        for it in items:
            a = it.get("assets") or {}
            fmt, cap = a.get("asset_url_format"), a.get("library_capsule_2x") or a.get("library_capsule")
            cache[str(it.get("appid") or it.get("id"))] = STEAM_ASSETS + fmt.replace("${FILENAME}", cap) if fmt and cap else ""
        for a in chunk:
            cache.setdefault(a, "")
    if missing:
        store("steam-art.json", cache)
    return cache


def steam_suggested_id():
    sp = steam_path()
    if not sp:
        return None
    try:
        users = ci(vdf(read(os.path.join(sp, "config", "loginusers.vdf"))), "users") or {}
    except OSError:
        return None
    for sid, u in users.items():
        if isinstance(u, dict) and ci(u, "MostRecent") == "1":
            return sid
    return next(iter(users), None)


def scan_steam_local():
    sp = steam_path()
    if not sp:
        return []
    libs = [sp]
    try:
        for v in (ci(vdf(read(os.path.join(sp, "steamapps", "libraryfolders.vdf"))), "libraryfolders") or {}).values():
            if isinstance(v, dict) and v.get("path"):
                libs.append(v["path"])
    except OSError:
        pass
    stats = {}
    for cfg in glob.glob(os.path.join(sp, "userdata", "*", "config", "localconfig.vdf")):
        apps = ci(vdf(read(cfg)), "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") or {}
        for appid, a in apps.items():
            if isinstance(a, dict):
                s = stats.setdefault(appid, {"last": 0, "min": 0})
                s["last"] = max(s["last"], int(ci(a, "LastPlayed") or 0))
                s["min"] = max(s["min"], int(ci(a, "Playtime") or 0))
    games, seen = [], set()
    for lib in dict.fromkeys(os.path.normcase(os.path.normpath(p)) for p in libs):
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            st = ci(vdf(read(acf)), "AppState") or {}
            appid, name = ci(st, "appid"), ci(st, "name")
            if not appid or not name or appid in seen or STEAM_SKIP.search(name):
                continue
            # Steam also keeps a record for a game it hasn't finished installing (queued, a demo or playtest it never
            # downloaded): only the ones flagged fully installed, with their folder there, can start
            try:
                flags = int(ci(st, "StateFlags") or 0)
            except ValueError:
                flags = 0
            folder = ci(st, "installdir") and os.path.join(lib, "steamapps", "common", ci(st, "installdir"))
            if not flags & 4 or not (folder and os.path.isdir(folder)):
                continue
            seen.add(appid)
            s = stats.get(appid, {})
            games.append(steam_game(appid, name, True, s.get("min"), s.get("last")))
    return games


def resolve_steam_id(text, key):
    text = text.strip()
    m = re.search(r"(7656\d{13})", text)
    if m:
        return m.group(1)
    m = re.search(r"steamcommunity\.com/id/([^/?#]+)", text)
    vanity = m.group(1) if m else text
    r = http_json("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?" + urllib.parse.urlencode({"key": key, "vanityurl": vanity}))["response"]
    if r.get("success") != 1:
        raise ValueError("Couldn't find that Steam profile")
    return r["steamid"]


def scan_steam_account(acc):
    q = urllib.parse.urlencode({"key": acc["key"], "steamid": acc["steamid"], "include_appinfo": 1, "include_played_free_games": 1, "format": "json"})
    games = http_json("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?" + q)["response"].get("games", [])
    return [steam_game(str(g["appid"]), g.get("name", f"App {g['appid']}"), False, g.get("playtime_forever"), g.get("rtime_last_played"))
            for g in games if not STEAM_SKIP.search(g.get("name", ""))]


# ---------------------------------------------------------------- Epic
# Epic has no public library API. Like Legendary/Heroic, this uses the Epic Games launcher's own OAuth client.
EPIC_CLIENT = ("34a02cf8f4414e29b15921876da36f9a", "daafbccc737745039dffe53d94fc76cf")
EPIC_LOGIN_URL = "https://www.epicgames.com/id/login?redirectUrl=" + urllib.parse.quote(
    f"https://www.epicgames.com/id/api/redirect?clientId={EPIC_CLIENT[0]}&responseType=code", safe="")
EPIC_OAUTH = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
EPIC_LIBRARY = "https://library-service.live.use1a.on.epicgames.com/library/api/public/items"
EPIC_CATALOG = "https://catalog-public-service-prod06.ol.epicgames.com/catalog/api/shared/namespace/{}/bulk/items"
EPIC_UA = "UELauncher/11.0.1-14907503+++Portal+Release-Live Windows/10.0.19041.1.256.64bit"


def epic_token(form):
    auth = base64.b64encode(":".join(EPIC_CLIENT).encode()).decode()
    return http_json(EPIC_OAUTH, data=urllib.parse.urlencode({**form, "token_type": "eg1"}).encode(),
                     headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded", "User-Agent": EPIC_UA})


def epic_login(code_text):
    m = re.search(r"[0-9a-f]{32}", code_text)
    if not m:
        raise ValueError("That doesn't look like an Epic authorization code")
    tok = epic_token({"grant_type": "authorization_code", "code": m.group(0)})
    return {"refresh_token": tok["refresh_token"], "account_id": tok.get("account_id"), "name": tok.get("displayName")}


EPIC_DIR = os.path.expanduser("~/Library/Application Support/Epic/EpicGamesLauncher") if MAC else r"C:\ProgramData\Epic\EpicGamesLauncher"


def epic_installed():
    apps = set()
    for item in glob.glob(os.path.join(EPIC_DIR, "Data", "Manifests", "*.item")):
        try:
            apps.add(json.loads(read(item)).get("AppName"))
        except ValueError:
            pass
    return apps


def scan_epic(accounts):
    acc = accounts["epic"]
    tok = epic_token({"grant_type": "refresh_token", "refresh_token": acc["refresh_token"]})
    acc["refresh_token"] = tok["refresh_token"]  # refresh tokens rotate
    store("accounts.json", accounts)
    auth = {"Authorization": f"Bearer {tok['access_token']}", "User-Agent": EPIC_UA}
    records, cursor = [], None
    while True:
        q = {"includeMetadata": "true", **({"cursor": cursor} if cursor else {})}
        page = http_json(EPIC_LIBRARY + "?" + urllib.parse.urlencode(q), headers=auth)
        records += page.get("records", [])
        cursor = (page.get("responseMetadata") or {}).get("nextCursor")
        if not cursor:
            break
    catalog = load("epic-catalog.json", {})
    launcher = os.path.isdir(EPIC_DIR)
    installed = epic_installed()
    games = []
    for r in records:
        ns, cid, app = r.get("namespace"), r.get("catalogItemId"), r.get("appName")
        if not ns or not cid or ns == "ue":
            continue
        key = f"{ns}:{cid}"
        if key not in catalog or "description" not in catalog[key]:  # older cache entries lack the details-screen fields
            try:
                q = urllib.parse.urlencode({"id": cid, "includeDLCDetails": "true", "includeMainGameDetails": "true", "country": "US", "locale": "en"})
                item = http_json(EPIC_CATALOG.format(ns) + "?" + q, headers=auth).get(cid, {})
                imgs = {i.get("type"): i.get("url") for i in item.get("keyImages", [])}
                catalog[key] = {"title": item.get("title"), "dlc": bool(item.get("mainGameItem")),
                                "game": any(c.get("path") in ("games", "applications") for c in item.get("categories", [])),
                                "cover": imgs.get("DieselGameBoxTall") or imgs.get("OfferImageTall") or imgs.get("DieselGameBox"),
                                "description": item.get("description") or "", "logo": imgs.get("DieselGameBoxLogo") or "",
                                "wide": imgs.get("DieselGameBox") or imgs.get("OfferImageWide") or ""}
            except (urllib.error.URLError, ValueError):
                continue
        c = catalog[key]
        if c.get("dlc") or not c.get("game") or not c.get("title"):
            continue
        uri = f"com.epicgames.launcher://apps/{ns}%3A{cid}%3A{app}?action={'launch' if app in installed else 'install'}&silent=true"
        games.append({"id": f"epic-{app}", "title": c["title"], "group": "Epic", "source": "Epic", "installed": app in installed,
                      "minutes": 0, "lastPlayed": 0, "cover": c.get("cover") or "",
                      "epic": {"description": c.get("description", ""), "logo": c.get("logo", ""), "hero": c.get("wide", "")},
                      "launch": {"type": "uri", "uri": uri} if launcher else
                      {"type": "none", "message": "Install the Epic Games launcher to play Epic games"}})
    store("epic-catalog.json", catalog)
    return games


# ---------------------------------------------------------------- user libraries
SYSTEMS = [  # (folder-name pattern, name, libretro thumbnail set, extensions, RetroArch cores in order of preference)
    # first match wins: add-ons and later models come before the console whose name they contain
    (r"wii ?u", "Wii U", "Nintendo - Wii U", ".wud .wux .wua .rpx", []),
    (r"\bwii\b", "Wii", "Nintendo - Wii", ".iso .wbfs .rvz .gcz .ciso", ["dolphin"]),
    (r"gamecube|\bgc\b|\bngc\b", "GameCube", "Nintendo - GameCube", ".iso .rvz .gcm .gcz .ciso", ["dolphin"]),
    (r"switch ?2", "Switch 2", "Nintendo - Switch", ".nsp .xci .nup", []),  # .nup: Eglantine's own NUP container
    (r"switch", "Switch", "Nintendo - Switch", ".nsp .xci", []),
    (r"3ds", "3DS", "Nintendo - Nintendo 3DS", ".3ds .cci .cia .cxi", ["citra"]),
    (r"\bn?ds\b|nintendo ds", "DS", "Nintendo - Nintendo DS", ".nds", ["melonds", "desmume"]),
    (r"64 ?dd", "64DD", "Nintendo - Nintendo 64DD", ".ndd .d64 .n64dd .zip .7z", []),
    (r"n64|nintendo 64", "N64", "Nintendo - Nintendo 64", ".n64 .z64 .v64 .zip .7z", ["mupen64plus_next", "parallel_n64"]),
    (r"snes|super nintendo|super famicom|\bsfc\b", "SNES", "Nintendo - Super Nintendo Entertainment System", ".sfc .smc .zip .7z", ["snes9x", "bsnes"]),
    (r"\bfds\b|famicom disk|disk system", "FDS", "Nintendo - Family Computer Disk System", ".fds .nes .unf .unif .zip .7z", []),
    (r"\bnes\b|famicom|nintendo entertainment", "NES", "Nintendo - Nintendo Entertainment System", ".nes .fds .unf .unif .zip .7z", ["mesen", "nestopia", "fceumm"]),
    (r"gba|game ?boy advance", "GBA", "Nintendo - Game Boy Advance", ".gba .zip .7z", ["mgba", "vba_next"]),
    (r"gbc|game ?boy colou?r", "GBC", "Nintendo - Game Boy Color", ".gbc .zip .7z", ["gambatte", "sameboy"]),
    (r"\bgb\b|game ?boy", "Game Boy", "Nintendo - Game Boy", ".gb .zip .7z", ["gambatte", "sameboy"]),
    (r"virtual ?boy|\bvboy\b|\bvb\b", "Virtual Boy", "Nintendo - Virtual Boy", ".vb .vboy .zip", []),
    (r"pok[eé]mon ?mini|pokemini", "Pokemon Mini", "Nintendo - Pokemon Mini", ".min .zip", ["pokemini"]),
    (r"game ?(&|and|n) ?watch|\bg ?& ?w\b|\bgnw\b|\bgw\b", "Game & Watch", "Handheld Electronic Game", ".zip .7z", []),
    # PlayStation 3/4/5 games are often folders; "eboot.bin" matches that file by name and the folder names the game
    # Kyty plays decrypted dumps only: a folder with eboot.bin, or a .zar archive (never the encrypted .pkg installers)
    (r"ps5|playstation 5", "PS5", None, ".zar eboot.bin", []),
    (r"ps4|playstation 4", "PS4", None, ".pkg eboot.bin", []),
    (r"vita|psv\b", "PS Vita", None, ".vpk", []),
    (r"ps3|playstation 3", "PS3", "Sony - PlayStation 3", ".iso .pkg eboot.bin", []),
    (r"ps2|playstation 2", "PS2", "Sony - PlayStation 2", ".iso .chd .cso .gz", ["pcsx2"]),
    (r"psp|playstation portable", "PSP", "Sony - PlayStation Portable", ".iso .cso .pbp .chd", ["ppsspp"]),
    (r"ps1|psx|playstation", "PS1", "Sony - PlayStation", ".cue .chd .pbp .m3u", ["swanstation", "mednafen_psx_hw", "pcsx_rearmed"]),
    (r"naomi ?2", "NAOMI 2", "Sega - Naomi 2", ".zip .7z .bin .dat .lst .elf .chd", []),
    (r"naomi", "NAOMI", "Sega - Naomi", ".zip .7z .bin .dat .lst .elf .chd", []),
    (r"atomis ?wave|\bawave\b", "Atomiswave", "Atomiswave", ".zip .7z .bin .dat .lst", []),
    (r"model ?3", "Model 3", None, ".zip .7z", []),
    (r"dreamcast|\bdc\b", "Dreamcast", "Sega - Dreamcast", ".chd .gdi .cdi .cue", ["flycast"]),
    (r"saturn", "Saturn", "Sega - Saturn", ".cue .chd .ccd .mds .iso", ["mednafen_saturn", "yabasanshiro"]),
    (r"sega ?-?cd|mega ?-?cd", "Sega CD", "Sega - Mega-CD - Sega CD", ".chd .cue .iso .m3u", []),
    (r"32x", "32X", "Sega - 32X", ".32x .bin .zip .7z", []),
    (r"genesis|mega ?drive|\bmd\b", "Genesis", "Sega - Mega Drive - Genesis", ".md .gen .smd .bin .zip .7z", ["genesis_plus_gx", "picodrive"]),
    (r"master ?system|\bsms\b|mark ?(iii|3)", "Master System", "Sega - Master System - Mark III", ".sms .zip .7z", []),
    (r"game ?gear|\bgg\b", "Game Gear", "Sega - Game Gear", ".gg .zip .7z", []),
    (r"sg[- ]?1000", "SG-1000", "Sega - SG-1000", ".sg .zip .7z", []),
    (r"xbox ?360|x360", "Xbox 360", None, ".iso .xex .zar", []),
    (r"xbox", "Xbox", "Microsoft - Xbox", ".iso .xiso", []),
    (r"pc-?fx", "PC-FX", "NEC - PC-FX", ".cue .ccd .toc .m3u", []),
    (r"(pc ?-?engine|supergrafx|\bsgx\b|turbo ?grafx(-?16)?|\bpce\b|\btg-?16\b) ?-?(super )?cd|turbo ?duo|\btg-?cd\b|\bpce-?cd\b|cd-?rom2", "PC Engine CD", "NEC - PC Engine CD - TurboGrafx-CD", ".cue", []),
    (r"^(?!.*\b(cd|duo)\b).*(pc ?-?engine|supergrafx|\bsgx\b|turbo ?grafx|\bpce\b|\btg-?16\b)", "PC Engine", "NEC - PC Engine - TurboGrafx 16", ".pce .zip .7z", []),
    (r"neo ?-?geo ?pocket|\bngpc?\b", "Neo Geo Pocket", "SNK - Neo Geo Pocket Color", ".ngc .ngp .npc .ngpc .zip", []),
    (r"neo ?-?geo ?cd|\bngcd\b", "Neo Geo CD", "SNK - Neo Geo CD", ".chd .cue .toc .iso", []),
    (r"neo ?-?geo|\bmvs\b|\baes\b", "Neo Geo", "SNK - Neo Geo", ".zip .7z", []),
    (r"jaguar|\bjag\b", "Atari Jaguar", "Atari - Jaguar", ".j64 .jag .rom .abs .cof .zip", []),
    (r"lynx", "Atari Lynx", "Atari - Lynx", ".lnx .zip", []),
    (r"atari[ -]*7800|\b7800\b|prosystem", "Atari 7800", "Atari - 7800", ".a78", []),
    (r"atari[ -]*5200|\b5200\b|\ba52\b", "Atari 5200", "Atari - 5200", ".a52 .car .bin .rom", []),
    (r"atari[ -]*2600|\b2600\b|\bvcs\b", "Atari 2600", "Atari - 2600", ".a26 .bin .rom .zip", []),
    (r"atari[ -]*ste?\b|\bst\b(?=.*atari)", "Atari ST", "Atari - ST", ".st .msa .stx .dim .ipf .zip", []),
    (r"atari[ -]*(8-?bit|800|400|xl|xe)(xl|xe)?\b", "Atari 8-bit", "Atari - 8-bit Family", ".atr .atx .xex .xfd .car .cas .com .bin .rom .cdm .zip .7z", []),
    (r"wonder ?swan|\bwsc?\b|swan ?crystal", "WonderSwan", "Bandai - WonderSwan Color", ".ws .wsc .pc2 .zip .7z", []),
    (r"arcade|\bmame\b|\bfbneo\b|\bfba\b|final ?burn", "Arcade", "MAME", ".zip .7z", []),
    (r"\b3do\b", "3DO", "The 3DO Company - 3DO", ".chd .cue .iso", ["opera"]),
    (r"\bcd-?i\b|cdimono|philips ?cd", "CD-i", "Philips - CD-i", ".chd .cue .toc .iso", []),
    (r"coleco", "ColecoVision", "Coleco - ColecoVision", ".col .rom .bin .zip", []),
    (r"intellivision|\bintv\b", "Intellivision", "Mattel - Intellivision", ".int .bin .rom .zip", []),
    (r"vectrex", "Vectrex", "GCE - Vectrex", ".vec .bin .gam .vc .zip", []),
    (r"odyssey ?(2|²)|o2em|videopac|\bg7000\b", "Odyssey 2", "Magnavox - Odyssey2", ".bin .zip", []),
    (r"n-?gage", "N-Gage", None, ".zip", []),
    # DOS and ScummVM games are folders: one per game (see FOLDER_GAMES)
    (r"\bdos\b|ms-?dos|dosbox", "DOS", "DOS", ".exe .com .bat", []),
    (r"scumm", "ScummVM", "ScummVM", ".scummvm .svm", []),
    (r"c64|commodore[ -]*64", "C64", "Commodore - 64", ".d64 .g64 .d71 .d81 .t64 .tap .prg .p00 .crt .x64 .zip .7z", []),
    (r"(commodore[ -]*)?vic-? ?20|\bvic\b|vc-? ?20", "VIC-20", "Commodore - VIC-20", ".prg .crt .d64 .t64 .tap .a0 .b0 .20 .40 .60 .zip .7z", []),
    (r"\bamiga\b(?!.*cd ?32)|\ba(500|600|1200)\b", "Amiga", "Commodore - Amiga", ".adf .adz .dms .ipf .lha .hdf .uae .rp9 .zip .7z", []),
    (r"zx ?spectrum|\bspectrum\b|\bzx\b(?! ?81)", "ZX Spectrum", "Sinclair - ZX Spectrum", ".tap .tzx .pzx .z80 .sna .snx .sp .zx .zsf .rzx .dsk .trd .scl .mdr", []),
    (r"amstrad|\bcpc\b", "Amstrad CPC", "Amstrad - CPC", ".dsk .sna .cdt .voc .cpr .kcr .m3u .zip .7z", ["cap32", "crocods"]),
    (r"\bmsx", "MSX", "Microsoft - MSX2", ".rom .mx1 .mx2 .ri .dsk .di1 .di2 .dmk .xsa .cas .zip", []),
    (r"apple ?(ii|2)(?! ?gs)(e|\+|c)?\b|apple ?\]\[", "Apple II", None, ".dsk .do .po .nib .woz .zip .7z", []),
    (r"\bflash\b|\bswf\b|ruffle", "Flash", None, ".swf", []),
]
# Launch arguments for common emulators ({rom} = the game file). Editable per library in data/config.json.
# Placeholders: {bios} the console's BIOS folder, {romdir} its ROMs folder, {romfolder} the folder the game file is in
# (a subfolder of {romdir}, or {romdir} itself), {gamedir} the game's folder, {basename} the
# game's name without its extension, {bioscfg} a RetroArch config naming the BIOS folder, {gameid} a ScummVM game id
# (or --auto-detect), and {auto}: arguments worked out at launch from the files found (AUTO_ARGS), or none.
EMU_ARGS = [
    (r"duckstation", ["-batch", "-fullscreen", "{rom}"]),
    (r"pcsx2", ["-batch", "-fullscreen", "{rom}"]),
    (r"dolphin", ["-b", "-C", "Dolphin.Display.Fullscreen=True", "-e", "{rom}"]),
    (r"azahar|lime3ds|citra", ["-f", "{rom}"]),
    (r"melonds", ["-f", "{rom}"]),
    (r"mesen", ["--fullscreen", "{rom}"]),
    (r"vita3k", ["-F", "{rom}"]),
    (r"xenia", ["--fullscreen=true", "{rom}"]),
    (r"rpcs3", ["--no-gui", "--fullscreen", "{rom}"]),
    (r"ppsspp", ["--fullscreen", "{rom}"]),
    (r"cemu", ["-f", "-g", "{rom}"]),
    (r"eden|eglantine|yuzu|suyu|sudachi|citron", ["-f", "-g", "{rom}"]),
    (r"shadps4", ["-g", "{rom}", "-f", "true"]),
    # {screenw}/{screenh} = this PC's screen. Only options the official KytyPS5 knows: it won't start with any other
    # (the Gran Turismo 7 fork's --bindless and --shader-optimization-type can be added per library in data/config.json)
    (r"kyty", ["--game", "{rom}", "--fullscreen", "--hide-cursor", "--screen-width", "{screenw}", "--screen-height", "{screenh}", "--tessellation"]),
    (r"mgba", ["-f", "{rom}"]),
    (r"mednafen", ["-video.fs", "1", "{rom}"]),
    (r"xemu", ["-full-screen", "-dvd_path", "{rom}"]),
    (r"ymir", ["-f", "{rom}"]),  # never -P: that starts it paused
    (r"flycast", ["-config", "window:fullscreen=yes", "-config", "config:Dreamcast.BiosPath={bios}", "{rom}"]),  # -config before the game: the rest is ignored
    (r"stella", ["-fullscreen", "1", "{rom}"]),
    (r"bigpemu", ["{rom}"]),
    (r"eka2l1", ["--fullscreen", "--device", "RH-29", "--mount", "{rom}", "--runng"]),
    (r"x64sc", ["+confirmonexit", "-VICIIfull", "-autostart", "{rom}"]),
    (r"xvic", ["-VICfull", "{rom}"]),
    (r"amiberry", ["-o", "rom_path={bios}", "-s", "gfx_fullscreen_amiga=true", "-G", "{auto}", "{rom}"]),
    (r"zesarux", ["--fullscreen", "--nowelcomemessage", "--quickexit", "{rom}"]),
    (r"hatari", ["--fullscreen", "--confirm-quit", "false", "{auto}", "{rom}"]),
    (r"^dosbox\.exe$", ["--working-dir", "{gamedir}", "--fullscreen", "{auto}", "{rom}"]),
    (r"scummvm", ["-f", "--extrapath={bios}", "-p", "{gamedir}", "{gameid}"]),
    (r"applewin", ["-f", "-no-printscreen-dlg", "-d1", "{rom}"]),
    (r"supermodel", ["-fullscreen", "{rom}"]),
    (r"ruffle", ["--fullscreen", "{rom}"]),
]
# One program for several consoles, each started its own way: (program pattern, arguments) by console, used when that
# console's program matches (EMU_ARGS otherwise)
ARES = ["--fullscreen", "--no-file-prompt"]
CONSOLE_ARGS = {
    "Genesis": (r"^ares", ["--system", "Mega Drive", *ARES, "{rom}"]),
    "Sega CD": (r"^ares", ["--system", "Mega CD", *ARES, "{auto}", "{rom}"]),
    "32X": (r"^ares", ["--system", "Mega 32X", *ARES, "{rom}"]),
    "Master System": (r"^ares", ["--system", "Master System", *ARES, "{auto}", "{rom}"]),
    "Game Gear": (r"^ares", ["--system", "Game Gear", *ARES, "{auto}", "{rom}"]),
    "64DD": (r"^ares", ["--system", "Nintendo 64DD", *ARES, "{auto}", "{rom}"]),
    "Atari Lynx": (r"mednafen", ["-video.fs", "1", "-filesys.path_firmware", "{bios}", "{rom}"]),
    "PC-FX": (r"mednafen", ["-video.fs", "1", "-force_module", "pcfx", "-pcfx.bios", "{bios}\\pcfx.rom", "{rom}"]),
    # MAME: the machine, then the game; -rompath is where it finds the system's own ROMs (it starts in its own folder)
    "Atari 7800": (r"^mame", ["{auto}", "-cart", "{rom}", "-rompath", "{bios}", "-skip_gameinfo"]),  # {auto}: a7800, or a7800p for PAL
    "Arcade": (r"^mame", ["{basename}", "-rompath", "{romfolder};{romdir};{bios}", "-skip_gameinfo"]),
    "Neo Geo": (r"^mame", ["{basename}", "-rompath", "{romfolder};{romdir};{bios}", "-skip_gameinfo"]),
    "Neo Geo CD": (r"^mame", ["neocdz", "-rompath", "{bios}", "-cdrm", "{rom}", "-skip_gameinfo"]),
    "CD-i": (r"^mame", ["cdimono1", "-rompath", "{bios}", "-cdrom", "{rom}", "-skip_gameinfo"]),
    "Intellivision": (r"^mame", ["intv", "-rompath", "{bios}", "-cart", "{rom}", "-skip_gameinfo"]),
    "Vectrex": (r"^mame", ["vectrex", "-rompath", "{bios}", "-cart", "{rom}", "-skip_gameinfo"]),
    "Odyssey 2": (r"^mame", ["{auto}", "-rompath", "{bios}", "-cart", "{rom}", "-skip_gameinfo"]),  # odyssey2, or videopac for PAL
    "Game & Watch": (r"^mame", ["{basename}", "-rompath", "{romfolder};{romdir}", "-skip_gameinfo"]),
    "ColecoVision": (r"openmsx", ["-machine", "ColecoVision_SGM", "-command", "set fullscreen on", "-cart", "{rom}"]),
    "MSX": (r"openmsx", ["-command", "set fullscreen on", "{rom}"]),
    "Atari 5200": (r"atari800", ["-5200", "-fullscreen", "{auto}", "-cart", "{rom}"]),
    "Atari 8-bit": (r"atari800", ["-fullscreen", "{auto}", "{rom}"]),
}
NOT_ROM = set(IMG_EXT) | {".txt", ".nfo", ".xml", ".dat", ".sav", ".srm", ".state", ".cfg", ".ini", ".db", ".json", ".pdf"}
EXE_SKIP = re.compile(r"unins|setup|install|crash|redist|vc_?redist|dxsetup|directx|helper|updat|report|benchmark|server|config|cefprocess|uploader|dotnet|ue4prereq|vcrun", re.I)


# The systems the frontend knows, by maker, in the order they're listed (Settings > Systems and the setup guide).
SYSTEM_GROUPS = [
    ("PlayStation", ["PS5", "PS4", "PS3", "PS2", "PS1", "PSP", "PS Vita"]),
    ("Nintendo", ["Switch 2", "Switch", "Wii U", "Wii", "GameCube", "N64", "64DD", "SNES", "NES", "FDS", "3DS", "DS", "GBA", "GBC", "Game Boy",
                  "Virtual Boy", "Pokemon Mini", "Game & Watch"]),
    ("Xbox", ["Xbox 360", "Xbox"]),
    ("Sega", ["Dreamcast", "Saturn", "Sega CD", "32X", "Genesis", "Master System", "Game Gear", "SG-1000", "NAOMI", "NAOMI 2", "Atomiswave", "Model 3"]),
    ("NEC", ["PC Engine", "PC Engine CD", "PC-FX"]),
    ("SNK", ["Neo Geo", "Neo Geo CD", "Neo Geo Pocket"]),
    ("Atari", ["Atari Jaguar", "Atari Lynx", "Atari 7800", "Atari 5200", "Atari 2600", "Atari ST", "Atari 8-bit"]),
    ("Bandai", ["WonderSwan"]),
    ("Arcade", ["Arcade"]),
    ("Other consoles", ["3DO", "CD-i", "ColecoVision", "Intellivision", "Vectrex", "Odyssey 2", "N-Gage"]),
    ("Computers", ["DOS", "ScummVM", "C64", "VIC-20", "Amiga", "ZX Spectrum", "Amstrad CPC", "MSX", "Apple II", "Flash"]),
]
# One ROMs folder holds a subfolder per system the user plays; each system's emulator is chosen once (Settings > Systems).
ROM_FOLDERS = [s for _, group in SYSTEM_GROUPS for s in group]
SYSTEM_GROUP = {s: g for g, group in SYSTEM_GROUPS for s in group}
FOLDER_GAMES = {"DOS", "ScummVM"}  # a game is a folder (DOS: its program inside is started; ScummVM: the folder is)
ZIP_GAMES = {"Arcade", "Neo Geo", "Game & Watch", "NAOMI", "NAOMI 2", "Atomiswave", "Model 3", "N-Gage"}  # the archive is the game: never unpacked
# Emulator programs to look for per platform (first found wins); RetroArch covers the retro systems as a fallback.
MESEN, MEDNAFEN, ARES_EXE, MAME = ["mesen*.exe"], ["mednafen*.exe"], ["ares.exe"], ["mame.exe"]
EMU_FIND = {
    "Switch 2": ["eglantine*.exe"],
    "Switch": ["eden*.exe", "citron*.exe", "sudachi*.exe", "suyu*.exe", "yuzu*.exe", "ryujinx*.exe"],
    "PS1": ["duckstation*.exe"], "PS2": ["pcsx2*.exe"], "PS3": ["rpcs3*.exe"], "PS4": ["shadps4*.exe"],
    "PS5": ["kyty_emulator.exe"],  # not kyty*.exe: the launcher and updater sit beside it
    "PSP": ["ppsspp*.exe"], "PS Vita": ["vita3k*.exe"], "GameCube": ["dolphin*.exe"], "Wii": ["dolphin*.exe"], "Wii U": ["cemu*.exe"],
    "3DS": ["azahar*.exe", "lime3ds*.exe", "citra*.exe"], "DS": ["melonds*.exe", "desmume*.exe"], "GBA": ["mgba*.exe"], "GBC": ["mgba*.exe"],
    "Game Boy": ["mgba*.exe"], "SNES": ["snes9x*.exe", "bsnes*.exe", "mesen*.exe"], "N64": ["project64*.exe", "simple64*.exe"],
    "Xbox": ["xemu*.exe"], "Xbox 360": ["xenia*.exe"],
    "NES": MESEN, "FDS": MESEN, "PC Engine": MESEN, "PC Engine CD": MESEN, "WonderSwan": MESEN, "SG-1000": MESEN,
    "Virtual Boy": MEDNAFEN, "Neo Geo Pocket": MEDNAFEN, "Atari Lynx": MEDNAFEN, "PC-FX": MEDNAFEN,
    "Genesis": ARES_EXE, "Sega CD": ARES_EXE, "32X": ARES_EXE, "Master System": ARES_EXE, "Game Gear": ARES_EXE, "64DD": ARES_EXE,
    "Saturn": ["ymir-sdl3.exe"], "Dreamcast": ["flycast*.exe", "redream*.exe"], "NAOMI": ["flycast*.exe"], "NAOMI 2": ["flycast*.exe"],
    "Atomiswave": ["flycast*.exe"], "Model 3": ["supermodel.exe"], "Atari 2600": ["stella*.exe"], "Atari Jaguar": ["bigpemu*.exe"],
    "Atari 7800": MAME, "Arcade": MAME, "Neo Geo": MAME, "Neo Geo CD": MAME, "CD-i": MAME, "Intellivision": MAME, "Vectrex": MAME,
    "Odyssey 2": MAME, "Game & Watch": MAME, "ColecoVision": ["openmsx.exe"], "MSX": ["openmsx.exe"], "Atari 5200": ["atari800.exe"],
    "Atari 8-bit": ["atari800.exe"], "Atari ST": ["hatari.exe"], "N-Gage": ["eka2l1_qt.exe"], "C64": ["x64sc.exe"], "VIC-20": ["xvic.exe"],
    "Amiga": ["amiberry*.exe"], "ZX Spectrum": ["zesarux.exe"], "DOS": ["dosbox.exe"], "ScummVM": ["scummvm.exe"], "Apple II": ["applewin.exe"],
    "Flash": ["ruffle.exe"],
}
# What Settings > Systems installs for each console: (emulator, winget package) for those published there and up to
# date, (emulator, "github") for those downloaded from their own GitHub releases (GITHUB_EMUS), Dolphin's and Hatari's
# own downloads, RetroArch plus one core ("retroarch:<core>"), or "manual": only its project page.
EMU_INSTALL = {
    "PS1": ("DuckStation", "Stenzek.DuckStation"),
    "PS2": ("PCSX2", "PCSX2Team.PCSX2"),
    "PS3": ("RPCS3", "github"),
    "PS4": ("shadPS4", "shadps4-emu.shadPS4"),
    "PS5": ("KytyPS5", "github"),
    "PSP": ("PPSSPP", "PPSSPPTeam.PPSSPP"),
    "PS Vita": ("Vita3K", "Vita3K.Vita3K"),
    "Switch 2": ("Eglantine", "github"),
    "Switch": ("Eden", "Utopia.Eden.MSVC"),
    "Wii U": ("Cemu", "Cemu.Cemu"),
    "Wii": ("Dolphin", "dolphin"),
    "GameCube": ("Dolphin", "dolphin"),
    "N64": ("Project64", "Project64.Project64"),
    "SNES": ("Mesen", "github"),
    "3DS": ("Azahar", "AzaharEmu.Azahar"),
    "DS": ("melonDS", "melonDS.melonDS"),
    "GBA": ("mGBA", "JeffreyPfau.mGBA"),
    "GBC": ("mGBA", "JeffreyPfau.mGBA"),
    "Game Boy": ("mGBA", "JeffreyPfau.mGBA"),
    "Xbox 360": ("Xenia Canary", "github"),
    "Xbox": ("xemu", "xemu-project.xemu"),
    **{s: ("Mesen", "github") for s in ("NES", "FDS", "PC Engine", "PC Engine CD", "WonderSwan", "SG-1000")},
    **{s: ("Mednafen", "MednafenTeam.Mednafen") for s in ("Virtual Boy", "Neo Geo Pocket", "Atari Lynx", "PC-FX")},
    **{s: ("ares", "ares-emulator.ares") for s in ("Genesis", "Sega CD", "32X", "Master System", "Game Gear", "64DD")},
    **{s: ("Flycast", "github") for s in ("Dreamcast", "NAOMI", "NAOMI 2", "Atomiswave")},
    **{s: ("MAME", "MAMEdev.MAME") for s in ("Atari 7800", "Arcade", "Neo Geo", "Neo Geo CD", "CD-i", "Intellivision", "Vectrex", "Odyssey 2", "Game & Watch")},
    **{s: ("openMSX", "github") for s in ("ColecoVision", "MSX")},
    **{s: ("Atari800", "github") for s in ("Atari 5200", "Atari 8-bit")},
    **{s: ("VICE", "VICE-Team.VICE.GTK3") for s in ("C64", "VIC-20")},
    "Saturn": ("Ymir", "github"),
    "Model 3": ("Supermodel", "github"),
    "Atari 2600": ("Stella", "github"),
    "Atari Jaguar": ("BigPEmu", "manual"),
    "Atari ST": ("Hatari", "hatari"),
    "3DO": ("RetroArch", "retroarch:opera"),
    "Pokemon Mini": ("RetroArch", "retroarch:pokemini"),
    "Amstrad CPC": ("RetroArch", "retroarch:cap32"),
    "N-Gage": ("EKA2L1", "github"),
    "Amiga": ("Amiberry", "github"),
    "ZX Spectrum": ("ZEsarUX", "github"),
    "DOS": ("DOSBox Staging", "DOSBoxStaging.DOSBoxStaging"),
    "ScummVM": ("ScummVM", "ScummVM.ScummVM"),
    "Apple II": ("AppleWin", "AppleWin.AppleWin"),
    "Flash": ("Ruffle", "github"),
}
WINGET_ARGS = {"MAMEdev.MAME": ["--location", os.path.join(EMU_HOME, "MAME")]}  # its package needs a folder
# Packages that need to be told their folder, a fixed one in Program Files: given both ways of installing, the elevated
# helper's included (so it isn't a folder the page or the user's own files could change)
FIXED_ARGS = {"Blizzard.BattleNet": ["--location", os.path.join(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)", "Battle.net")]}
# Downloaded from the project's own GitHub releases: repo, the Windows download's name, the program inside it. Newest
# release first, pre-releases included (Eglantine only makes those, and some KytyPS5 builds have no Windows download).
GITHUB_EMUS = {
    "RPCS3": ("RPCS3/rpcs3-binaries-win", r"_win64.*\.7z$", "rpcs3.exe"),
    "KytyPS5": ("KytyPS5/KytyPS5", r"-Windows-x64\.zip$", "kyty_emulator.exe"),
    "Eglantine": ("Djihads80/Eglantine", r"^eglantine-windows-x86_64\.zip$", "eglantine.exe"),
    "Mesen": ("nesdev-org/MesenCE", r"^Mesen_[0-9.]+_Windows\.zip$", "Mesen.exe"),  # MesenCE: Mesen2 is archived
    "Xenia Canary": ("xenia-canary/xenia-canary", r"^xenia_canary_windows\.7z$", "xenia_canary.exe"),
    "Ymir": ("StrikerX3/Ymir", r"^ymir-windows-x86_64-(AVX2|SSE2)-v[0-9.]+\.zip$", "ymir-sdl3.exe"),  # AVX2 build when the CPU has it
    "Flycast": ("flyinghead/flycast", r"^flycast-win64-[0-9.]+\.zip$", "flycast.exe"),
    "Stella": ("stella-emu/stella", r"^Stella-[0-9.]+[a-z]?-windows\.zip$", "Stella.exe"),
    "openMSX": ("openMSX/openMSX", r"^openmsx-[0-9.]+-windows-vc-x64-bin\.zip$", "openmsx.exe"),
    "Atari800": ("atari800/atari800", r"^atari800-[0-9.]+-win64\.zip$", "atari800.exe"),
    "EKA2L1": ("EKA2L1/EKA2L1", r"^EKA2L1-Windows-x86_64\.zip$", "eka2l1_qt.exe"),  # the rolling build: the old numbered ones don't match
    "Amiberry": ("BlitterStudio/amiberry", r"^amiberry-v[0-9.]+-windows-x64-portable\.zip$", "Amiberry.exe"),
    "ZEsarUX": ("chernandezba/zesarux", r"^ZEsarUX_windows-[0-9.]+\.zip$", "zesarux.exe"),
    "Supermodel": ("trzy/Supermodel", r"^supermodel-.*-windows\.zip$", "Supermodel.exe"),
    "Ruffle": ("ruffle-rs/ruffle", r"^ruffle-[0-9.]+-windows-x86_64\.zip$", "ruffle.exe"),
}
# Each emulator's own project page (Settings > Systems), where it can also be downloaded by hand
EMU_SITES = {
    "DuckStation": "https://www.duckstation.org/", "PCSX2": "https://pcsx2.net/", "RPCS3": "https://rpcs3.net/",
    "shadPS4": "https://shadps4.net/", "KytyPS5": "https://github.com/KytyPS5/KytyPS5", "PPSSPP": "https://www.ppsspp.org/",
    "Vita3K": "https://vita3k.org/", "Eglantine": "https://github.com/Djihads80/Eglantine", "Eden": "https://eden-emu.dev/",
    "Cemu": "https://cemu.info/", "Dolphin": "https://dolphin-emu.org/", "Project64": "https://www.pj64-emu.com/",
    "Mesen": "https://github.com/nesdev-org/MesenCE", "Azahar": "https://azahar-emu.org/", "melonDS": "https://melonds.kuribo64.net/",
    "mGBA": "https://mgba.io/", "Xenia Canary": "https://xenia.jp/", "xemu": "https://xemu.app/",
    "Mednafen": "https://mednafen.github.io/", "ares": "https://ares-emu.net/", "Ymir": "https://github.com/StrikerX3/Ymir",
    "Flycast": "https://github.com/flyinghead/flycast", "Stella": "https://stella-emu.github.io/", "MAME": "https://www.mamedev.org/",
    "BigPEmu": "https://www.richwhitehouse.com/jaguar/", "openMSX": "https://openmsx.org/", "Atari800": "https://atari800.github.io/",
    "EKA2L1": "https://eka2l1.github.io", "VICE": "https://vice-emu.sourceforge.io/", "Amiberry": "https://amiberry.com/",
    "ZEsarUX": "https://github.com/chernandezba/zesarux", "Hatari": "https://www.hatari-emu.org/", "DOSBox Staging": "https://www.dosbox-staging.org/",
    "ScummVM": "https://www.scummvm.org/", "AppleWin": "https://github.com/AppleWin/AppleWin", "Supermodel": "https://supermodel3.com/",
    "Ruffle": "https://ruffle.rs/",
}
SYSTEM_SITES = {"3DO": "https://github.com/libretro/opera-libretro", "Pokemon Mini": "https://docs.libretro.com/library/pokemini/",
                "Amstrad CPC": "https://github.com/libretro/libretro-cap32"}  # RetroArch systems: their core's page


def emulator_for(system):
    return emu_table().get(system, [None])[0]


def system_site(system):
    return SYSTEM_SITES.get(system) or EMU_SITES.get(emulator_for(system))


INSTALL_LOCK = threading.Lock()
JOB_LOCAL = threading.local()  # .job: the queue job this thread is installing, which hears how far it has got


def job_progress(stage, done=None, total=None, percent=None, force=False):
    """Tell the queue job being installed its stage and how far it has got (percent from done/total bytes, or given; None
    when unknown). A no-op outside the queue. A new stage shows at once; the same stage at most about 4 times a second."""
    job = getattr(JOB_LOCAL, "job", None)
    if not job:
        return
    now = time.monotonic()
    if not force and stage == job.get("stage") and now - job.get("at", 0) < 0.25:
        return
    if percent is None and total:
        percent = done * 100 / total
    with QUEUE_COND:
        job.update(stage=stage, progress=None if percent is None else round(min(100, max(0, percent)), 1),
                   done=done, total=total or None, at=now)


def copy_progress(response, output, size=0, limit=0):
    """response -> output in 256 KB pieces as they arrive, telling the queue job how far it's got (from Content-Length, or
    the size the caller knows). limit: stop after that many bytes."""
    total = int(response.headers.get("Content-Length") or 0) or size
    done = 0
    job_progress("Downloading", 0, total, force=True)
    while not limit or done < limit:
        chunk = response.read(min(256 << 10, limit - done) if limit else 256 << 10)
        if not chunk:
            break
        output.write(chunk)
        done += len(chunk)
        job_progress("Downloading", done, total)
    job_progress("Downloading", done, total or done, force=True)
    return done


def unpack(archive, folder, name):
    """A zip with Python's own reader, anything else (7z) with 7-Zip, or Windows' tar when 7-Zip isn't installed."""
    import zipfile
    os.makedirs(folder, exist_ok=True)
    if archive.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(folder)  # extractall keeps every entry inside folder
        return
    tool = SEVEN_ZIP or shutil.which("tar")
    if not tool:
        raise ValueError(f"Install 7-Zip first to unpack {name}")
    command = [tool, "x", archive, "-o" + folder, "-y"] if SEVEN_ZIP else [tool, "-xf", archive, "-C", folder]
    if subprocess.run(command, capture_output=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode:
        raise ValueError(f"Could not unpack {name}. Install 7-Zip and try again.")


def cpu_avx2():
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # PF_AVX2_INSTRUCTIONS_AVAILABLE
    except (OSError, AttributeError):
        return False


def install_download(name, url, filename, program_name, digest="", size=0, target=None):
    """Download an emulator's archive, unpack it and keep the folder its program is in as C:\\Ultra-Front-End\\Emulators\\<name>
    (target: an installed copy to update). Unpacked over what's there, so its saves and settings stay; a settings file the
    emulator already has is never replaced by the download's default one."""
    import tempfile
    target = target or os.path.join(EMU_HOME, name)
    with tempfile.TemporaryDirectory(prefix="frontend-emu-") as staging:
        archive = os.path.join(staging, filename)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as response, open(archive, "wb") as output:
            copy_progress(response, output, size)
        if digest.startswith("sha256:") and file_sha256(archive) != digest[7:].lower():
            raise ValueError(f"The {name} download was damaged. Try again.")
        unpacked = os.path.join(staging, "unpacked")
        job_progress("Unpacking")
        unpack(archive, unpacked, name)
        programs = glob.glob(os.path.join(unpacked, "**", program_name), recursive=True)
        if not programs:
            raise ValueError(f"The {name} download has no {program_name}")
        job_progress("Setting up")
        os.makedirs(target, exist_ok=True)
        keep = lambda src, dst: dst if os.path.exists(dst) and dst.lower().endswith(EMU_SETTINGS) else shutil.copy2(src, dst)
        shutil.copytree(os.path.dirname(min(programs, key=len)), target, dirs_exist_ok=True, copy_function=keep)  # the program's folder, whatever wraps it
    return os.path.join(target, program_name)


# Eglantine publishes a build of every branch (branch-fix-..., branch-exp-...) beside its daily builds: installs and
# updates take the daily line, never someone's experiment
GITHUB_TAGS = {"Eglantine": r"^daily-\d{8}$"}


def github_latest(name):
    """The newest Windows download of a GitHub emulator: (asset, published) or (None, "")."""
    repo, pattern, program_name = GITHUB_EMUS[name]
    releases = http_json(f"https://api.github.com/repos/{repo}/releases?per_page=30", timeout=30)
    try:  # the list isn't always newest first (RPCS3's is by tag name), so the newest full release goes in too
        releases = [http_json(f"https://api.github.com/repos/{repo}/releases/latest", timeout=30)] + releases
    except (urllib.error.URLError, ValueError):  # none yet: Eglantine only makes pre-releases
        pass
    avx2 = cpu_avx2()
    line = GITHUB_TAGS.get(name)  # a project whose releases include test builds of single fixes: only its regular line
    found = sorted(((r.get("published_at") or "", a) for r in releases if not r.get("draft") and (not line or re.search(line, r.get("tag_name") or ""))
                    for a in r.get("assets", []) if re.search(pattern, a["name"]) and (avx2 or "AVX2" not in a["name"])),
                   key=lambda x: (x[0], "AVX2" in x[1]["name"]), reverse=True)
    return (found[0][1], found[0][0]) if found else (None, "")


def install_from_github(name, target=None):
    repo, pattern, program_name = GITHUB_EMUS[name]
    asset, published = github_latest(name)
    if not asset:
        raise ValueError(f"{name} has no Windows download right now. Its project page may have one.")
    url = asset["browser_download_url"]
    if not url.startswith(f"https://github.com/{repo}/releases/download/"):
        raise ValueError(f"{name}'s download isn't on its own project")
    # GitHub's SHA-256 of the file, on everything uploaded since mid-2025
    exe = install_download(name, url, asset["name"], program_name, asset.get("digest") or "", asset.get("size") or 0, target)
    versions = load("emu-versions.json", {})
    tag = (re.search(r"/releases/download/([^/]+)/", url) or [None, ""])[1]
    versions[name] = {"asset": asset["name"], "published": published, "tag": urllib.parse.unquote(tag), "folder": os.path.dirname(exe), "at": time.time()}
    EMU_VERSIONS.clear()
    store("emu-versions.json", versions)
    return exe


def install_hatari():
    """Hatari publishes on its own GitLab (framagit), not GitHub: the newest release's 64-bit Windows zip."""
    releases = http_json("https://framagit.org/api/v4/projects/hatari%2Fhatari/releases", timeout=30)
    for r in sorted(releases, key=lambda r: r.get("released_at") or "", reverse=True):
        for link in (r.get("assets") or {}).get("links", []):
            url = link.get("url") or ""
            if url.startswith("https://framagit.org/hatari/") and re.search(r"/hatari-[0-9.]+_windows64\.zip$", url):
                return install_download("Hatari", url, url.rsplit("/", 1)[1], "hatari.exe")
    raise ValueError("Hatari has no Windows download right now. Its project page may have one.")


CORE_EXT = ".dylib" if MAC else ".dll"
CORE_URL = ("https://buildbot.libretro.com/nightly/apple/osx/%s/latest/{}_libretro.dylib.zip" % ("arm64" if __import__("platform").machine() == "arm64" else "x86_64")
            if MAC else "https://buildbot.libretro.com/nightly/windows/x86_64/latest/{}_libretro.dll.zip")


def install_core(retroarch, core):
    """One RetroArch core from libretro's own build server into RetroArch's cores folder (never replacing one)."""
    import io
    import zipfile
    dll = (os.path.expanduser(f"~/Library/Application Support/RetroArch/cores/{core}_libretro.dylib") if MAC
           else os.path.join(os.path.dirname(retroarch), "cores", f"{core}_libretro.dll"))
    if os.path.isfile(dll):
        return dll
    with urllib.request.urlopen(urllib.request.Request(CORE_URL.format(core), headers={"User-Agent": UA}), timeout=120) as response:
        if not response.geturl().startswith("https://buildbot.libretro.com/"):
            raise ValueError("The core download went somewhere other than libretro's build server")
        buffer = io.BytesIO()
        copy_progress(response, buffer, limit=200 << 20)
        data = buffer.getvalue()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            body = z.read(f"{core}_libretro{CORE_EXT}")  # that one file, at the top: nothing else in the zip is used
    except (zipfile.BadZipFile, KeyError):
        raise ValueError(f"The {core} core download was damaged. Try again.")
    if body[:2] != b"MZ" and not MAC or MAC and body[:4] not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        raise ValueError(f"The {core} core download isn't a program for this computer")
    job_progress("Setting up")
    os.makedirs(os.path.dirname(dll), exist_ok=True)
    with open(dll + ".part", "wb") as f:
        f.write(body)
    os.replace(dll + ".part", dll)
    return dll


def install_dolphin():
    # Official release, verified against https://dolphin-emu.org/download/.
    import tempfile
    target = os.path.join(EMU_HOME, "Dolphin-2609a")
    exe = os.path.join(target, "Dolphin-x64", "Dolphin.exe")
    if not os.path.isfile(exe):
        with tempfile.TemporaryDirectory(prefix="frontend-dolphin-") as staging:
            archive = os.path.join(staging, "dolphin.7z")
            req = urllib.request.Request("https://dl.dolphin-emu.org/releases/2609a/dolphin-2609a-x64.7z", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as response, open(archive, "wb") as output:
                copy_progress(response, output)
            job_progress("Unpacking")
            unpacked = os.path.join(staging, "unpacked")
            os.makedirs(unpacked)
            tool = SEVEN_ZIP or shutil.which("tar")
            if not tool:
                raise ValueError("Install 7-Zip first to unpack Dolphin")
            command = [tool, "x", archive, "-o" + unpacked, "-y"] if SEVEN_ZIP else [tool, "-xf", archive, "-C", unpacked]
            result = subprocess.run(command, capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode or not os.path.isfile(os.path.join(unpacked, "Dolphin-x64", "Dolphin.exe")):
                raise ValueError("Could not unpack the Dolphin release. Install 7-Zip and try again.")
            job_progress("Setting up")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copytree(unpacked, target, dirs_exist_ok=True)
    return exe


# winget redraws its download bar in place (\r, and \b for its spinner): "##########....  12.5 MB / 34.2 MB", or a percentage
WINGET_BYTES = re.compile(r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)\s*/\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)")
WINGET_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
SIZE_UNITS = {"B": 1, "KB": 1 << 10, "MB": 1 << 20, "GB": 1 << 30}


def winget_progress(text, seen):
    """Follow winget's download in the newest of its output; once it's downloaded, the install itself (no percent)."""
    if seen["installing"]:
        return
    if "Starting package install" in text or "Successfully verified installer hash" in text:
        seen["installing"] = True
        return job_progress("Installing", force=True)
    newest = [piece for piece in re.split(r"[\r\n\b]+", text) if piece.strip()][-1:]
    sizes = WINGET_BYTES.findall(newest[0]) if newest else []
    if sizes:
        done, total = (round(float(n) * SIZE_UNITS[u]) for n, u in (sizes[-1][:2], sizes[-1][2:]))
        job_progress("Downloading", min(done, total), total)
    elif newest and WINGET_PERCENT.search(newest[0]):
        job_progress("Downloading", percent=float(WINGET_PERCENT.findall(newest[0])[-1]))
    else:
        return
    job = getattr(JOB_LOCAL, "job", None)
    if job and job.get("progress") is not None and job["progress"] >= 100:
        seen["installing"] = True
        job_progress("Installing", force=True)


INSTALL_HINT = 60  # seconds of quiet before the page suggests answering a window the installer opened
INSTALL_STALLED = 300  # seconds of quiet before the install is stopped
INSTALL_LONGEST = 2700  # however busy it looks, never longer than this
WINGET_STALLED = 0x8A15FFF1  # the elevated helper's answer when it stopped a stalled install
STALLED_TEXT = ("{name}'s installer stopped responding, so it was stopped after 5 minutes. It may have been waiting for a "
                "window hidden behind Ultra Front End. Try again, or install it from its own website.")


def tree_cpu(pid):
    """CPU seconds used so far by a process and everything it started (those this program may look at)."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    total = 0
    for p in process_tree(pid):
        h = k32.OpenProcess(0x1000, False, p)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        times = [ctypes.c_ulonglong() for _ in range(4)]
        if k32.GetProcessTimes(h, *[ctypes.byref(x) for x in times]):
            total += times[2].value + times[3].value  # kernel + user, in 100 ns
        k32.CloseHandle(h)
    return total / 1e7


def msi_busy():
    """Windows Installer is installing something (its execute mutex exists): MSI packages run in its own service, outside winget's
    process tree, so their work doesn't show up in tree_cpu."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenMutexW.restype = ctypes.c_void_p
    k32.OpenMutexW.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.OpenMutexW(0x00100000, False, "Global\\_MSIExecute")  # SYNCHRONIZE
    if h:
        k32.CloseHandle(h)
        return True
    return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: there, but not ours to open


def watch_install(proc, last_output, hint=True):
    """Waits for winget to finish. Returns its exit code, or None if it was stopped: nothing from it for INSTALL_STALLED seconds
    (no output, no CPU used by it or anything it started, Windows Installer idle), which is usually an installer waiting on
    a window nobody can see. hint: say so on the page after a minute of quiet."""
    start = active = time.time()
    cpu, hinted = tree_cpu(proc.pid), False
    while True:
        try:
            return proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        now, used = time.time(), tree_cpu(proc.pid)
        if used - cpu > 0.2 or msi_busy():
            active = now
        cpu, active = used, max(active, last_output[0])
        if hint and not hinted and now - active > INSTALL_HINT:
            hinted = True
            job_progress("Still installing. If a window popped up, answer it", force=True)
        elif hinted and now - active < 5:
            hinted = False
            job_progress("Installing", force=True)
        if now - active > INSTALL_STALLED or now - start > INSTALL_LONGEST:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            return None


def winget_install(package_id, name, plain=False):
    """plain: without asking for C:\\Ultra-Front-End\\Emulators (the second go, if an installer won't take a folder)."""
    try:
        return winget_install_once(package_id, name, plain)
    except ValueError as e:
        if plain or not emu_location(package_id) or "winget code" not in str(e):
            raise
        return winget_install(package_id, name, plain=True)


def winget_install_once(package_id, name, plain=False):
    import codecs
    winget = shutil.which("winget")
    if not winget:
        raise ValueError("Install Microsoft App Installer from the Microsoft Store first, then restart the frontend")
    if package_id in broker_packages() and start_broker():  # one administrator prompt for all of setup's installs
        code, text = winget_via_broker(package_id, name, plain)
        if code != BROKER_NO_WINGET:  # (it couldn't find winget where only administrators can change it: the usual way)
            return winget_result(package_id, name, code, [text])
    where = "" if plain else emu_location(package_id)
    if where:
        os.makedirs(where, exist_ok=True)
    proc = subprocess.Popen(
        [winget, "install", "--id", package_id, "--exact", "--source", "winget", *WINGET_ARGS.get(package_id, []), *FIXED_ARGS.get(package_id, []),
         *(["--location", where] if where else []),
         "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity", "--silent"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out, job, last_output = [], getattr(JOB_LOCAL, "job", None), [time.time()]

    def pump():  # read the output as it streams (read1: whatever has arrived), for the progress and the log
        JOB_LOCAL.job = job
        decoder, recent, seen = codecs.getincrementaldecoder("utf-8")("replace"), "", {"installing": False}
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            text = decoder.decode(chunk)
            out.append(text)
            last_output[0] = time.time()
            recent = (recent + text)[-400:]  # a redraw split across two reads still parses
            winget_progress(recent, seen)
        out.append(decoder.decode(b"", True))

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        code = watch_install(proc, last_output)
    finally:
        reader.join(30)
    return winget_result(package_id, name, WINGET_STALLED if code is None else code, out)


def winget_result(package_id, name, code, out):
    if code & 0xffffffff not in (0, 0x8A15002B):  # already installed with no upgrade is also success
        with open(os.path.join(DATA, "emulator-install.log"), "a", encoding="utf-8") as log:
            log.write(f"--- {time.strftime('%Y-%m-%d %H:%M')} winget install {package_id}: code {code & 0xffffffff:#x}"
                      f"{' (stopped: no activity)' if code & 0xffffffff == WINGET_STALLED else ''}\n{''.join(out)}\n")
        if code & 0xffffffff == WINGET_STALLED:
            raise ValueError(STALLED_TEXT.format(name=name))
        raise ValueError(f"{name} didn't install (winget code {code & 0xffffffff:#x}). Try again, or use its "
                         "project page. Details are in emulator-install.log in the data folder.")


# ---------- one administrator prompt for setup's installs ----------
# Some winget installers (the game launchers, several emulators) each ask Windows for administrator rights, sometimes behind
# the full-screen frontend. Instead, Windows asks once: an elevated copy of this program (--install-broker) runs the
# installs, then closes. It only ever runs "winget install" for a package in the app's own tables, so nothing else on the
# PC can use it to run something as administrator. Not for standard accounts: if another person's administrator account
# approved it, the installs would land in that person's user folder.
BROKER = {"token": "", "seen": 0.0, "jobs": [], "next": 0, "out": {}, "done": {}, "declined": 0.0}
BROKER_COND = threading.Condition()
ADMINISTRATORS = "S-1-5-32-544"
BROKER_NO_WINGET = 0x8A15FFF0  # the elevated helper's answer when there's no winget it can trust


def protected_winget():
    """winget.exe in its own package folder in Program Files › WindowsApps, which only administrators can change; never
    the copy found through PATH (the user's own PATH and WindowsApps alias folder are theirs to change, so a planted
    winget there would run as administrator). The newest version, or ""."""
    root = os.path.join(os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files", "WindowsApps")
    found = []
    for folder in glob.glob(os.path.join(glob.escape(root), "Microsoft.DesktopAppInstaller_*__8wekyb3d8bbwe")):
        exe = os.path.join(folder, "winget.exe")
        real = os.path.realpath(exe)
        if os.path.isfile(real) and os.path.normcase(real).startswith(os.path.normcase(os.path.realpath(root)) + os.sep):
            found.append((version_key(os.path.basename(folder).split("_")[1]), real))
    return max(found)[1] if found else ""


def emu_location(package_id):
    """C:\\Ultra-Front-End\\Emulators\\<emulator> for an emulator's winget package (RetroArch's included), else "". Made
    from the app's own tables and fixed folder, never from a request. Installers that ignore it go to their usual place."""
    if not WIN or package_id in WINGET_ARGS or package_id in FIXED_ARGS:
        return ""
    names = {p[1]: p[0] for p in EMU_INSTALL.values() if p and p[1]}
    names["Libretro.RetroArch"] = "RetroArch"
    name = names.get(package_id)
    return os.path.join(EMU_HOME, re.sub(r'[<>:"/\\|?*]', "", name)) if name else ""


def plain_folder(path):
    """True if no part of the path that exists is a link or junction to somewhere else: the elevated helper only installs
    into C:\\Ultra-Front-End\\Emulators when it is really there (the folder is the user's, so it could be pointed elsewhere)."""
    part = path
    while True:
        if os.path.lexists(part) and (os.path.islink(part) or os.path.normcase(os.path.realpath(part)) != os.path.normcase(os.path.abspath(part))):
            return False
        parent = os.path.dirname(part)
        if parent == part:
            return True
        part = parent


def broker_packages():
    """The winget packages the elevated helper may install: the launchers' and the emulators' (MAME's needs a folder in the
    user's own home, so it installs the usual way)."""
    ids = {wid for _, _, wid in LAUNCHERS} | {"Libretro.RetroArch"}
    ids |= {p[1] for p in EMU_INSTALL.values() if p and re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", p[1] or "")}
    return ids - set(WINGET_ARGS)


def broker_alive():
    return bool(BROKER["token"]) and time.time() - BROKER["seen"] < 40


def start_broker():
    """Windows' prompt, once, for the elevated install helper. False if it can't be used (then installers ask as usual)."""
    if not WIN or broker_alive():
        return broker_alive()
    if time.time() - BROKER["declined"] < 600 or ADMINISTRATORS not in token_groups():
        return False
    import secrets
    token = secrets.token_hex(16)
    with BROKER_COND:
        BROKER.update(token=token, seen=0.0)
    exe = frontend_exe()
    args = f"--install-broker {PORT} {token}"
    if not getattr(sys, "frozen", False):  # from source: Python runs frontend.py
        exe, args = sys.executable, subprocess.list2cmdline([os.path.join(ROOT, "frontend.py")]) + " " + args
    try:
        shell_runas(exe, args)
    except ValueError:
        BROKER["declined"] = time.time()  # no for now: the installers ask as usual, and setup can offer again later
        return False
    deadline = time.time() + 30
    while time.time() < deadline and not broker_alive():
        time.sleep(0.3)
    return broker_alive()


def shell_runas(program, params):
    """Start a program through Windows' administrator prompt without waiting for it."""
    import ctypes
    import ctypes.wintypes as W

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("fMask", W.ULONG), ("hwnd", W.HWND), ("lpVerb", W.LPCWSTR), ("lpFile", W.LPCWSTR), ("lpParameters", W.LPCWSTR),
                    ("lpDirectory", W.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", W.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", W.LPCWSTR),
                    ("hkeyClass", W.HKEY), ("dwHotKey", W.DWORD), ("hIcon", W.HANDLE), ("hProcess", W.HANDLE)]
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(Info)]
    info = Info(cbSize=ctypes.sizeof(Info), fMask=0x100, lpVerb="runas", lpFile=program, lpParameters=params, nShow=0)  # NOASYNC, hidden
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        raise ValueError("Windows' permission prompt was cancelled" if ctypes.get_last_error() == 1223 else "Windows' permission prompt couldn't open")


def winget_via_broker(package_id, name, plain=False):
    """winget install through the elevated helper: its output comes back as it runs, for the progress bar. Returns winget's exit code."""
    where = "" if plain else emu_location(package_id)
    if where:
        os.makedirs(where, exist_ok=True)  # made by the user's own copy, so it's theirs; the helper checks it's really there
    with BROKER_COND:
        BROKER["next"] += 1
        job = BROKER["next"]
        BROKER["jobs"].append({"id": job, "package": package_id, "plain": bool(plain)})
        BROKER["out"][job] = []
        BROKER_COND.notify_all()
    seen, recent, deadline, everything = {"installing": False}, "", time.time() + INSTALL_LONGEST + 300, []
    heard, hinted = time.time(), False
    while True:
        with BROKER_COND:
            BROKER_COND.wait_for(lambda: BROKER["out"][job] or job in BROKER["done"] or not broker_alive(), timeout=5)
            chunks, BROKER["out"][job] = BROKER["out"][job], []
            code = BROKER["done"].pop(job, None)
        for text in chunks:
            everything.append(text)
            heard = time.time()
            recent = (recent + text)[-400:]
            winget_progress(recent, seen)
        if not hinted and time.time() - heard > INSTALL_HINT:  # (the elevated helper does the stopping: it can see the installer)
            hinted = True
            job_progress("Still installing. If a window popped up, answer it", force=True)
        elif hinted and chunks:
            hinted = False
            job_progress("Installing", force=True)
        if code is not None:
            BROKER["out"].pop(job, None)
            return code, "".join(everything)
        if not broker_alive() or time.time() > deadline:
            with BROKER_COND:
                BROKER["jobs"] = [j for j in BROKER["jobs"] if j["id"] != job]
            raise ValueError(f"{name}: the installer helper stopped. Try again.")


def install_broker(port, token):
    """The elevated side (--install-broker): asks the helper for installs, runs winget for each, sends the output back.
    Leaves after ten idle minutes, or once the helper is gone."""
    try:
        broker_loop(port, token)
    except Exception:  # whatever happens, it just goes (an error box from a hidden administrator process would only confuse)
        pass


def broker_loop(port, token):
    import codecs
    base, last_job, last_answer = f"http://127.0.0.1:{int(port)}/api/broker", time.time(), time.time()
    allowed, system32 = broker_packages(), os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32")

    def post(path, body):
        try:
            req = urllib.request.Request(base + path, data=json.dumps({**body, "token": token}).encode(), headers={"Content-Type": "application/json", "X-Frontend": "1"})
            urllib.request.urlopen(req, timeout=15).read()
        except (OSError, ValueError):
            pass
    while time.time() - last_job < 600 and time.time() - last_answer < 60:
        try:
            with urllib.request.urlopen(f"{base}/next?token={token}", timeout=40) as r:
                job = json.loads(r.read() or b"{}")
            last_answer = time.time()
        except (OSError, ValueError):
            time.sleep(2)
            continue
        if not isinstance(job, dict) or not job:
            continue
        last_job = time.time()
        if not isinstance(job.get("package"), str) or job["package"] not in allowed:  # only the app's own packages, whatever is asked
            post("/done", {"job": job.get("id"), "exit": 1})
            continue
        winget = protected_winget()
        if not winget:
            post("/done", {"job": job.get("id"), "exit": BROKER_NO_WINGET})
            continue
        where = "" if job.get("plain") else emu_location(job["package"])  # the app's own folder for it, never one from the request
        if where and not (os.path.isdir(where) and plain_folder(where)):
            where = ""  # not there, or pointed somewhere else: installed to its usual place
        proc = subprocess.Popen([winget, "install", "--id", job["package"], "--exact", "--source", "winget", *FIXED_ARGS.get(job["package"], []),
                                 *(["--location", where] if where else []), "--accept-source-agreements",
                                 "--accept-package-agreements", "--disable-interactivity", "--silent"], cwd=system32,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        decoder, last_output = codecs.getincrementaldecoder("utf-8")("replace"), [time.time()]

        def pump(job_id=job["id"]):
            while True:
                chunk = proc.stdout.read1(65536)
                if not chunk:
                    break
                last_output[0] = time.time()
                post("/out", {"job": job_id, "text": decoder.decode(chunk)})
        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        code = watch_install(proc, last_output, hint=False)
        reader.join(30)
        post("/done", {"job": job["id"], "exit": WINGET_STALLED if code is None else code & 0xffffffff})
        last_answer = last_job = time.time()  # a long install isn't the helper going quiet


def connect_emulator(package, exe=None):
    """Give every console this package plays its program (found, or the one just installed), keeping the user's own choices."""
    cfg, found = config(), {} if exe else find_emulators()
    for console, candidate in emu_table().items():
        path = exe or found.get(console)
        if candidate == package and path and not cfg.get("emulators", {}).get(console, {}).get("path"):
            cfg.setdefault("emulators", {})[console] = {"path": path, "args": emulator_args(path, (system_info(console) or {"cores": []})["cores"], console)}
    store("config.json", cfg)
    return cfg


def install_emulator(system):
    package = emu_table().get(system)
    if not package:
        raise ValueError("Installation is not available for this console yet")
    if package[1] == "manual":
        raise ValueError(f"{package[0]} can't be installed from here. Download it from its project page, then choose its program.")
    if not INSTALL_LOCK.acquire(blocking=False):
        raise ValueError("An emulator installation is already running")
    try:
        source = package[1]
        if source == "mac":  # from the emulator's own project, into ~/Applications
            cfg = connect_emulator(package, install_mac_app(package[0]))
        elif source.startswith("retroarch:"):  # RetroArch once, then this console's core into its cores folder
            ra = find_emulators(keep_retroarch=True).get("_retroarch")
            if not ra and MAC:
                raise ValueError("Download RetroArch from retroarch.com into Applications first, then try again")
            if not ra:
                winget_install("Libretro.RetroArch", "RetroArch")
                ra = find_emulators(keep_retroarch=True).get("_retroarch")
            if not ra:
                raise ValueError("RetroArch installed, but its program wasn't found. Choose it with Choose program.")
            install_core(ra, source.split(":", 1)[1])
            cfg = connect_emulator(package, ra)
        elif source in ("dolphin", "github", "hatari"):
            cfg = connect_emulator(package, install_dolphin() if source == "dolphin" else install_hatari() if source == "hatari" else install_from_github(package[0]))
        else:
            winget_install(source, package[0])
            job_progress("Setting up")
            cfg = connect_emulator(package)
        job_progress("Setting up")
        scan()
        return {**settings_view(), "installedEmulator": package[0], "detected": bool(cfg.get("emulators", {}).get(system, {}).get("path"))}
    except subprocess.TimeoutExpired:
        raise ValueError("Installation timed out. Check Windows for an installer prompt before trying again.")
    finally:
        INSTALL_LOCK.release()


FIND_SKIP = {"windows", "$recycle.bin", "system volume information", "steamapps", "steamlibrary", "node_modules", "windowsapps", "programdata", "appdata"}


def system_info(name):
    return next(({"system": s, "thumbs": t, "exts": e.split(), "cores": c} for _, s, t, e, c in SYSTEMS if s == name), None)


EMU_FIND_MAC = {"DOS": ["dosbox*.app"], "Saturn": ["ymir*.app"], "C64": ["vice*.app"], "VIC-20": ["vice*.app"], "N-Gage": ["eka2l1*.app"],
                "ColecoVision": ["openmsx*.app"], "MSX": ["openmsx*.app"], "PS5": ["kyty*.app"], "N64": ["ares.app"],
                "Switch 2": ["eglantine*.app"]}  # Mac app names that differ from the Windows exe's
BREW_BIN = ("/opt/homebrew/bin", "/usr/local/bin")  # Homebrew's command-line emulators (mame, mednafen, atari800...)


def find_emulators_mac():
    """Known emulators installed as Mac apps (Dolphin.app, PCSX2.app, RetroArch.app...), or as Homebrew commands."""
    import fnmatch
    home, found = os.path.expanduser("~"), {}
    for root in ("/Applications", os.path.join(home, "Applications"), os.path.join(home, "Emulators")):  # (not Downloads or the Desktop: slow, and apps belong in Applications)
        if not os.path.isdir(root):
            continue
        base = root.rstrip("/").count(os.sep)
        for dirpath, dirs, _ in os.walk(root):
            apps = [d for d in dirs if d.lower().endswith(".app")]
            dirs[:] = [] if dirpath.count(os.sep) - base >= 2 else [d for d in dirs if not d.lower().endswith(".app")]
            for a in sorted(apps, key=str.lower):
                al = a.lower()
                for platform, pats in EMU_FIND.items():
                    pats = [p.replace(".exe", ".app") for p in pats] + EMU_FIND_MAC.get(platform, [])
                    if platform not in found and any(fnmatch.fnmatch(al, p) for p in pats):
                        found[platform] = os.path.join(dirpath, a)
                if al == "retroarch.app":
                    found.setdefault("_retroarch", os.path.join(dirpath, a))
    for platform, pats in EMU_FIND.items():
        if platform in found:
            continue
        for d in BREW_BIN:
            names = os.listdir(d) if os.path.isdir(d) else []
            hit = next((n for n in sorted(names) for p in pats if fnmatch.fnmatch(n.lower(), p.lower().replace(".exe", ""))), None)
            if hit:
                found[platform] = os.path.join(d, hit)
                break
    return found


def find_emulators(keep_retroarch=False):
    """Look in the usual install places for known emulators. Returns {platform: exe path} (and RetroArch as "_retroarch")."""
    import fnmatch
    if MAC:
        found = find_emulators_mac()
        ra = found.pop("_retroarch", None)
        for name in ROM_FOLDERS if ra else []:
            info = system_info(name)
            if name not in found and info and info["cores"] and emulator_args(ra, info["cores"])[1:2] == ["-L"]:
                found[name] = ra
        return found
    home = os.path.expanduser("~")
    roots = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"), os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"),
             EMU_HOME, os.path.join(home, "Emulators"), os.path.join(home, "Desktop"), os.path.join(home, "Downloads"), os.path.join(home, "Documents"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "DOSBox"), "C:\\RetroArch-Win64",  # DOSBox Staging's and RetroArch's own installers
             "C:\\Emulators", "C:\\Games"] + [f"{d}:\\" for d in "DEFGH" if os.path.isdir(f"{d}:\\")]
    found = {}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        base = root.rstrip("\\/").count(os.sep)
        for dirpath, dirs, files in os.walk(root):
            if dirpath.count(os.sep) - base >= 3:
                dirs[:] = []
            dirs[:] = [d for d in dirs if d.lower() not in FIND_SKIP]
            for f in sorted(files, key=lambda name: ("-sdl" in name.lower(), name.lower())):
                fl = f.lower()
                if not fl.endswith(".exe") or EXE_SKIP.search(fl) or re.search(r"[-_](cli|cmd|nogui|room)\b", fl):  # want the normal app (azahar-room is its netplay server)
                    continue
                for platform, pats in EMU_FIND.items():
                    if platform not in found and any(fnmatch.fnmatch(fl, p) for p in pats):
                        found[platform] = os.path.join(dirpath, f)
                if fl == "retroarch.exe":
                    found.setdefault("_retroarch", os.path.join(dirpath, f))
    ra = found.pop("_retroarch", None)
    if ra:  # RetroArch fills any retro platform that has a matching core installed
        for name in ROM_FOLDERS:
            info = system_info(name)
            if name not in found and info and info["cores"] and emulator_args(ra, info["cores"])[1:2] == ["-L"]:
                found[name] = ra
    if ra and keep_retroarch:
        found["_retroarch"] = ra
    return found


def auto_emulators(cfg):
    """Fill in emulators for platforms that don't have one yet. Returns how many were added."""
    emus, added = cfg.setdefault("emulators", {}), 0
    for platform, exe in find_emulators().items():
        if platform not in emus:
            info = system_info(platform) or {"cores": []}
            emus[platform] = {"path": exe, "args": emulator_args(exe, info["cores"], platform)}
            added += 1
    return added


ARCHIVES = [".zip", ".7z"]  # any console folder may hold zipped games
# Emulators that open zipped games themselves; for the rest the game is unpacked on first play.
ZIP_OK = re.compile(r"retroarch|snes9x|bsnes|mesen|mgba|project64|simple64|fceux|nestopia|blastem|kega|visualboy|vba|gens|higan|ares", re.I)
SEVEN_ZIP = next((p for p in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe") if os.path.isfile(p)), None) or shutil.which("7z") or shutil.which("7zz")


def detect_system(folder):
    name = os.path.basename(folder.rstrip("\\/")).lower()
    for pat, sysname, thumbs, exts, cores in SYSTEMS:
        if re.search(pat, name):
            return {"system": sysname, "thumbs": thumbs, "exts": list(dict.fromkeys(exts.split() + ARCHIVES)), "cores": cores}
    return {"system": os.path.basename(folder.rstrip("\\/")), "thumbs": None, "exts": None, "cores": []}


RA_BIOS = {"3DO", "Pokemon Mini"}  # RetroArch systems whose core reads its BIOS from the system folder


def emulator_args(emu, cores, system=None):
    name = os.path.basename(emu).lower()
    if "retroarch" in name:
        for core in cores:
            dll = (os.path.expanduser(f"~/Library/Application Support/RetroArch/cores/{core}_libretro.dylib") if MAC
                   else os.path.join(os.path.dirname(emu), "cores", f"{core}_libretro.dll"))
            if os.path.isfile(dll):
                return ["-f", "-L", dll, *(["--appendconfig", "{bioscfg}"] if system in RA_BIOS else []), "{rom}"]
        return ["-f", "{rom}"]
    pat, args = CONSOLE_ARGS.get(system, (None, None))
    if pat and re.search(pat, name):
        return list(args)
    for pat, args in EMU_ARGS:
        if re.search(pat, name):
            return list(args)
    return ["{rom}"]


def best_app(folder):
    """A Mac game in a folder: the .app named most like the folder, else the shallowest (an .app is a folder: not looked inside)."""
    apps, base = [], folder.rstrip("/").count(os.sep)
    for dirpath, dirs, _ in os.walk(folder):
        found = [d for d in dirs if d.lower().endswith(".app")]
        apps += [os.path.join(dirpath, d) for d in found]
        dirs[:] = [] if dirpath.count(os.sep) - base >= 2 else [d for d in dirs if d not in found]
    if not apps:
        return None
    want = norm(os.path.basename(folder))
    return max(apps, key=lambda p: (bool(want) and (want in norm(os.path.basename(p)) or norm(os.path.splitext(os.path.basename(p))[0]) in want), -p.count(os.sep)))


def best_exe(folder, exts=(".exe",)):
    exes = []
    base = folder.rstrip("\\/").count(os.sep)
    for dirpath, dirs, files in os.walk(folder):
        if dirpath.count(os.sep) - base >= 3:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(exts) and not EXE_SKIP.search(f):
                p = os.path.join(dirpath, f)
                exes.append(p)
    if not exes:
        return None
    want = norm(os.path.basename(folder))
    # Prefer an exe named like the folder, then the shallowest, then the biggest.
    return max(exes, key=lambda p: (bool(want) and (norm(os.path.splitext(os.path.basename(p))[0]) in want or want in norm(os.path.basename(p))),
                                    -p.count(os.sep), os.path.getsize(p)))


def online_cover(title):
    """Look a PC game up on the Steam store by name and use its library art (cached)."""
    cache = load("cover-cache.json", {})
    key = norm(title)
    if key not in cache:
        try:
            items = http_json("https://store.steampowered.com/api/storesearch/?" + urllib.parse.urlencode({"term": title, "l": "english", "cc": "US"}), timeout=6).get("items", [])
            # the same name, or the top result when one name holds the other and they're nearly the same length
            # ("Retail" is no "Retail Hell": only names close in length count)
            close = lambda x, y: (x in y or y in x) and min(len(x), len(y)) >= .75 * max(len(x), len(y))
            hit = next((i for i in items if norm(i["name"]) == key), None) or next((i for i in items[:1] if close(key, norm(i["name"]))), None)
            cache[key] = (steam_store_art([str(hit["id"])]).get(str(hit["id"])) or STEAM_CDN.format(hit["id"])) if hit else ""
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            return ""
        store("cover-cache.json", cache)
    return cache[key]


def clean_title(stem):
    return re.sub(r"\s+", " ", re.sub(r"[\(\[].*?[\)\]]", "", stem.replace("_", " "))).strip() or stem


# a console name tacked onto a ROM's file name ("Gran Turismo 7 PS5"); DS/3DS/Wii are left alone since real titles end in them
SYSTEM_TAGS = r"ps[1-5]|psx|psp|ps ?vita|playstation ?[1-5]?|switch|nsw|gba|gbc|n64|snes|game ?cube|ngc|wii ?u"


def zip_names(path):
    """Lower-case file names inside a .zip (read from its index, so instant even for huge archives); None if unreadable."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            return [os.path.basename(n).lower() for n in z.namelist()]
    except (OSError, ValueError, zipfile.BadZipFile):
        return None


def read_sfo(b):
    """PlayStation param.sfo (key/value table) -> dict."""
    import struct
    if b[:4] != b"\0PSF":
        return {}
    keys, data, n = struct.unpack_from("<III", b, 8)
    out = {}
    for i in range(n):
        ko, fmt, ln, _, do = struct.unpack_from("<HHIII", b, 0x14 + i * 16)
        key = b[keys + ko:b.index(b"\0", keys + ko)].decode("ascii", "replace")
        raw = b[data + do:data + do + ln]
        out[key] = struct.unpack("<I", raw[:4])[0] if fmt == 0x404 else raw.rstrip(b"\0").decode("utf-8", "replace")
    return out


PKG_CACHE = {}


def ps4_pkg(path):
    """A PS4 .pkg's own param.sfo: {"title", "id", "kind" (game/update/add-on), "ver"}; None for other files. Read from the
    package's entry table, so instant even for 50 GB packages."""
    import struct
    try:
        st = os.stat(path)
        key = (path, st.st_size, st.st_mtime)
        if key not in PKG_CACHE:
            with open(path, "rb") as f:
                h, info = f.read(0x20), None
                if h[:4] == b"\x7fCNT":
                    count, table = struct.unpack_from(">I", h, 0x10)[0], struct.unpack_from(">I", h, 0x18)[0]
                    f.seek(table)
                    t = f.read(min(count, 4096) * 32)
                    for i in range(len(t) // 32):
                        eid, _, _, _, off, size = struct.unpack_from(">IIIIII", t, i * 32)
                        if eid == 0x1000 and size < 1 << 20:  # param.sfo
                            f.seek(off)
                            sfo = read_sfo(f.read(size))
                            info = {"title": re.sub(r"[™®©\ufffd]", "", sfo.get("TITLE", "")).strip(), "id": sfo.get("TITLE_ID", ""),
                                    "content": sfo.get("CONTENT_ID", ""),
                                    "kind": {"gd": "game", "gp": "update", "ac": "add-on"}.get(sfo.get("CATEGORY", ""), "game"),
                                    "ver": sfo.get("APP_VER") or sfo.get("VERSION") or ""}
                            break
            PKG_CACHE[key] = info
        return PKG_CACHE[key]
    except (OSError, ValueError, IndexError):
        return None


def scene_title(stem):
    """'[SPSX]-Gran.Turismo.Sport-CUSA02168-EUR-...' -> 'Gran Turismo Sport'."""
    t = re.sub(r"^(\[[^\]]*\][-_ ]*)+", "", stem)
    t = re.split(r"[-_ ](?:CUSA|PPSA|PCJS|PLJS|PCAS|BLUS|BLES|NPUB|NPEB)\d{5}", t)[0]
    return re.sub(r"\s+", " ", t.replace(".", " ").replace("_", " ")).strip() or stem


def ps4_group(games, pkgs, lib):
    """One tile per PS4 game. Updates and add-ons fold into their game; a game installed as a folder hides its .pkg; and
    shadPS4, which only plays installed games, gets a clear message instead of a .pkg it can't open."""
    installed = {g["titleId"] for g in games if g.get("titleId")}
    by_id, out = {}, []
    for g in games:
        info = pkgs.get(g["id"])
        if info and info["id"]:
            by_id.setdefault(info["id"], []).append((g, info))
        else:
            out.append(g)
    for tid, items in by_id.items():
        if tid in installed:
            continue
        game = next(((g, i) for g, i in items if i["kind"] == "game"), None)
        g, info = game or next(((g, i) for g, i in items if i["kind"] == "update"), items[0])
        name = info["title"] if info["kind"] != "add-on" else scene_title(os.path.splitext(os.path.basename(g["launch"].get("rom") or g.get("_file", "")))[0])
        g["title"], g["titleId"] = name or g["title"], tid
        extras = [i for _, i in items if i is not info]
        if not game:
            g["launch"] = {"type": "none", "message": f"Only {'an update' if info['kind'] == 'update' else 'an add-on'}"
                           f"{' (v' + info['ver'].lstrip('0') + ')' if info['ver'] and info['kind'] == 'update' else ''} for {g['title']} "
                           f"is here. Add the game's own .pkg to play it."}
        elif g["launch"]["type"] == "emu" and re.search(r"shadps4", os.path.basename(g["launch"]["emu"]), re.I):
            more = " and its update" if any(i["kind"] == "update" for i in extras) else ""
            g["launch"] = {"type": "none", "message": f"{g['title']} is still a .pkg installer. shadPS4 plays installed games: install the "
                           f".pkg{more} with shadPS4's launcher into a folder inside {lib['path']}, and it shows up here ready to play."}
        out.append(g)
    return out


def ps5_content_id(folder):
    try:
        with open(os.path.join(folder, "sce_sys", "param.json"), encoding="utf-8-sig") as f:
            return json.load(f).get("contentId", "")
    except (OSError, ValueError, AttributeError):
        return ""


def ps5_title(folder):
    """A PS5 dump's own name from sce_sys/param.json, for dumps whose folder is only an id like PPSA01317."""
    try:
        with open(os.path.join(folder, "sce_sys", "param.json"), encoding="utf-8-sig") as f:
            loc = json.load(f).get("localizedParameters") or {}
        names = loc.get(loc.get("defaultLanguage", "en-US")) or loc.get("en-US") or next((v for v in loc.values() if isinstance(v, dict)), {})
        return (names.get("titleName") or "").replace("™", "").replace("®", "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def rom_title(stem, system):
    """A ROM's display name: no region tags, no console name, and PlayStation package ids turned into the game's label."""
    m = re.fullmatch(r"[A-Z]{2}\d{4}-[A-Z]{4}\d{5}_\d\d-([A-Z0-9]+?)0*(?:-[A-Z0-9]+)?(?:_\d+)?", stem.strip(), re.I)
    if m:  # JP9001-PPSA01315_00-GRANTURISMO70000 -> Granturismo 7
        stem = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", m.group(1).title())
    t = clean_title(stem)
    t = re.sub(r"^(.+?),? The(?= - |$)", r"The \1", t)  # No-Intro's "Legend of Zelda, The - ..." -> "The Legend of Zelda - ..."
    pat = next((p for p, name, *_ in SYSTEMS if name == system), None)
    for rx in (rf"^(?P<t>.+?)[\s\-–:]+(?P<tag>{SYSTEM_TAGS})$", rf"^(?P<tag>{SYSTEM_TAGS})[\s\-–:]+(?P<t>.+)$"):
        m = re.match(rx, t, re.I)
        if pat and m and re.search(pat, m["tag"], re.I):  # only the game's own console: "Pokemon Ruby GBA" in GBA/
            t = m["t"].strip(" -–:")
    return t or stem


# Folders a game's program sits in that say nothing about the game (007 First Light keeps its exe in Retail\, Hades II in Ship\)
GENERIC_DIRS = re.compile(r"bin(32|64)?|binaries|win(32|64|dows)?|(x(64|86)|amd64)([ _-]?(dx\d+|vk|vulkan))?|release|retail|final|gold|live|"
                          r"ship(ping)?|game|client|build(s)?|exe|app|program|data|pc|dx(9|11|12)|vulkan|windowsnoeditor|windowsclient|"
                          r"steam|gog|epic|current|latest|default|main|launcher|public|ptr|beta", re.I)
# Folders that hold many games: a game named after one of them is named after nothing
SHELF_DIRS = re.compile(r"games?|pc ?games|my games|pc ports|ports|common|steamapps|steamlibrary|program files( \(x86\))?|"
                        r"epic games|gog games|apps|software|downloads|desktop", re.I)


def exe_name_title(exe):
    """A game's name from its program's: "007FirstLight-Win64-Shipping.exe" -> "007 First Light"."""
    stem = os.path.splitext(os.path.basename(exe))[0]
    stem = re.sub(r"[-_ ](win(32|64)|x(64|86)|shipping|dx\d+|vk|steam|gog|epic|release|retail)\b.*$", "", stem, flags=re.I)
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z]{2})", " ", stem)  # FirstLight -> First Light
    return clean_title(stem.replace("-", " ").replace("_", " "))


def title_for_exe(exe):
    """Name a game after its folder, skipping generic ones (bin, Win64, Retail...). Unreal Engine games keep their
    program in <game>/<project>/Binaries/Win64, where the project folder is often a code name: the game's folder above
    it names it. A folder that's still no name (a drive, a folder of many games) gives way to the program's own name."""
    d, skipped = os.path.dirname(exe), []
    while GENERIC_DIRS.fullmatch(os.path.basename(d)) and os.path.dirname(d) != d:
        skipped.append(os.path.basename(d).lower())
        d = os.path.dirname(d)
    if "binaries" in skipped:  # Unreal Engine: d is the project folder; its parent is the game's own
        parent = os.path.dirname(d)
        if parent != d and os.path.dirname(parent) != parent and not SHELF_DIRS.fullmatch(os.path.basename(parent)):
            d = parent
    name = os.path.basename(d)
    if not name or os.path.dirname(d) == d or SHELF_DIRS.fullmatch(name) or GENERIC_DIRS.fullmatch(name):
        return exe_name_title(exe) or clean_title(name)
    return clean_title(name)


def exe_game(title, exe, group, cfg, folder=None):
    folder = folder or os.path.dirname(exe)
    gid_ = gid("pc", exe)
    img = find_image([folder, os.path.dirname(exe)], {"cover", "boxart", "folder", "poster", "library_600x900", title, os.path.basename(folder)})
    cover = local_art(gid_, img) if img else (online_cover(title) if cfg["onlineCovers"] else "")
    return {"id": gid_, "title": title, "group": group, "source": group, "installed": True, "minutes": 0, "lastPlayed": 0,
            "cover": cover, "launch": {"type": "exe", "exe": exe, "args": []}}


def folder_game(title, folder, group):
    """A folder that isn't a game (Apps, Movies...): Play opens it in File Explorer. Its own picture if it has one, never
    one looked up online by a name like "Apps"."""
    gid_ = gid("folder", folder)
    img = find_image([folder], {"cover", "folder", "poster", title})
    return {"id": gid_, "title": title, "group": group, "source": group, "installed": True, "minutes": 0, "lastPlayed": 0,
            "cover": local_art(gid_, img) if img else "", "isFolder": True, "launch": {"type": "uri", "uri": folder}}


# Switch games kept as folders, in the layouts Eglantine finds: <game>/exefs/main, or <game>/base/exefs/main with each update
# in <game>/updates/<version>/exefs/main. An update folder holds the whole updated game, so the newest one is what plays.
def switch_dump(folder):
    def exefs(d):
        main = os.path.join(d, "exefs", "main")
        return main if os.path.isfile(main) and os.path.isfile(main + ".npdm") else None
    for content in (folder, os.path.join(folder, "base")):
        try:
            versions = os.listdir(os.path.join(content, "updates"))
        except OSError:
            continue
        for v in sorted(versions, key=lambda v: int(v) if v.isdigit() else -1, reverse=True):
            main = exefs(os.path.join(content, "updates", v))
            if main:
                return main
    return exefs(folder) or exefs(os.path.join(folder, "base"))


def file_added(path):
    """When a game's file or folder arrived on this PC (its creation time on Windows), so new games can show first."""
    try:
        return int(os.path.getctime(path))
    except OSError:
        return 0


def npdm_title_id(path):
    """The program id in a main.npdm (its ACI0 section), written the way Eglantine shows it: 0400C3F00006E000."""
    try:
        with open(path, "rb") as f:
            b = f.read(1 << 16)
        off = struct.unpack_from("<I", b, 0x70)[0]
        return "%016X" % struct.unpack_from("<Q", b, off + 0x10)[0] if b[off:off + 4] == b"ACI0" else ""
    except (OSError, struct.error):
        return ""


# A game folder has no name inside it, so it's named after the folder. data/switch-titles.json can name one by its title id
# instead ({"0100...": "Full Title"}), for folders with shorthand names.
def switch_titles():
    try:
        return load("switch-titles.json", {})
    except ValueError:
        return {}


# ---------- shortcuts in a games folder (.lnk and .url): each one is a game ----------
LNK_CACHE = {}  # (path, modified) -> {"target", "args", "dir"}
LNK_SCRIPT = r"""
$paths = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{paths}')) | ConvertFrom-Json
$sh = New-Object -ComObject WScript.Shell
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$out = @{}
foreach ($p in $paths) { try { $l = $sh.CreateShortcut($p); $out[$p] = @{ target = $l.TargetPath; args = $l.Arguments; dir = $l.WorkingDirectory } } catch {} }
$out | ConvertTo-Json -Compress
"""


def shortcut_targets(paths):
    """What Windows shortcuts (.lnk) point at: {path: {"target", "args", "dir"}}. Read through Windows' own shortcut
    object, all of a folder's at once, and kept until a shortcut changes."""
    def stamp(p):
        try:
            return os.path.getmtime(p)
        except OSError:  # gone since the folder was listed
            return None
    todo = [p for p in paths if stamp(p) is not None and (p, stamp(p)) not in LNK_CACHE]
    for i in range(0, len(todo) if WIN else 0, 40):  # 40 at a time: the paths travel on PowerShell's command line
        batch = todo[i:i + 40]
        code = LNK_SCRIPT.replace("{paths}", base64.b64encode(json.dumps(batch).encode("utf-8")).decode())
        try:
            r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(code.encode("utf-16-le")).decode()],
                               capture_output=True, timeout=60)
            found = json.loads(r.stdout.decode("utf-8", "replace").strip()) if r.returncode == 0 and r.stdout.strip() else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            found = None
        if isinstance(found, dict):  # a failed read is tried again at the next scan, not remembered as "nothing"
            for p in batch:
                LNK_CACHE[(p, stamp(p))] = found.get(p) or {}
    return {p: LNK_CACHE.get((p, stamp(p)), {}) for p in paths}


def command_args(text):
    """A shortcut's arguments split the way Windows splits a command line."""
    if not text.strip():
        return []
    import ctypes
    shell, k32 = ctypes.WinDLL("shell32"), ctypes.WinDLL("kernel32")
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    n = ctypes.c_int()
    argv = shell.CommandLineToArgvW("x " + text, ctypes.byref(n))  # a program name first, so the arguments are parsed as arguments
    try:
        return [argv[i] for i in range(1, n.value)]
    finally:
        k32.LocalFree(argv)


def url_of(path):
    """The address in an internet shortcut (.url)."""
    try:
        m = re.search(r"^\s*URL\s*=\s*(\S.*?)\s*$", read(path), re.M | re.I)
    except OSError:
        return ""
    return m.group(1) if m else ""


def shortcut_games(folder, group, cfg):
    """The shortcuts directly in a games folder, as games. One to a game's program starts that program (so it's followed
    while it runs); a Steam shortcut is that Steam game; anything else opens the way double-clicking it would."""
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".lnk", ".url")) and os.path.isfile(os.path.join(folder, f)))
    links = shortcut_targets([os.path.join(folder, f) for f in files if f.lower().endswith(".lnk")])
    games, windows = [], os.path.normcase(os.environ.get("SystemRoot") or r"C:\Windows") + os.sep
    for f in files:
        path, title = os.path.join(folder, f), clean_title(os.path.splitext(f)[0])
        link = links.get(path) or {}
        target = url_of(path) if f.lower().endswith(".url") else link.get("target") or ""
        steam = (re.match(r"steam://(?:rungameid|run)/(\d+)", target, re.I)
                 or os.path.basename(target).lower() == "steam.exe" and re.search(r"(?:^|\s)-applaunch\s+(\d+)", link.get("args") or ""))
        if steam and int(steam.group(1)) < 2 ** 32:  # (a bigger number is a non-Steam game Steam made a shortcut for)
            g = steam_game(steam.group(1), title, True)
        elif target.lower().endswith(".exe") and os.path.isfile(target) and not os.path.normcase(target).startswith(windows):
            # (not Windows' own programs: their folder would make every program there count as this game)
            g = exe_game(title, target, group, cfg, os.path.dirname(target))
            g["id"] = gid("lnk", path)
            g["launch"]["args"] = command_args(link.get("args") or "")
            if link.get("dir") and os.path.isdir(link["dir"]):  # the shortcut's "Start in": some games need it
                g["launch"]["cwd"] = link["dir"]
            if g["launch"]["args"]:  # an emulator or launcher given a game: its folder says nothing about which game is running
                g["launch"]["noFolder"] = True
        elif target:
            folder_of = os.path.dirname(target) if os.path.isfile(target) and not os.path.normcase(target).startswith(windows) else None
            img = find_image([folder_of], {"cover", "boxart", "poster", title}) if folder_of else None
            g_id = gid("lnk", path)
            g = {"id": g_id, "title": title, "group": group, "source": group, "installed": True, "minutes": 0, "lastPlayed": 0,
                 "cover": local_art(g_id, img) if img else (online_cover(title) if cfg["onlineCovers"] else ""),
                 "launch": {"type": "uri", "uri": path}}
            if folder_of and len(folder_of) > 12:  # never a whole drive or Windows itself
                g["folder"] = folder_of
        else:
            continue
        g["shortcut"] = path
        games.append(g)
    return games


def scan_library(lib, cfg):
    path, kind = lib["path"], lib["type"]
    if kind == "game":
        if not (os.path.isfile(path) or MAC and path.rstrip("/").endswith(".app") and os.path.isdir(path)):
            return []
        title = lib.get("title") or ""
        if not title or GENERIC_DIRS.fullmatch(title) or SHELF_DIRS.fullmatch(title):  # a name kept from before folders like Retail were skipped
            title = title_for_exe(path)
        g = exe_game(title, path, lib["name"], cfg)
        if lib.get("args"):
            g["launch"]["args"] = list(lib["args"])
        if lib.get("system"):  # an emulator set up for one game (PlayStation Home in its own RPCS3): listed with that console
            g.update({"id": gid("rom", " ".join([path, *(lib.get("args") or [])])), "source": "Emulators", "system": lib["system"], "group": lib["system"]})
        return [g]
    if kind == "folder":  # a folder of anything, added as one tile: Play opens it
        if not os.path.isdir(path):
            return []
        return [folder_game(lib.get("title") or os.path.basename(path.rstrip("\\/")) or path, path, lib["name"])]
    if not os.path.isdir(path):
        raise FileNotFoundError(f"{path} isn't available")
    if kind == "pc" and MAC:
        games = []
        for sub in sorted(os.listdir(path)):
            full = os.path.join(path, sub)
            app = full if sub.lower().endswith(".app") else os.path.isdir(full) and best_app(full)
            if app:
                games.append(exe_game(clean_title(os.path.splitext(sub)[0] if sub.lower().endswith(".app") else sub), app, lib["name"], cfg,
                                      None if app == full else full))
        return games
    if kind == "pc":
        games = []
        for sub in sorted(os.listdir(path)):
            full = os.path.join(path, sub)
            if os.path.isdir(full) and SHELF_DIRS.fullmatch(sub):  # "Apps", "Software": a folder of things, not a game
                games.append(folder_game(sub, full, lib["name"]))
                continue
            exe = os.path.isdir(full) and best_exe(full)
            if exe:
                games.append(exe_game(clean_title(sub), exe, lib["name"], cfg, full))
        if WIN:  # and the shortcuts in it: a folder of shortcuts is a common way to keep games together
            games += shortcut_games(path, lib["name"], cfg)
        return games
    # ROM folder
    known = (system_info(lib.get("system") or lib["name"]) or {}).get("exts") or []  # types added since the library was saved
    order = [e for e in dict.fromkeys((lib.get("exts") or []) + known) if e not in ARCHIVES]  # the console's own types, best first
    exts = set(order) | set(ARCHIVES) if lib.get("exts") else set()     # (arcade games are only archives)
    by_name = {e for e in exts if not e.startswith(".")}   # whole file names, e.g. eboot.bin for folder games
    max_depth = 4 if by_name else 2                          # PS3 keeps EBOOT.BIN in Game/PS3_GAME/USRDIR/
    files, dumps = [], {}
    if lib["name"] in FOLDER_GAMES:  # DOS / ScummVM: each folder is a game
        for sub in sorted(os.listdir(path)):
            full = os.path.join(path, sub)
            if not os.path.isdir(full) or sub.lower() in ("bios", "media", "covers", "boxart", "images", "saves"):
                continue
            main = full if lib["name"] == "ScummVM" else best_exe(full, (".exe", ".com", ".bat"))
            if main:
                files.append(main)
                dumps[main] = full
    for dirpath, dirs, names in [] if lib["name"] in FOLDER_GAMES else os.walk(path):
        dirs[:] = [d for d in dirs if d.lower() not in ("media", "covers", "boxart", "images", "screenshots", "saves", "states")
                   and not (dirpath == path and d.lower() == "bios")]  # the console's BIOS folder (Settings > Systems) holds no games
        main = lib["name"] in ("Switch", "Switch 2") and switch_dump(dirpath)
        if main:  # a game kept as a folder: one game, and nothing further inside to look through
            files.append(main)
            dumps[main] = dirpath
            dirs[:] = []
            continue
        if dirpath.count(os.sep) - path.rstrip("\\/").count(os.sep) >= max_depth:
            dirs[:] = []
        listed = {n.lower() for n in names}
        for n in names:
            ext = os.path.splitext(n)[1].lower()
            if re.match(r"\[?bios\b", n, re.I):  # console BIOS/firmware dumps kept beside the games aren't games
                continue
            if n.lower() in by_name or ((ext in exts) if exts else (ext not in NOT_ROM and not n.startswith("."))):
                # skip discs that a playlist (.m3u) or .cue already covers
                if ext in (".cue", ".chd", ".bin") and any(x.endswith(".m3u") for x in listed) and ".m3u" in exts:
                    continue
                files.append(os.path.join(dirpath, n))
    games, pkgs, tids, cids = [], {}, {}, {}
    names = {os.path.basename(f).lower() for f in files}
    for f in sorted(files):
        stem = os.path.splitext(os.path.basename(f))[0]
        disc = re.search(r"\(disc ?(\d+)\)", os.path.basename(f), re.I)
        if disc and int(disc.group(1)) > 1 and re.sub(r"\(disc ?\d+\)", "(Disc 1)", os.path.basename(f), flags=re.I).lower() in names:
            continue  # later discs are changed from the emulator's own menu
        if f in dumps and lib["name"] in FOLDER_GAMES:
            stem = os.path.basename(dumps[f])
        elif f in dumps:  # Switch game folder
            stem = switch_titles().get(npdm_title_id(f + ".npdm")) or re.sub(r"\s+(rom|dump)$", "", os.path.basename(dumps[f]), flags=re.I)
        elif lib["name"] in ("Switch", "Switch 2") and re.search(r"\[[0-9a-f]{16}\]", stem, re.I):  # "Game [0100...].nup"
            tid = re.search(r"\[([0-9a-f]{16})\]", stem, re.I).group(1).upper()
            stem = switch_titles().get(tid) or stem
        elif os.path.basename(f).lower() in by_name:  # folder game: name it after its folder, not "EBOOT"
            d = os.path.dirname(f)
            while os.path.basename(d).lower() in ("usrdir", "ps3_game", "sce_sys", "app", "eboot", "uroot") and os.path.dirname(d) != d:  # uroot: PkgTool's PFS root
                d = os.path.dirname(d)
            if re.search(r"-(update|patch)$", os.path.basename(d), re.I):
                continue  # shadPS4 keeps a game's patch beside it as "<game>-UPDATE"
            sfo = {}
            try:
                with open(os.path.join(d, "sce_sys", "param.sfo"), "rb") as fh:
                    sfo = read_sfo(fh.read(1 << 20))
            except OSError:
                pass
            stem = ps5_title(d) or re.sub(r"\s+", " ", re.sub(r"[™®©]", " ", sfo.get("TITLE", ""))).strip() or os.path.basename(d)  # "Gran Turismo®SPORT"
            if sfo.get("TITLE_ID"):
                tids[f] = sfo["TITLE_ID"]
            content = sfo.get("CONTENT_ID") or ps5_content_id(d)
            if content:
                cids[f] = content
        gid_ = gid("rom", dumps.get(f, f))  # a game folder keeps its id, and so its playtime and art, when a newer update arrives
        d = dumps.get(f) or os.path.dirname(f)
        img = find_image([d, os.path.join(d, "covers"), os.path.join(d, "boxart"), os.path.join(d, "media", "covers"), os.path.join(d, "images")], {stem})
        cover, fallback = (local_art(gid_, img) if img else ""), ""
        if not cover and cfg["onlineCovers"] and lib.get("thumbs"):
            # libretro box art only matches No-Intro file names, so it's used after SteamGridDB (see scan)
            safe = re.sub(r'[&*/:`<>?\\|"]', "_", stem)
            fallback = f"https://thumbnails.libretro.com/{urllib.parse.quote(lib['thumbs'])}/Named_Boxarts/{urllib.parse.quote(safe)}.png"
        launch = ({"type": "emu", "emu": lib["emulator"], "args": lib.get("args") or ["{rom}"], "rom": f, "exts": order, "romdir": path} if lib.get("emulator")
                  else {"type": "none", "message": f"Choose an emulator for {lib['name']} in Settings › Systems"})
        if by_name and f.lower().endswith(".zip"):  # PS3/4/5 archive: is there a game the emulator can load inside?
            names = zip_names(f)
            if names is not None and not any(n == e or n.endswith(e) for n in names for e in order):
                launch = {"type": "none", "message": f"There's no playable game in this archive. {lib['name']} needs a game dump: "
                          f"a folder with eboot.bin{' or a .zar file' if '.zar' in order else ''}"
                          f"{'. Encrypted .pkg install files can’t be played' if any(n.endswith('.pkg') for n in names) else ''}."}
        info = ps4_pkg(f) if f.lower().endswith(".pkg") else None
        if info:
            pkgs[gid_] = info
            if info["kind"] != "add-on" and info.get("content"):
                cids[f] = info["content"]
        if info and info["kind"] != "add-on":
            stem = info["title"] or scene_title(stem)
        games.append({"id": gid_, "title": rom_title(stem, lib["name"]), "group": lib["name"], "source": "Emulators", "system": lib["name"],
                      "installed": True, "minutes": 0, "lastPlayed": 0, "added": file_added(dumps.get(f) or f), "cover": cover,
                      "fallbackCover": fallback, "launch": launch,
                      **({"titleId": tids[f]} if f in tids else {}), **({"contentId": cids[f]} if f in cids else {}),
                      **({"_file": f} if info else {})})
    games = ps4_group(games, pkgs, lib) if pkgs else games
    for g in games:
        g.pop("_file", None)
    return games


# ---------------------------------------------------------------- SteamGridDB (artwork)
SGDB = "https://www.steamgriddb.com/api/v2"
SGDB_KEY_PAGE = "https://www.steamgriddb.com/profile/preferences/api"
GRID_DIMS = "600x900,342x482,660x930"  # tall covers only
ART_DIR = os.path.join(DATA, "art")


def sgdb(path, key, **params):
    url = SGDB + path + ("?" + urllib.parse.urlencode(params) if params else "")
    r = http_json(url, headers={"Authorization": f"Bearer {key}"})
    if r.get("success") is False:
        raise ValueError("SteamGridDB: " + "; ".join(r.get("errors") or ["request failed"]))
    return r.get("data")


def sgdb_search(key, term):
    hits = sgdb("/search/autocomplete/" + urllib.parse.quote(term, safe=""), key) or []
    return [{"id": h["id"], "name": h["name"], "year": time.gmtime(h["release_date"]).tm_year if h.get("release_date") else None}
            for h in hits[:6]]


def sgdb_game_for(key, game):
    if game.get("appid"):
        try:
            d = sgdb(f"/games/steam/{game['appid']}", key)
            return {"id": d["id"], "name": d["name"], "year": None}
        except (urllib.error.HTTPError, KeyError, TypeError, ValueError):
            pass
    known = known_game_info(game) if game.get("source") == "Emulators" else {}
    if known.get("sgdbId"):
        return {"id": known["sgdbId"], "name": known["title"], "year": int(known["released"])}
    # The top search hit can be another game ("Nintendo Switch Sports" for "Nintendo Switch Sports Resort"), whose art would
    # then show this game as that one: only a hit with every word of the title counts.
    words = title_words(game["title"])
    return next((h for h in sgdb_search(key, game["title"]) if words <= title_words(h["name"])), None)


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}


def title_words(title):
    """A title's words for telling games apart: accents, apostrophes and little words dropped, numerals as digits, so
    "The Legend of Zelda - Majora's Mask" and "Legend of Zelda: Majoras Mask" have the same words."""
    import unicodedata
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower().replace("'", "")
    return {ROMAN.get(w, w) for w in re.findall(r"[a-z0-9]+", plain)} - {"the", "a", "an", "of", "and"}


def sgdb_grids(key, sgdb_id, kind="cover"):
    """Tall covers, or wide hero images for the details screen background. Covers and backgrounds come animated too
    (animated WebP or PNG): those first, marked, and never ones flagged as flashing (epilepsy)."""
    if kind == "logo":
        data = [(d, False) for d in (sgdb(f"/logos/game/{sgdb_id}", key, types="static", nsfw="false") or [])]
    else:
        path, extra = (f"/heroes/game/{sgdb_id}", {}) if kind == "hero" else (f"/grids/game/{sgdb_id}", {"dimensions": GRID_DIMS})
        data = []
        for animated in (True, False):
            try:
                found = sgdb(path, key, types="animated" if animated else "static", nsfw="false",
                             **({"epilepsy": "false"} if animated else {}), **extra) or []
            except (urllib.error.HTTPError, ValueError):  # no animated art for this game: the still ones still show
                if not animated:
                    raise
                found = []
            data += [(d, animated) for d in found if not (animated and d.get("epilepsy"))][:30 if animated else 60]
    return [{"thumb": d.get("thumb") or d["url"], "url": d["url"], "author": (d.get("author") or {}).get("name"), "animated": animated}
            for d, animated in data[:80]]


def safe_name(game_id):
    return re.sub(r"[^A-Za-z0-9_-]", "_", game_id)


def set_art(game_id, url, kind="cover"):
    host = urllib.parse.urlparse(url).hostname or ""
    if urllib.parse.urlparse(url).scheme != "https" or not (host == "steamgriddb.com" or host.endswith(".steamgriddb.com")
                                                             or host == "thumbnails.libretro.com"):
        raise ValueError("Artwork must come from SteamGridDB or libretro")
    limit = 60 * 1024 * 1024  # animated covers and backgrounds run to tens of megabytes
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
        data = r.read(limit + 1)
        ctype = (r.headers.get("Content-Type") or "").split(";")[0]
    if len(data) > limit or not ctype.startswith("image/"):
        raise ValueError("That artwork couldn't be downloaded")
    os.makedirs(ART_DIR, exist_ok=True)
    stem = safe_name(game_id) + ("-" + kind if kind in ("hero", "logo") else "")
    for old in glob.glob(os.path.join(ART_DIR, stem + ".*")) + glob.glob(os.path.join(ART_DIR, stem + "-still.*")):
        os.remove(old)
    name = stem + {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(ctype, ".jpg")
    with open(os.path.join(ART_DIR, name), "wb") as f:
        f.write(data)
    overrides = load("overrides.json", {})
    o = overrides.setdefault(game_id, {})
    o[kind if kind in ("hero", "logo") else "cover"] = name
    if kind not in ("hero", "logo"):
        still = still_frame(os.path.join(ART_DIR, name))
        if still:
            o["coverStill"] = os.path.basename(still)
        else:
            o.pop("coverStill", None)
    store("overrides.json", overrides)
    DETAILS.pop(game_id, None)
    HEROES.pop(game_id, None)


def still_frame(path):
    """An animated cover's first frame, saved beside it: the row shows that and plays the animation only on the selected
    cover, so a row of animated covers doesn't keep a handheld busy. None for a still image."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            if not getattr(im, "is_animated", False):
                return None
            im.seek(0)
            out = os.path.splitext(path)[0] + "-still.png"
            im.convert("RGBA").save(out)
            return out
    except Exception:
        return None


def reset_art(game_id, kind="cover"):
    overrides = load("overrides.json", {})
    o = overrides.get(game_id, {})
    name = o.pop(kind if kind in ("hero", "logo") else "cover", None)
    for old in [name, o.pop("coverStill", None) if kind not in ("hero", "logo") else None]:
        if not old:
            continue
        try:
            os.remove(os.path.join(ART_DIR, old))
        except OSError:
            pass
    if not o:
        overrides.pop(game_id, None)
    store("overrides.json", overrides)
    DETAILS.pop(game_id, None)
    HEROES.pop(game_id, None)


def sgdb_fill_missing(key, games):
    """Give games without any cover the top SteamGridDB grid (cached by title; a few new lookups per scan)."""
    cache, changed, lookups = load("sgdb-cache.json", {}), False, 0
    for g in games:
        if g["cover"] or g.get("isFolder"):  # (a folder tile named "Movies" isn't a game called Movies)
            continue
        k = norm(g["title"])
        if k not in cache:
            if lookups >= 40:
                continue
            lookups += 1
            try:
                hit = sgdb_game_for(key, g)
                grids = sgdb_grids(key, hit["id"]) if hit else []
                cache[k] = grids[0]["url"] if grids else ""
                changed = True
            except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
                continue
        g["cover"] = cache[k]
    if changed:
        store("sgdb-cache.json", cache)


# ---------------------------------------------------------------- game details (news, store info, hero art)
DETAILS = {}      # game id -> (time, details); news refreshes after 30 minutes
DETAIL_ART = {}   # local hero/logo files, kept across rescans


def steam_appid_for(game):
    """The game's Steam app id, or for non-Steam games a Steam store match by exact name (cached)."""
    if game.get("appid"):
        return game["appid"]
    cache, key = load("appid-cache.json", {}), norm(game["title"])
    if key not in cache:
        try:
            items = http_json("https://store.steampowered.com/api/storesearch/?" + urllib.parse.urlencode({"term": game["title"], "l": "english", "cc": "US"}), timeout=6).get("items", [])
        except (urllib.error.URLError, ValueError, TimeoutError):
            return None
        hit = next((i for i in items if norm(i["name"]) == key), None)
        cache[key] = str(hit["id"]) if hit else ""
        store("appid-cache.json", cache)
    return cache[key] or None


def tidy(t):
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([:;,.!?])", r"\1", t)          # tags removed next to punctuation leave stray spaces
    return re.sub(r"([.!?])(?=[A-Z])", r"\1 ", t).strip()  # paragraphs that lost their breaks


CLAN_IMG = "https://clan.akamai.steamstatic.com/images"
# Any BBCode tag, with or without attributes: [b], [/url], [url=...], [dynamiclink href="..."], [expand type="details"]
BBCODE_TAG = r"\[/?(?:[a-z][a-z0-9_*]*|\*)(?:[ =][^\]]*)?\]"  # any tag, with or without attributes; also list items [*] [/*]


def news_blocks(raw):
    """Turn a Steam post (BBCode and/or HTML) into plain blocks the UI renders itself: no markup from Steam reaches the page."""
    t = raw.replace("{STEAM_CLAN_IMAGE}", CLAN_IMG)
    t = re.sub(r"\[img(?:\s+src=[\"']?([^\"'\]\s]+)[\"']?)?[^\]]*\](.*?)\[/img\]", lambda m: f"\n\x00IMG\x00{(m.group(1) or m.group(2)).strip()}\n", t, flags=re.I | re.S)
    t = re.sub(r"<img[^>]+src=[\"']([^\"']+)[\"'][^>]*>", lambda m: f"\n\x00IMG\x00{m.group(1)}\n", t, flags=re.I)
    t = re.sub(r"\[previewyoutube=([\w-]{6,})[^\]]*\].*?\[/previewyoutube\]", lambda m: f"\n\x00IMG\x00https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg\n", t, flags=re.I | re.S)
    t = re.sub(r"\[h[1-6]\](.*?)\[/h[1-6]\]|<h[1-6][^>]*>(.*?)</h[1-6]>", lambda m: f"\n\x00H\x00{m.group(1) or m.group(2)}\n", t, flags=re.I | re.S)
    # A list item runs from [*] to its [/*] (or the next item, or the list's end). Newer posts wrap each item's text in
    # [p]...[/p], which used to split it off as a plain paragraph and leave "[/*]" showing.
    t = re.sub(r"\[\*\](.*?)(?=\[/\*\]|\[\*\]|\[/o?list\]|$)",
               lambda m: "\n\x00LI\x00" + " ".join(re.sub(r"\[/?p\]", " ", m.group(1), flags=re.I).split()) + "\n", t, flags=re.I | re.S)
    t = re.sub(r"\[/\*\]", "", t)
    t = re.sub(r"<li[^>]*>", "\n\x00LI\x00", t, flags=re.I)
    t = re.sub(r"\[/?(p|list|olist|hr|br|quote|table|tr|td|th)[^\]]*\]|</?(p|ul|ol|li|br|hr|div|blockquote|tr|td|table)[^>]*>", "\n", t, flags=re.I)
    t = re.sub(BBCODE_TAG + r"|<[^>]+>", "", t, flags=re.I)
    blocks = []
    for line in html.unescape(t).split("\n"):
        kind, _, rest = line.strip().partition("\x00") if line.strip().startswith("\x00") else ("", "", line)
        if line.strip().startswith("\x00"):
            kind, _, rest = line.strip()[1:].partition("\x00")
        if kind == "IMG":
            if rest.startswith("https://"):
                blocks.append({"t": "img", "src": rest})
        elif tidy(rest):
            blocks.append({"t": {"H": "h", "LI": "li"}.get(kind, "p"), "text": tidy(rest)})
    return blocks[:150]


def news_text(raw):
    t = re.sub(r"\[img[^\]]*\].*?\[/img\]|\{STEAM_CLAN_IMAGE\}\S*|" + BBCODE_TAG + r"|<[^>]+>", " ", raw, flags=re.I | re.S)
    t = re.sub(r"https?://\S+", "", html.unescape(t))
    t = tidy(t)
    return t[:280] + ("…" if len(t) > 280 else "")


def news_image(raw):
    """First picture in a Steam news post (or its YouTube thumbnail)."""
    raw = raw.replace("{STEAM_CLAN_IMAGE}", "https://clan.akamai.steamstatic.com/images")
    m = (re.search(r"\[img[^\]]*\]\s*(https://[^\s\[]+?)\s*\[/img\]", raw, re.I) or re.search(r"<img[^>]+src=[\"'](https://[^\"']+)", raw, re.I)
         or re.search(r"(https://clan\.akamai\.steamstatic\.com/images/\S+?\.(?:jpe?g|png|gif|webp))", raw, re.I))
    if m:
        return html.unescape(m.group(1))
    yt = re.search(r"\[previewyoutube=([\w-]{6,});", raw)
    return f"https://i.ytimg.com/vi/{yt.group(1)}/hqdefault.jpg" if yt else ""


def steam_news(appid):
    def fetch(**extra):
        q = urllib.parse.urlencode({"appid": appid, "count": 12, "maxlength": 0, "format": "json", **extra})
        return http_json("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?" + q, timeout=8)["appnews"].get("newsitems", [])
    items = fetch(feeds="steam_community_announcements") or [n for n in fetch() if re.fullmatch(r"[\x20-\x7e‘-”–—…]+", n.get("title", ""))]
    return [{"title": html.unescape(n["title"]), "url": n["url"], "date": n["date"], "source": n.get("feedlabel") or "",
             "summary": news_text(n.get("contents", "")), "image": news_image(n.get("contents", "")), "body": news_blocks(n.get("contents", ""))}
            for n in items[:10] if n.get("url", "").startswith("https://")]


REMOTE_OK = {}


def remote_ok(url):
    """Does this image URL exist? Older Steam games have no library logo/hero at the usual address."""
    if not url.startswith("https://"):
        return bool(url)
    if url not in REMOTE_OK:
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=6) as r:
                REMOTE_OK[url] = r.status == 200 and (r.headers.get("Content-Type") or "").startswith("image/")
        except (urllib.error.URLError, TimeoutError, ValueError):
            REMOTE_OK[url] = False
    return REMOTE_OK[url]


WIKI_UA = {"User-Agent": "GameFrontend/0.1 (personal game launcher)"}


def wiki_match_rank(page, game):
    """How well a Wikipedia article title matches a game name (lower is better, None = not this game).
    Compares names, not keywords, so "GRID" doesn't match "Off the Grid"."""
    def simple(s):
        s = re.sub(r"\s*\([^)]*\)", "", re.sub(r"[™®©]", "", s)).lower()
        return re.sub(r"[^a-z0-9:]+", " ", s).strip()
    p, g = simple(page), simple(game)  # "Rust - Staging Branch" -> "Rust"
    flat = lambda s: " ".join(s.replace(":", " ").split())
    dated = bool(re.search(r"\(\d{4}[^)]*\)", page))           # "Grid (2019 video game)": maybe another game of that name
    if flat(p) == flat(g):
        return 2 if dated else 0
    if p.endswith(": " + g):                                     # "Race Driver: Grid" ~ "GRID"
        return 1
    if flat(p).startswith(flat(g) + " and "):                    # "Pokémon Black" ~ "Pokémon Black and White"
        return 2
    base = simple(re.split(r"\s+-\s+", game)[0])
    if base != g and len(base) >= 4 and flat(p) == flat(base) and not re.search(r"series|franchise", page, re.I):
        return 3                                                 # "Donkey Kong Country 2 - Diddy's Kong Quest" ~ "Donkey Kong Country 2"
    return None


def wiki_title_matches(page, game):
    return wiki_match_rank(page, game) is not None


def wiki_summary(title):
    """Last-resort game description from Wikipedia, for delisted or non-Steam games (cached)."""
    cache, key = load("wiki-cache.json", {}), norm(title)
    if key not in cache:
        clean = re.split(r"\s+-\s+", re.sub(r"\s*\([^)]*\)", "", re.sub(r"[™®©]", "", title)))[0].strip()
        text = ""
        try:
            q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": f"{clean} video game", "srlimit": 6, "format": "json"})
            hits = http_json("https://en.wikipedia.org/w/api.php?" + q, headers=WIKI_UA, timeout=6)["query"]["search"]
            ranked = sorted(((wiki_match_rank(h["title"], title), i, h) for i, h in enumerate(hits)), key=lambda x: (x[0] is None, x[0] or 0, x[1]))
            for rank, _, h in ranked:
                if rank is None:
                    break
                s = http_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(h["title"].replace(" ", "_"), safe=""), headers=WIKI_UA, timeout=6)
                extract = s.get("extract", "")
                if s.get("type") == "standard" and "game" in extract.lower():
                    sentences = re.split(r"(?<=[.!?])\s+", extract)
                    text = ""
                    for sent in sentences:
                        if len(text) + len(sent) > 420 and text:
                            break
                        text = (text + " " + sent).strip()
                    break
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            return ""
        cache[key] = text
        store("wiki-cache.json", cache)
    return cache[key]


HEROES = {}  # game id -> wide background URL ("" when none), for the "game art" home background


def hero_for(g):
    """A wide background for a game, without the slower details lookup (news, store text)."""
    if g["id"] in HEROES:
        return HEROES[g["id"]]
    hit = DETAILS.get(g["id"])
    url = hit[1]["hero"] if hit else ""
    custom = load("overrides.json", {}).get(g["id"], {}).get("hero")
    if not url and custom and os.path.isfile(os.path.join(ART_DIR, custom)):
        url = detail_art(f"{safe_name(g['id'])}-customhero", os.path.join(ART_DIR, custom))
    if not url and g.get("appid"):
        sp = steam_path()
        hits = glob.glob(os.path.join(sp, "appcache", "librarycache", g["appid"], "*", "library_hero.jpg")) if sp else []
        if hits:
            url = detail_art(f"{safe_name(g['id'])}-hero", hits[0])
        else:
            try:  # Steam's store service knows the hashed hero path for newer games
                q = json.dumps({"ids": [{"appid": int(g["appid"])}], "context": {"language": "english", "country_code": "US"}, "data_request": {"include_assets": True}})
                item = http_json("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/?" + urllib.parse.urlencode({"input_json": q}), timeout=6)["response"]["store_items"][0]
                a = item.get("assets") or {}
                if a.get("asset_url_format") and a.get("library_hero"):
                    url = STEAM_ASSETS + a["asset_url_format"].replace("${FILENAME}", a.get("library_hero_2x") or a["library_hero"])
            except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError):
                pass
    if not url:
        url = (g.get("epic") or {}).get("hero", "")
    accounts = load("accounts.json", {})
    if not url and "sgdb" in accounts and not g.get("isFolder"):  # a folder tile has only the background you give it
        try:
            m = sgdb_game_for(accounts["sgdb"]["key"], g)
            heroes = sgdb(f"/heroes/game/{m['id']}", accounts["sgdb"]["key"], types="static", nsfw="false") if m else []
            url = heroes[0]["url"] if heroes else ""
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            pass
    HEROES[g["id"]] = url
    return url


# Wide art for the home background is kept on disk as a 2560px JPEG after its first use: a SteamGridDB background is
# often a several-MB PNG, which made the full-screen art slow to change.
HERO_IMG = os.path.join(DATA, "hero-img")
HERO_FETCHING, HERO_FETCH_LOCK = set(), threading.Lock()


HERO_STILLS = {}  # game id -> (the background's mtime, its still or None): whether a picked background is animated


def animated_hero(g):
    """A picked background that's animated: (its still first frame, the animation) as addresses, else ("", "").
    Scrolling the home row preloads the backgrounds either side; decoding tens of megabytes of animation for each of
    them made scrolling stall, so the row preloads and shows the still, and the page starts the animation once the
    selection rests on the game."""
    name = load("overrides.json", {}).get(g["id"], {}).get("hero")
    path = name and os.path.join(ART_DIR, name)
    if not path or not os.path.isfile(path):
        return "", ""
    mtime = os.path.getmtime(path)
    hit = HERO_STILLS.get(g["id"])
    if not hit or hit[0] != mtime:
        still = os.path.splitext(path)[0] + "-still.jpg"
        try:
            if not (os.path.isfile(still) and os.path.getmtime(still) >= mtime):
                from PIL import Image
                with Image.open(path) as im:
                    if not getattr(im, "is_animated", False):
                        still = None
                    else:
                        im.seek(0)
                        im.convert("RGB").save(still, "JPEG", quality=88)
        except Exception:
            still = None
        hit = HERO_STILLS[g["id"]] = (mtime, still)
    if not hit[1]:
        return "", ""
    key = safe_name(g["id"])
    return detail_art(f"{key}-customhero-still", hit[1]), detail_art(f"{key}-customhero", path)


def hero_local(g, url):
    """The local copy's address if it's ready; otherwise the original (and start saving a copy in the background)."""
    if not url.startswith("https://"):
        return url
    index = load(os.path.join("hero-img", "index.json"), {})
    path = os.path.join(HERO_IMG, safe_name(g["id"]) + ".jpg")
    if index.get(g["id"]) == url and os.path.isfile(path):
        return f"/api/heroimg?id={urllib.parse.quote(g['id'])}&v={int(os.path.getmtime(path))}"
    with HERO_FETCH_LOCK:
        if g["id"] in HERO_FETCHING:
            return url
        HERO_FETCHING.add(g["id"])

    def save():
        try:
            from io import BytesIO
            from PIL import Image
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                data = r.read(40 * 1024 * 1024)
            with Image.open(BytesIO(data)) as im:
                im.thumbnail((2560, 2560))
                os.makedirs(HERO_IMG, exist_ok=True)
                im.convert("RGB").save(path, "JPEG", quality=86)
            with HERO_FETCH_LOCK:
                index = load(os.path.join("hero-img", "index.json"), {})
                index[g["id"]] = url
                store(os.path.join("hero-img", "index.json"), index)
        except Exception:
            pass
        finally:
            with HERO_FETCH_LOCK:
                HERO_FETCHING.discard(g["id"])
    threading.Thread(target=save, daemon=True).start()
    return url


def metadata_title(title):
    title = re.sub(r"\s*\([^)]*\)|\s*\[[^]]*\]", "", title).strip()
    title = re.sub(r"[\s\-–:]+(nintendo\s+)?switch\s*2\s+edition\b.*$", "", title, flags=re.I) or title  # the game's own page
    title = re.sub(r"^(.+?) The - ", r"The \1: ", title)
    title = title.replace("Pokemon", "Pokémon")
    title = re.sub(r"^Pokémon\s*-\s*(.+?)(?: Version)?$", r"Pokémon \1", title)
    return title


def metadata_key(title):
    import unicodedata
    return norm(unicodedata.normalize("NFKD", metadata_title(title)).encode("ascii", "ignore").decode())


def known_game_info(g):
    """Hand-written details for a game the online sources get wrong: the list that ships, plus this copy's own data/games.json."""
    rows = []
    for path in (os.path.join(shipped("metadata"), "games.json"), os.path.join(DATA, "games.json")):
        try:
            with open(path, encoding="utf-8") as source:
                rows += json.load(source)
        except (OSError, ValueError):
            pass
    return next((dict(row) for row in rows if row["system"] == g.get("system") and metadata_key(row["title"]) == metadata_key(g["title"])), {})


def trailer_for_game(g, known):
    video_id = known.get("youtube")
    name = metadata_title(g["title"])
    if not video_id:
        cache = load("trailer-cache.json", {})
        key = str(g.get("system", "")) + ":" + metadata_key(name)
        hit = cache.get(key)
        if hit and time.time() - hit["t"] < (7 * 86400 if hit["d"] else 600):
            return hit["d"]
        try:
            query = urllib.parse.urlencode({"search_query": name + " " + g.get("system", "") + " official trailer"})
            req = urllib.request.Request("https://www.youtube.com/results?" + query, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as response:
                page = response.read(5_000_000).decode("utf-8")
            match = re.search(r"(?:var )?ytInitialData\s*=\s*", page)
            if not match:
                return []
            data, _ = json.JSONDecoder().raw_decode(page[match.end():])
            videos = []
            def walk(node):
                if isinstance(node, dict):
                    if "videoRenderer" in node:
                        videos.append(node["videoRenderer"])
                    else:
                        for value in node.values(): walk(value)
                elif isinstance(node, list):
                    for value in node: walk(value)
            walk(data)
            wanted = metadata_key(name)
            candidates = []
            for video in videos:
                title = "".join(x.get("text", "") for x in video.get("title", {}).get("runs", []))
                owner = "".join(x.get("text", "") for x in video.get("ownerText", {}).get("runs", []))
                if wanted not in metadata_key(title) or not re.search(r"trailer|commercial", title, re.I):
                    continue
                if re.search(r"fan.?made|concept|reaction|review", title, re.I):
                    continue
                candidate = video.get("videoId", "")
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                    candidates.append((bool(re.search(r"Nintendo|Pok.mon|PlayStation|Xbox|Ubisoft|Rockstar", owner, re.I)), candidate, title))
            if candidates:
                _, video_id, name = max(candidates, key=lambda item: item[0])
            result = [{"youtube": video_id, "name": name + " — Trailer", "thumb": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}] if video_id else []
            cache = load("trailer-cache.json", {})
            cache[key] = {"t": time.time(), "d": result}
            store("trailer-cache.json", cache)
            return result
        except (urllib.error.URLError, ValueError, TimeoutError):
            return []
    return [{"youtube": video_id, "name": name + " — Official trailer", "thumb": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}]


LR_INDEX, LR_LOCK = {}, threading.Lock()


def libretro_index(thumbs, kind):
    """Every image libretro has for one console ("Named_Snaps" gameplay, "Named_Titles" title screens), keyed by
    cleaned-up title, so "Mario Kart DS" finds "Mario Kart DS (Europe) (En,Fr,De,Es,It).png". Cached for a month."""
    key = f"{thumbs}/{kind}"
    with LR_LOCK:
        if key in LR_INDEX:
            return LR_INDEX[key]
        hit = load("libretro-index.json", {}).get(key)
        if hit and time.time() - hit["t"] < 30 * 86400:
            names = hit["names"]
        else:
            req = urllib.request.Request("https://thumbnails.libretro.com/" + urllib.parse.quote(f"{thumbs}/{kind}/"), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
            names = [urllib.parse.unquote(n)[:-4] for n in re.findall(r'href="([^"?/][^"]*\.png)"', page)]
            cache = load("libretro-index.json", {})
            cache[key] = {"t": time.time(), "names": names}
            store("libretro-index.json", cache)
        index = {}
        for n in names:
            index.setdefault(metadata_key(n), []).append(n)
        LR_INDEX[key] = index
        return index


def libretro_rank(n):
    """Finished USA or World copies before other regions; demos and kiosk builds last."""
    unfinished = bool(re.search(r"\((?:[^)]*\b)?(?:Demo|Kiosk|Beta|Proto|Sample|Preview)\b", n, re.I))
    region = next((i for i, r in enumerate(("USA", "World", "Europe", "Australia", "Japan")) if re.search(rf"[(,] ?{r}\b", n)), 9)
    return (unfinished, region, len(n))


def libretro_pick(names):
    return min(names, key=libretro_rank)


def libretro_art(g, kind, query=""):
    """Art choices for an emulated game when SteamGridDB has little or nothing: box art for the cover, gameplay and
    title screens for the background. A typed search name finds every release whose title starts with it."""
    info = system_info(g.get("system") or g.get("group"))
    if g.get("source") != "Emulators" or not info or not info["thumbs"]:
        return []
    stem = os.path.splitext(os.path.basename((g.get("launch") or {}).get("rom", "")))[0]
    keys = [k for k in ([metadata_key(query)] if query else [metadata_key(stem), metadata_key(g["title"])]) if k]
    out = []
    for lr_kind in ("Named_Snaps", "Named_Titles") if kind == "hero" else ("Named_Boxarts",):
        try:
            index = libretro_index(info["thumbs"], lr_kind)
        except (urllib.error.URLError, ValueError, TimeoutError, OSError):
            continue
        names = [n for k in keys for n in index.get(k, [])]
        if query and not names:
            names = [n for key, ns in index.items() if any(key.startswith(k) for k in keys) for n in ns]
        for n in sorted(dict.fromkeys(names), key=libretro_rank)[:16]:
            url = "https://thumbnails.libretro.com/" + urllib.parse.quote(f"{info['thumbs']}/{lr_kind}/{n}.png")
            out.append({"thumb": url, "url": url, "author": "libretro"})
    return out


def libretro_cover(g):
    """libretro's box art for an emulated game, found in its list of files by cleaned-up name (so "Mario Kart DS.nds" finds
    "Mario Kart DS (USA, Australia) (En,Fr,De,Es,It)"): no account needed. Empty if it has none, or can't be reached."""
    hits = libretro_art(g, "cover")
    return hits[0]["url"] if hits else ""


def emulator_screenshots(g):
    info = system_info(g.get("system") or g.get("group"))
    if not info or not info["thumbs"]:
        return []
    stem = os.path.splitext(os.path.basename((g.get("launch") or {}).get("rom", "")))[0]
    shots = []
    for kind in ("Named_Snaps", "Named_Titles"):
        try:
            index = libretro_index(info["thumbs"], kind)
        except (urllib.error.URLError, ValueError, TimeoutError, OSError):
            continue
        names = next((index[k] for k in (metadata_key(stem), metadata_key(g["title"])) if k and k in index), None)
        if names:
            url = "https://thumbnails.libretro.com/" + urllib.parse.quote(f"{info['thumbs']}/{kind}/{libretro_pick(names)}.png")
            shots.append({"thumb": url, "full": url})
    return shots


PS_STORE_REGION = {"UP": "en-us", "EP": "en-gb", "JP": "ja-jp", "HP": "en-hk", "KP": "ko-kr"}


def ps_store_shots(content_id):
    """Screenshots from the game's PlayStation Store page (PS4/PS5), found by the content id inside its .pkg or dump. Cached."""
    cache = load("psstore-cache.json", {})
    if content_id in cache and time.time() - cache[content_id]["t"] < (30 * 86400 if cache[content_id]["shots"] else 86400):
        return cache[content_id]["shots"]
    shots = []
    for region in dict.fromkeys([PS_STORE_REGION.get(content_id[:2], "en-us"), "en-us", "en-gb"]):
        try:
            req = urllib.request.Request(f"https://store.playstation.com/{region}/product/{urllib.parse.quote(content_id)}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                page = r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        urls = re.findall(r'"role":"SCREENSHOT","type":"IMAGE","url":"(https://image\.api\.playstation\.com/[^"]+)"', page)
        shots = [{"thumb": u + "?w=640", "full": u} for u in list(dict.fromkeys(urls))[:10]]
        if shots:
            break
    cache = load("psstore-cache.json", {})
    cache[content_id] = {"t": time.time(), "shots": shots}
    store("psstore-cache.json", cache)
    return shots


def trailer_stills(trailers):
    """Three frames YouTube keeps from the trailer (at a quarter, half and three quarters), for games no store has pictures of."""
    vid = next((t["youtube"] for t in trailers or [] if t.get("youtube")), None)
    if not vid:
        return []
    base = f"https://i.ytimg.com/vi/{vid}/"
    big = remote_ok(base + "maxres1.jpg")
    return [{"thumb": f"{base}mq{n}.jpg", "full": f"{base}{'maxres' if big else 'hq'}{n}.jpg"} for n in (1, 2, 3)]


WIKI_PAUSE = [0.0]  # Wikipedia said "too many requests": leave it alone until then instead of making it worse


def platform_words(system):
    """How a console's articles name it ("Switch 2", "Super Nintendo Entertainment System"), to tell same-named games apart."""
    info = system_info(system) or {}
    words = [system] + ([info["thumbs"].split(" - ", 1)[-1]] if info.get("thumbs") else [])
    return [w for w in dict.fromkeys(words) if w and len(w) > 2]


def wiki_game_info(title, system=None):
    """Matched game biography plus structured genre, studio and release data. Two games of one name ("Star Fox" on the
    SNES and on Switch 2) each have a dated page: the one naming the game's console is used, and kept under the console."""
    title = metadata_title(title)
    key = norm(title)
    cache = load("wiki-info-cache.json", {})
    hit = cache.get(f"{key}|{system}") if system else cache.get(key)
    if hit and time.time() - hit["t"] < 30 * 86400 and hit.get("v") == 4:
        return hit["d"]
    if time.time() < WIKI_PAUSE[0]:
        return {}
    out = {}
    try:
        hits = []
        # ROM names put the subtitle after " - "; search as written, then for the part before it ("Rust - Staging Branch")
        # with the console too, so a remake with its own page ("Ocarina of Time (2026 video game)" on Switch 2) is among them
        for q in dict.fromkeys([title.replace(" - ", ": "), re.split(r"\s+-\s+", title)[0]] + ([f"{title.replace(' - ', ': ')} {system}"] if system else [])):
            query = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": q if system and q.endswith(system) else f"{q} video game", "srlimit": 6, "format": "json"})
            hits += [h for h in http_json("https://en.wikipedia.org/w/api.php?" + query, headers=WIKI_UA, timeout=8)["query"]["search"]
                     if h["title"] not in {x["title"] for x in hits}]
            if any(wiki_match_rank(h["title"], title) is not None for h in hits) and not system:
                break
        ranked = sorted(((wiki_match_rank(h["title"], title), i, h) for i, h in enumerate(hits)), key=lambda x: (x[0] is None, x[0] or 0, x[1]))
        plat, other_console, chosen = platform_words(system) if system else [], None, None
        for rank, _, hit in ranked:
            if rank is None:
                break
            summary = http_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(hit["title"].replace(" ", "_"), safe=""), headers=WIKI_UA, timeout=8)
            text = summary.get("extract", "")
            if summary.get("type") != "standard" or "game" not in text.lower():
                continue
            first = re.split(r"(?<=[.!?])\s", text)[0]
            if (rank == 3 and re.search(r"\b(series|franchise)\b", first, re.I)) or re.search(r"\bis an? (\w+ )*(series|franchise)\b", first, re.I):
                continue  # a page about the whole series ("Star Fox is a series of..."), not this game
            if rank <= 2 and plat and not any(w.lower() in text.lower() for w in plat):  # the original, when a version for this console has its own page
                other_console = other_console or (rank, summary, hit)  # a same-named game on another console: only if nothing better
                continue
            chosen = (rank, summary, hit)
            break
        for rank, summary, hit in [chosen or other_console] if (chosen or other_console) else []:
            text = summary.get("extract", "")
            dated = rank == 2
            sentences = re.split(r"(?<=[.!?])\s+", text)
            bio = ""
            for sentence in sentences:
                if bio and len(bio) + len(sentence) > 650:
                    break
                bio = (bio + " " + sentence).strip()
            out = {"description": bio, "descSource": "Wikipedia", "sourceTitle": summary.get("title") or hit["title"], "_dated": dated}
            entity_id = summary.get("wikibase_item", "")
            if re.fullmatch(r"Q\d+", entity_id):
                entity = http_json(f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json", headers=WIKI_UA, timeout=8)["entities"][entity_id]
                claims = entity.get("claims", {})
                def values(prop):
                    return [c["mainsnak"]["datavalue"]["value"] for c in claims.get(prop, []) if c.get("rank") != "deprecated" and "datavalue" in c.get("mainsnak", {})]
                genres = [v["id"] for v in values("P136") if isinstance(v, dict) and "id" in v][:3]
                developers = [v["id"] for v in values("P178") if isinstance(v, dict) and "id" in v][:2]
                # each publication date may name its platform (qualifier P400): "1998 on N64, 2011 on 3DS"
                dated_claims = []
                for c in claims.get("P577", []):
                    v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if c.get("rank") != "deprecated" and isinstance(v, dict) and v.get("precision", 0) >= 9 and v.get("time", "").startswith("+"):
                        on = [q["datavalue"]["value"]["id"] for q in c.get("qualifiers", {}).get("P400", []) if "datavalue" in q]
                        dated_claims.append((v["time"][1:5], on))
                platforms = list(dict.fromkeys(p for _, on in dated_claims for p in on))[:20]
                ids = list(dict.fromkeys(genres + developers + platforms))
                labels = {}
                if ids:
                    q = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels", "languages": "en", "languagefallback": 1, "format": "json"})
                    entities = http_json("https://www.wikidata.org/w/api.php?" + q, headers=WIKI_UA, timeout=8).get("entities", {})
                    labels = {k: v.get("labels", {}).get("en", {}).get("value", "") for k, v in entities.items()}
                    out["genres"] = [labels[i] for i in genres if labels.get(i)]
                    out["developer"] = ", ".join(labels[i] for i in developers if labels.get(i))
                def on_this_console(name):
                    name = norm(name)
                    return any(norm(w) == name or norm("Nintendo " + w) == name for w in plat)
                mine = [y for y, on in dated_claims if any(on_this_console(labels.get(p, "")) for p in on)]
                if mine:
                    out["released"] = min(mine)  # the year it came out on this game's console
                elif dated_claims and (not plat or any(w.lower() in text.lower() for w in plat)):
                    out["released"] = min(y for y, _ in dated_claims)  # year avoids implying one platform/region's date applies to all
                # otherwise the page is another console's version (the N64 original for a Switch 2 release): no year beats a wrong one
            break
    except urllib.error.HTTPError as e:
        if e.code == 429:
            wait = e.headers.get("Retry-After", "")
            WIKI_PAUSE[0] = time.time() + (int(wait) if wait.isdigit() else 900)
        out.pop("_dated", None)
        return out
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
        out.pop("_dated", None)
        return out  # retain a biography if structured metadata is temporarily unavailable; retry later
    dated = out.pop("_dated", False)
    if out:
        cache = load("wiki-info-cache.json", {})
        cache[f"{key}|{system}" if system else key] = {"t": time.time(), "d": out, "v": 4}  # the year depends on the console
        store("wiki-info-cache.json", cache)
    return out


def detail_art(key, path):
    DETAIL_ART[key] = path
    return f"/api/art/{key}?v={int(os.path.getmtime(path))}"


from concurrent.futures import ThreadPoolExecutor

POOL = ThreadPoolExecutor(8)   # slow lookups for one game run side by side
INFO_TTL = 7 * 86400           # store text, screenshots and art URLs are kept on disk for a week
NEWS = {}                      # game id -> (time, news); news refreshes after 30 minutes


def steam_store_info(appid):
    info = http_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english", timeout=8).get(str(appid)) or {}
    data = (info.get("data") or {}) if info.get("success") else {}
    return {"description": html.unescape(data.get("short_description", "")), "genres": [x["description"] for x in data.get("genres", [])][:3],
            "developer": ", ".join(data.get("developers", [])[:2]), "released": (data.get("release_date") or {}).get("date", ""),
            "screenshots": [{"thumb": x["path_thumbnail"], "full": x["path_full"]} for x in data.get("screenshots", [])[:12]],
            # Steam streams trailers (HLS); older ones also exist as a plain MP4, used if the stream fails
            "trailers": [{"name": m.get("name", "").strip(), "thumb": m.get("thumbnail", ""), "hls": m.get("hls_h264", ""),
                          "mp4": f"https://video.akamai.steamstatic.com/store_trailers/{m['id']}/movie_max.mp4"}
                         for m in data.get("movies", [])[:4] if m.get("hls_h264") or m.get("id")]}


def local_steam_art(g, appid):
    """Hero/logo files Steam already downloaded (instant, no network)."""
    out, sp = {}, steam_path()
    if not sp or not appid:
        return out
    cache = os.path.join(sp, "appcache", "librarycache")
    for field, name in (("hero", "library_hero.jpg"), ("logo", "logo.png")):
        hits = glob.glob(os.path.join(cache, appid, "*", name)) + glob.glob(os.path.join(cache, appid, name)) + glob.glob(os.path.join(cache, f"{appid}_{name}"))
        if hits:
            out[field] = detail_art(f"{safe_name(g['id'])}-{field}", hits[0])
    return out


def sgdb_art(key, g, need_hero, need_logo):
    m = sgdb_game_for(key, g)
    if not m:
        return {}
    hero = POOL.submit(sgdb, f"/heroes/game/{m['id']}", key, types="static", nsfw="false") if need_hero else None
    logo = POOL.submit(sgdb, f"/logos/game/{m['id']}", key, types="static", nsfw="false") if need_logo else None
    out = {}
    if hero and (hero.result() or []):
        out["hero"] = hero.result()[0]["url"]
    if logo and (logo.result() or []):
        out["logo"] = logo.result()[0]["url"]
    return out


def quiet(fut, default):
    try:
        return fut.result() if fut else default
    except Exception:
        return default


def info_fresh(hit, g):
    """A cached details entry still holds: same name (a renamed ROM looks again), saved with a studio or by this version,
    and not expired (entries without a description retry after 5 minutes)."""
    return (bool(hit) and hit.get("title", g["title"]) == g["title"]
            and (hit.get("version") == 10 or (hit.get("version") in (7, 8, 9) and g.get("source") != "Emulators")
                 or (hit.get("version") in (5, 6) and g.get("source") != "Emulators" and hit["d"].get("developer") and hit["d"].get("screenshots")))
            and time.time() - hit["t"] < (INFO_TTL if hit.get("d", {}).get("description") else 300))


def remote_info(g, appid, local):
    """Store text, screenshots, trailers and online art for a game. Network lookups run in parallel; cached on disk."""
    if g.get("isFolder"):  # nothing to look up for a folder
        return {"description": "", "genres": [], "developer": "", "released": "", "screenshots": [], "trailers": [], "descSource": "", "hero": "", "logo": ""}
    cache = load("info-cache.json", {})
    hit = cache.get(g["id"])
    if info_fresh(hit, g):
        return hit["d"]
    cfg, accounts = config(), load("accounts.json", {})
    cdn = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/" if appid else ""
    store_f = POOL.submit(steam_store_info, appid) if appid and g.get("source") != "Emulators" else None  # not a PC port's page
    hero_ok = POOL.submit(remote_ok, cdn + "library_hero.jpg") if appid and "hero" not in local else None
    logo_ok = POOL.submit(remote_ok, cdn + "logo.png") if appid and "logo" not in local else None
    epic = g.get("epic") or {}
    sgdb_f = None
    if "sgdb" in accounts and ("hero" not in local or "logo" not in local):
        sgdb_f = POOL.submit(sgdb_art, accounts["sgdb"]["key"], g, "hero" not in local, "logo" not in local)
    d = {"description": "", "genres": [], "developer": "", "released": "", "screenshots": [], "trailers": [], "descSource": ""}
    d.update(quiet(store_f, {}))
    sg = quiet(sgdb_f, {})
    d["hero"] = (cdn + "library_hero.jpg" if quiet(hero_ok, False) else "") or epic.get("hero", "") or sg.get("hero", "")
    d["logo"] = (cdn + "logo.png" if quiet(logo_ok, False) else "") or epic.get("logo", "") or sg.get("logo", "")
    d["description"] = d["description"] or html.unescape(epic.get("description", ""))
    known = known_game_info(g) if g.get("source") == "Emulators" else {}
    if known:
        d.update({k: known[k] for k in ("description", "genres", "developer", "released", "descSource", "sourceUrl")})
        if known.get("logo"):
            d["logo"] = known["logo"]
    if not d["description"] and cfg["onlineCovers"]:
        bio = wiki_game_info(g["title"], g.get("system"))
        for field in ("description", "descSource", "sourceTitle", "genres", "developer", "released"):
            if not d.get(field) and bio.get(field):
                d[field] = bio[field]
    if cfg["onlineCovers"]:
        if not d["screenshots"] and g.get("source") == "Emulators":
            d["screenshots"] = emulator_screenshots(g)
        if not d["screenshots"] and g.get("contentId"):
            d["screenshots"] = ps_store_shots(g["contentId"])
        if not d["trailers"]:  # delisted Steam games, Epic games and ROMs: look for an official trailer on YouTube
            d["trailers"] = trailer_for_game(g, known)
        if not d["screenshots"]:  # still nothing (delisted games, add-on-only packages): stills from the trailer
            d["screenshots"] = trailer_stills(d["trailers"])
    if not d["hero"] and "hero" not in local and d["screenshots"]:  # no background art anywhere: a screenshot, shown softened
        d["hero"], d["heroSoft"] = d["screenshots"][0]["full"], True
    cache = load("info-cache.json", {})
    cache[g["id"]] = {"t": time.time(), "d": d, "version": 10, "title": g["title"]}
    store("info-cache.json", cache)
    return d


ACH = {}  # game id -> (time, achievements); refreshed after 10 minutes


def achievements(g):
    if g.get("source") == "Emulators":  # ROMs: RetroAchievements
        if not ra_account():
            return None
        hit = ACH.get(g["id"])
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        # no placeholder while it loads: a second request meanwhile (the details screen asks twice) would read it as
        # "no achievements". A failed lookup isn't remembered either, so the next request simply tries again.
        result = ra_progress(g)
        ACH[g["id"]] = (time.time(), result)
        return result
    acc = load("accounts.json", {}).get("steam")
    if not acc or not g.get("appid"):
        return None
    hit = ACH.get(g["id"])
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    q = urllib.parse.urlencode({"appid": g["appid"], "key": acc["key"], "steamid": acc["steamid"]})
    try:
        ach = http_json("https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/?" + q, timeout=8)["playerstats"].get("achievements") or []
    except Exception:
        ACH[g["id"]] = (time.time(), None)  # failed (often: the game has no stats): don't ask again straight away
        raise
    result = {"done": sum(a.get("achieved", 0) for a in ach), "total": len(ach), "source": "Steam",
              "items": steam_ach_items(g["appid"], acc["key"], ach)} if ach else None
    ACH[g["id"]] = (time.time(), result)
    return result


def steam_icon(url):
    """Steam moved achievement icons; the schema still gives the old address, which is gone for many games."""
    return re.sub(r"^https://[^/]+/steamcommunity/public/images/apps/", "https://shared.cloudflare.steamstatic.com/community_assets/images/apps/", url or "")


def steam_ach_items(appid, key, player):
    """Each Steam achievement with its name, description, icon (grey while locked), unlock time and how many players
    have it. Names and icons come from the game's schema, cached for a month; failing that, just the IDs."""
    def schema():
        q = urllib.parse.urlencode({"appid": appid, "key": key, "l": "english"})
        rows = http_json("https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?" + q, timeout=8)
        rows = ((rows.get("game") or {}).get("availableGameStats") or {}).get("achievements") or []
        q = urllib.parse.urlencode({"gameid": appid})
        try:
            pct = {a["name"]: float(a["percent"]) for a in http_json(
                "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/?" + q, timeout=8)
                ["achievementpercentages"]["achievements"]}
        except Exception:
            pct = {}
        return {r["name"]: {"title": r.get("displayName") or r["name"], "desc": r.get("description") or "", "hidden": bool(r.get("hidden")),
                            "icon": r.get("icon", ""), "gray": r.get("icongray", ""), "pct": pct.get(r["name"])} for r in rows}
    try:
        info = ra_cached("steam-ach-cache.json", str(appid), 30, schema)
    except Exception:
        info = {}
    items = []
    for a in player:
        s, got = info.get(a.get("apiname"), {}), bool(a.get("achieved"))
        items.append({"title": s.get("title") or a.get("apiname", ""), "points": 0, "hardcore": False, "rarity": s.get("pct"),
                      "desc": s.get("desc") or ("Hidden achievement" if s.get("hidden") and not got else ""),
                      "earned": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(a["unlocktime"])) if got and a.get("unlocktime") else ("unlocked" if got else ""),
                      "badge": steam_icon((s.get("icon") if got else s.get("gray")) or s.get("icon", ""))})
    return items


# ---------------------------------------------------------------- RetroAchievements (emulated games)
# With a RetroAchievements username and web API key, each ROM is matched to its RetroAchievements game (by the ROM's
# fingerprint like emulators do, else by title) and its details screen shows your progress and the achievement list.
RA_API = "https://retroachievements.org/API/"
RA_MEDIA = "https://media.retroachievements.org"
RA_KEY_PAGE = "https://retroachievements.org/settings"
# our console names -> RetroAchievements system names (theirs vary, e.g. "SNES/Super Famicom", "Mega Drive")
RA_SYSTEM = {"NES": ["NES/Famicom", "NES"], "SNES": ["SNES/Super Famicom", "SNES"], "N64": ["Nintendo 64"], "Game Boy": ["Game Boy"],
             "GBC": ["Game Boy Color"], "GBA": ["Game Boy Advance"], "DS": ["Nintendo DS"], "3DS": ["Nintendo 3DS"], "GameCube": ["GameCube"],
             "Wii": ["Wii"], "Wii U": ["Wii U"], "PS1": ["PlayStation"], "PS2": ["PlayStation 2"], "PSP": ["PlayStation Portable"],
             "Genesis": ["Genesis/Mega Drive", "Mega Drive"], "Saturn": ["Saturn"], "Dreamcast": ["Dreamcast"]}
RA_CART = {"NES", "SNES", "N64", "Game Boy", "GBC", "GBA", "Genesis"}  # whole-file fingerprints (discs and DS need more)


def ra_account():
    return load("accounts.json", {}).get("ra")


RA_CALL = threading.Lock()
RA_LAST = [0.0]


def ra(endpoint, acc=None, **q):
    """One request at a time, a moment apart, retrying when told to slow down: RetroAchievements answers parallel
    requests with "too many requests" (several games' details load together)."""
    acc = acc or ra_account()
    url = RA_API + endpoint + "?" + urllib.parse.urlencode({**q, "y": acc["key"], "z": acc["user"]})
    for attempt in range(4):
        with RA_CALL:
            time.sleep(max(0.0, RA_LAST[0] + 0.25 - time.time()))
            try:
                return http_json(url, timeout=15)
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 3:
                    raise
                wait = e.headers.get("Retry-After", "")
                time.sleep(min(10, int(wait)) if wait.isdigit() else 1.5 * (attempt + 1))
            finally:
                RA_LAST[0] = time.time()


RA_LOCK = threading.Lock()  # one download of each list at a time (several games ask together when the helper starts)


def ra_cached(name, key, days, fetch):
    with RA_LOCK:
        cache = load(name, {})
        hit = cache.get(key)
        if hit and time.time() - hit["t"] < days * 86400:
            return hit["d"]
        data = fetch()
        cache = load(name, {})
        cache[key] = {"t": time.time(), "d": data}
        store(name, cache)
        return data


def ra_console_id(system):
    consoles = ra_cached("ra-cache.json", "consoles", 30, lambda: [{"ID": c["ID"], "Name": c["Name"]} for c in ra("API_GetConsoleIDs.php", g=1)])
    by_name = {norm(c["Name"]): c["ID"] for c in consoles}
    return next((by_name[norm(n)] for n in RA_SYSTEM.get(system, [system]) if norm(n) in by_name), None)


def ra_games(console_id):
    return ra_cached("ra-cache.json", f"games-{console_id}", 7, lambda: [
        {"ID": x["ID"], "Title": x["Title"], "Hashes": [h.lower() for h in x.get("Hashes") or []], "Icon": x.get("ImageIcon", "")}
        for x in ra("API_GetGameList.php", i=console_id, f=1, h=1)])


def ra_title_key(title):
    """"Legend of Zelda, The: Ocarina of Time 3D" and "Legend of Zelda The - Ocarina of Time 3D" give the same key."""
    t = re.sub(r"~[^~]*~|\[[^]]*\]|\([^)]*\)", "", metadata_title(title)).lower()
    t = re.sub(r"\b(the|version)\b", " ", t.replace("é", "e"))
    return re.sub(r"[^a-z0-9]", "", t)


def ra_fingerprint(path, system, exts):
    """MD5 of a cartridge ROM the way RetroAchievements hashes it (copier/iNES headers skipped, N64 in big-endian order)."""
    import hashlib
    import zipfile
    if system not in RA_CART or not os.path.isfile(path) or os.path.getsize(path) > 96 * 1024 * 1024:
        return None
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            member = next((m for m in z.infolist() if os.path.splitext(m.filename)[1].lower() in exts and m.file_size <= 96 * 1024 * 1024), None)
            if not member:
                return None
            data = z.read(member)
    elif path.lower().endswith(".7z"):
        return None
    else:
        with open(path, "rb") as f:
            data = f.read()
    if system == "NES" and data[:4] == b"NES\x1a":
        data = data[16:]
    elif system == "SNES" and len(data) % 1024 == 512:
        data = data[512:]
    elif system == "N64" and data[:1] == b"\x37":      # .v64: byte-swapped
        data = b"".join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, len(data) - 1, 2))
    elif system == "N64" and data[:1] == b"\x40":      # .n64: little-endian words
        data = b"".join(data[i:i + 4][::-1] for i in range(0, len(data) - 3, 4))
    return hashlib.md5(data).hexdigest()


def ra_game_for(g):
    """The RetroAchievements game for a ROM (0 = none); remembered per game."""
    matches = load("ra-match.json", {})
    if g["id"] in matches:
        return matches[g["id"]]
    system = g.get("system") or g.get("group")
    cid = ra_console_id(system)
    found = 0
    if cid:
        games = ra_games(cid)
        L = g.get("launch") or {}
        try:
            fp = ra_fingerprint(L.get("rom", ""), system, set((system_info(system) or {}).get("exts") or []))
        except (OSError, ValueError, RuntimeError):
            fp = None
        hit = next((x for x in games if fp and fp in x["Hashes"]), None)
        if not hit:  # by name: main sets only (not hacks or bonus subsets); "Pokémon HeartGold | Pokémon SoulSilver" matches either
            want = ra_title_key(g["title"])
            hit = next((x for x in games if not x["Title"].startswith("~") and "[Subset" not in x["Title"]
                        and want in {ra_title_key(part) for part in x["Title"].split("|")}), None)
        found = hit["ID"] if hit else 0
    with RA_LOCK:
        matches = load("ra-match.json", {})
        matches[g["id"]] = found
        store("ra-match.json", matches)
    return found


def ra_progress(g):
    acc = ra_account()
    game_id = ra_game_for(g) if acc else 0
    if not game_id:
        return None
    d = ra("API_GetGameInfoAndUserProgress.php", acc, g=game_id, u=acc.get("ulid") or acc["user"])
    items = sorted((d.get("Achievements") or {}).values(), key=lambda a: (not a.get("DateEarned"), a.get("DisplayOrder") or 0))
    return {"done": d.get("NumAwardedToUser") or 0, "total": d.get("NumAchievements") or len(items), "source": "RetroAchievements",
            "items": [{"title": a.get("Title", ""), "desc": a.get("Description", ""), "points": a.get("Points") or 0,
                       "earned": a.get("DateEarnedHardcore") or a.get("DateEarned") or "", "hardcore": bool(a.get("DateEarnedHardcore")),
                       "badge": f"{RA_MEDIA}/Badge/{a.get('BadgeName')}{'' if a.get('DateEarned') else '_lock'}.png"} for a in items]}


def warm_details():
    """After startup, quietly fetch details for games not cached yet (most recently played first), so details open instantly."""
    time.sleep(5)
    try:
        all_news()  # so the News page opens instantly
    except Exception:
        pass
    for g in sorted(STATE["games"], key=lambda x: -(x.get("lastPlayed") or 0)):
        if info_fresh(load("info-cache.json", {}).get(g["id"]), g):
            continue
        try:
            appid = steam_appid_for(g) if g.get("appid") or config()["onlineCovers"] else None
            remote_info(g, appid, local_steam_art(g, appid))
        except Exception:
            pass
        time.sleep(1.5)  # gentle on Steam / Wikipedia rate limits


def game_details(g):
    """Everything the details screen shows except news (fetched separately so the screen fills in at once)."""
    cfg = config()
    look = g
    appid = steam_appid_for(look) if g.get("appid") or (cfg["onlineCovers"] and not g.get("isFolder")) else None
    local = local_steam_art(g, appid)
    ach_f = POOL.submit(achievements, g)
    d = dict(remote_info(look, appid, local))
    raw = d.get("genres") or []  # Wikipedia gives "racing video game"; show "Racing"
    d["genres"] = list(dict.fromkeys((tidy_genres([x]) or [(lambda y: y[:1].upper() + y[1:])(re.sub(r"\s+video games?$", "", x, flags=re.I))])[0] for x in raw))
    d["hero"] = local.get("hero") or d.get("hero", "")
    d["heroSoft"] = bool(d.get("heroSoft")) and not local.get("hero")
    d["logo"] = local.get("logo") or d.get("logo", "")
    custom = load("overrides.json", {}).get(g["id"], {}).get("hero")
    if custom and os.path.isfile(os.path.join(ART_DIR, custom)):  # background the user picked
        d["hero"] = detail_art(f"{safe_name(g['id'])}-customhero", os.path.join(ART_DIR, custom))
        d["heroSoft"] = False
    custom_logo = load("overrides.json", {}).get(g["id"], {}).get("logo")
    if custom_logo and os.path.isfile(os.path.join(ART_DIR, custom_logo)):
        d["logo"] = detail_art(f"{safe_name(g['id'])}-customlogo", os.path.join(ART_DIR, custom_logo))
    try:  # don't hold the screen up for Steam's achievements service; the UI asks again if it isn't ready
        d["achievements"], d["achPending"] = ach_f.result(timeout=0.25), False
    except Exception:
        d["achievements"], d["achPending"] = None, not ach_f.done()
    news = NEWS.get(g["id"])
    d["news"] = news[1] if news and time.time() - news[0] < 1800 else None
    if g.get("source") == "Emulators":
        d["raConnected"] = bool(ra_account())
    DETAILS[g["id"]] = (time.time(), d)
    return d


def all_news():
    """News from your Steam games (most recently played first), merged newest first, for the News page."""
    games = [g for g in STATE["games"] if g.get("appid") and not g.get("hidden")]
    games.sort(key=lambda g: (-(g.get("lastPlayed") or 0), not g["installed"], g["title"]))
    results = list(POOL.map(lambda g: (g, game_news(g)), games[:30]))
    items = [{**n, "game": g["title"], "gameId": g["id"], "cover": g["cover"]} for g, news in results for n in news[:4]]
    items.sort(key=lambda n: -n["date"])
    return items[:80]


# ---------- What's new: this app's own releases, for the News page ----------
WHATS_NEW = {"at": 0.0, "items": None, "error": ""}


def markdown_inline(text):
    """Markdown's inline marks taken out: the page shows plain text."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # pictures are blocks of their own
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)  # [text](link) -> text
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    return tidy(html.unescape(t))


def markdown_blocks(md):
    """A release's notes (Markdown) as the plain blocks the reader shows, like a Steam post's."""
    blocks, para = [], []

    def flush():
        if para:
            text = markdown_inline(" ".join(para))
            if text:
                blocks.append({"t": "p", "text": text})
            para.clear()
    for line in (md or "").replace("\r\n", "\n").split("\n"):
        s = line.strip()
        img = re.fullmatch(r"!\[[^\]]*\]\((https://[^\s)]+)[^)]*\)", s)
        head = re.match(r"#{1,6}\s+(.*)", s)
        item = re.match(r"(?:[-*+]|\d+[.)])\s+(.*)", s)
        if not s or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            flush()
        elif img:
            flush()
            blocks.append({"t": "img", "src": img.group(1)})
        elif head:
            flush()
            if markdown_inline(head.group(1)):
                blocks.append({"t": "h", "text": markdown_inline(head.group(1))})
        elif item:
            flush()
            if markdown_inline(item.group(1)):
                blocks.append({"t": "li", "text": markdown_inline(item.group(1))})
        elif blocks and blocks[-1]["t"] == "li" and not para and line[:1] in (" ", "\t"):  # an item carried on to the next line
            blocks[-1]["text"] = tidy(blocks[-1]["text"] + " " + markdown_inline(s))
        else:
            para.append(s)
    flush()
    return blocks[:150]


def release_date(text):
    try:
        import calendar
        return calendar.timegm(time.strptime(text or "", "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return 0


def in_app_notes(md):
    """A release's notes as the app shows them: without the section on downloading it, which someone reading this has done."""
    out, skip = [], False
    for b in markdown_blocks(md):
        if b["t"] == "h":
            skip = bool(re.match(r"(download|install(ing|ation)?)\b", b["text"], re.I))
        if not skip:
            out.append(b)
    return out


def release_summary(blocks):
    """The first lines of a release's notes, for its card."""
    text = " ".join(b["text"] for b in blocks if b["t"] in ("p", "li"))
    return text[:280] + ("…" if len(text) > 280 else "")


def whats_new():
    """This app's releases, newest first, from its GitHub page: asked for at most once an hour, and the last answer kept
    (with GitHub's ETag) for when it can't be reached."""
    if WHATS_NEW["items"] is not None and time.time() - WHATS_NEW["at"] < 3600:
        return WHATS_NEW["items"], WHATS_NEW["error"]
    saved = load("whatsnew.json", {})
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if saved.get("etag") and saved.get("releases") is not None:
        headers["If-None-Match"] = saved["etag"]
    releases, error = saved.get("releases"), ""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases?per_page=100", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            releases = [{"version": str(x.get("tag_name") or "").lstrip("vV"), "name": str(x.get("name") or ""), "notes": str(x.get("body") or ""),
                         "date": release_date(x.get("published_at")), "page": str(x.get("html_url") or "")}
                        for x in json.loads(r.read().decode("utf-8")) if not x.get("draft") and not x.get("prerelease")]
            store("whatsnew.json", {**load("whatsnew.json", {}), "etag": r.headers.get("ETag", ""), "releases": releases})
    except urllib.error.HTTPError as e:
        if e.code != 304:
            error = "GitHub didn't answer just now" if releases else f"Couldn't reach GitHub ({e.code})"
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        error = "" if releases else "Couldn't reach GitHub. Check the internet connection"
    items = []
    for x in releases or []:
        if not x.get("version"):
            continue
        key, mine, body = version_key(x["version"]), version_key(VERSION), in_app_notes(x["notes"])
        items.append({"version": x["version"], "title": x["name"] or f"Ultra Front End {x['version']}", "date": x["date"], "page": x["page"],
                      "summary": release_summary(body), "body": body,
                      "image": next((b["src"] for b in body if b["t"] == "img"), ""),  # its own picture: the first in its notes
                      "state": "installed" if key == mine else "update" if key > mine else ""})
    items.sort(key=lambda n: version_key(n["version"]), reverse=True)
    # an answer is kept an hour; nothing at all (offline at start-up, say) only a minute, so it's asked again soon
    WHATS_NEW.update(at=time.time() - (0 if releases else 3540), items=items, error=error)
    return items, error


def whats_new_unseen():
    """Whether this version's notes are still to be read: once it has updated itself. A first start just notes the version."""
    saved = load("whatsnew.json", {})
    if not saved.get("seen"):
        store("whatsnew.json", {**saved, "seen": VERSION})
        return False
    if is_nightly(VERSION):
        return False  # nightly builds have no notes of their own in News: only the releases do
    return version_key(saved["seen"]) < version_key(VERSION)


def game_news(g):
    hit = NEWS.get(g["id"])
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    appid = steam_appid_for(g) if g.get("source") != "Emulators" and (g.get("appid") or config()["onlineCovers"]) else None
    try:
        news = steam_news(appid) if appid else []
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
        return []
    NEWS[g["id"]] = (time.time(), news)
    return news


# ---------------------------------------------------------------- library scan
STATE = {"games": [], "byId": {}, "errors": [], "counts": {}, "scanned": 0}
SCAN_LOCK = threading.Lock()


def scan():
    with SCAN_LOCK:
        cfg, accounts = config(), load("accounts.json", {})
        ART_SEEN.clear()
        games, errors, counts = {}, [], {}

        def add(label, fn, key=None):
            try:
                found = fn()
            except Exception as e:  # one broken source shouldn't hide the rest
                rejected = isinstance(e, urllib.error.HTTPError) and e.code in (401, 403)
                errors.append(f"{label}: the saved key was rejected. Reconnect it in Settings › Accounts." if rejected else f"{label}: {e}")
                return
            counts[key or label] = len(found)
            for g in found:
                old = games.get(g["id"])
                if old and g.get("shortcut"):  # a Steam shortcut to a game Steam has listed: Steam's entry stays as it is
                    continue
                if old:  # e.g. Steam account + local install: keep install state and best stats
                    g["launch"] = (g if g["installed"] else old)["launch"]
                    g["installed"] = g["installed"] or old["installed"]
                    g["minutes"] = max(g["minutes"], old["minutes"])
                    g["lastPlayed"] = max(g["lastPlayed"], old["lastPlayed"])
                    if g["cover"].startswith("http") and not old["cover"].startswith("http"):
                        g["cover"] = old["cover"]
                games[g["id"]] = g

        if "steam" in accounts:
            add("Steam account", lambda: scan_steam_account(accounts["steam"]))
        if cfg["steamLocal"]:
            add("Steam (installed)", scan_steam_local)
        if WIN and any(cfg.get(p + "Local", True) for p in SERVICE_SCANS):
            try:
                programs = installed_programs()
            except Exception as e:
                programs = []
                errors.append(f"Installed programs: {e}")
            for prov, fn in (("ea", scan_ea), ("ubisoft", scan_ubisoft), ("gog", scan_gog), ("battlenet", scan_battlenet)):
                if cfg.get(prov + "Local", True):
                    add(f"{LOCAL_PROVIDERS[prov]} (installed)", lambda fn=fn: fn(programs, cfg))
        if "epic" in accounts:
            add("Epic account", lambda: scan_epic(accounts))
        for lib in cfg["libraries"]:
            add(lib["name"], lambda lib=lib: scan_library(lib, cfg), "lib:" + lib["id"])
        root = cfg.get("romRoot")
        if root and os.path.isdir(root):  # ROMs folder: every platform subfolder is a library
            for sub in sorted(os.listdir(root)):
                path = os.path.join(root, sub)
                if not os.path.isdir(path):
                    continue
                s = detect_system(path)
                emu = cfg.get("emulators", {}).get(s["system"], {})
                lib = {"type": "roms", "path": path, "name": s["system"], "emulator": emu.get("path", ""), "args": emu.get("args"),
                       "exts": s["exts"], "thumbs": s["thumbs"]}
                add(f"ROMs/{s['system']}", lambda lib=lib: scan_library(lib, cfg))
        elif root:
            errors.append(f"ROMs folder {root} isn't available")

        remote = [g for g in games.values() if g.get("appid") and g["cover"].startswith(STEAM_CDN.split("{")[0])]
        if remote:
            art = steam_store_art([g["appid"] for g in remote])
            for g in remote:
                g["cover"] = art.get(g["appid"]) or g["cover"]

        for game_id, o in load("overrides.json", {}).items():  # artwork the user picked
            g, f = games.get(game_id), o.get("cover") and os.path.join(ART_DIR, o["cover"])
            if g and f and os.path.isfile(f):
                still = o.get("coverStill") and os.path.join(ART_DIR, o["coverStill"])
                if still and os.path.isfile(still):
                    g["cover"] = local_art(game_id, still)
                    if light_anim(f):  # animated once its light copy is made (asked for here if it isn't)
                        g["coverAnim"] = local_art(game_id + "--anim", f)
                else:
                    g["cover"] = local_art(game_id, f)
                g["custom"] = True
            if g and o.get("hero") and os.path.isfile(os.path.join(ART_DIR, o["hero"])):
                g["customHero"] = True
            if g and o.get("appPath"):
                g["launch"] = {"type": "exe", "exe": o["appPath"], "args": []}
                g["appPath"] = o["appPath"]
                g["installed"] = True
            if g and o.get("logo") and os.path.isfile(os.path.join(ART_DIR, o["logo"])):
                g["customLogo"] = True
            if g and o.get("hidden"):
                g["hidden"] = True
            if g and o.get("title"):
                g["renameTo"] = o["title"]  # applied after the duplicate merge below, which goes by the game's own name
            if g and o.get("favorite"):
                g["favorite"] = True
            if g and o.get("collections"):
                g["collections"] = o["collections"]
        if cfg["onlineCovers"] and "sgdb" in accounts:
            try:
                sgdb_fill_missing(accounts["sgdb"]["key"], list(games.values()))
            except Exception as e:
                errors.append(f"SteamGridDB: {e}")
        for g in games.values():
            if not g["cover"] and g.get("fallbackCover"):
                g["cover"] = libretro_cover(g) or g["fallbackCover"]

        log, sessions, fixed = load("playlog.json", {}), load("sessions.json", []), False
        for g in games.values():
            p = log.get(g["id"])
            if p:
                if "seconds" not in p:  # a log from before 1.2.7: counted again from its sessions, once
                    p["minutes"], fixed = played_seconds(p, g["id"], sessions) // 60, True
                g["lastPlayed"] = max(g["lastPlayed"], p.get("lastPlayed", 0))
                g["minutes"] = max(g["minutes"], p.get("minutes", 0))
        if fixed:
            store("playlog.json", log)
        # A game found by a launcher (EA app, Ubisoft, Battle.net) and again in a games folder added by hand is the same
        # game: keep the launcher's entry (it starts through the launcher) with the better playtime of the two.
        folders = {os.path.normcase(os.path.normpath(g["folder"])): g for g in games.values() if g.get("folder")}
        for game_id, g in list(games.items()):
            exe = os.path.normcase((g.get("launch") or {}).get("exe", ""))
            owner = not g.get("folder") and exe and next((o for f, o in folders.items() if exe.startswith(f + os.sep)), None)
            if owner:
                owner["minutes"], owner["lastPlayed"] = max(owner["minutes"], g["minutes"]), max(owner["lastPlayed"], g["lastPlayed"])
                del games[game_id]
        # A PC game owned twice (on two stores, or two Steam versions of it) shows once: the installed copy, else the one
        # played most, else the latest played, else Steam's; it keeps the better playtime and last-played of the copies.
        copies = {}
        for g in games.values():
            if g.get("source") != "Emulators":
                copies.setdefault(re.sub(r"[^a-z0-9]", "", re.sub(r"[™®©]", "", g["title"].lower())), []).append(g)
        for same in copies.values():
            if len(same) > 1:
                keep = max(same, key=lambda c: (c["installed"], c["minutes"], c["lastPlayed"], c.get("source") == "Steam"))
                for c in same:
                    if c is not keep:
                        keep["minutes"], keep["lastPlayed"] = max(keep["minutes"], c["minutes"]), max(keep["lastPlayed"], c["lastPlayed"])
                        del games[c["id"]]
        for g in games.values():
            if g.get("renameTo"):
                g["title"], g["renamed"] = g.pop("renameTo"), True
        for k in [k for k in ART if k not in ART_SEEN]:
            ART.pop(k, None)
        STATE.update(games=list(games.values()), byId=games, errors=errors, counts=counts, scanned=time.time())
        sync_systems(counts)


# ---------------------------------------------------------------- watching for new games
# Games dropped into the ROMs folder (or any game folder library) show up by themselves: a cheap fingerprint of the
# folders (names, sizes, times) is taken every few seconds, and once it changes and then holds still (so a big ISO has
# finished copying) the library is rescanned. The app sees the new "scanned" time on its next ping and reloads.
WATCH_SKIP = {"media", "covers", "boxart", "images", "screenshots", "saves", "states"}


def fingerprint(path, depth, out, files=True):
    bios = "bios" in os.path.normcase(path).split(os.sep)  # BIOS files can have any extension: all count but the README
    try:
        with os.scandir(path) as it:
            for e in it:  # on Windows the size and time come with the listing, so this costs no extra disk reads
                if e.is_dir(follow_symlinks=False):
                    out.append((e.path,))
                    if depth > 1 and e.name.lower() not in WATCH_SKIP:
                        fingerprint(e.path, depth - 1, out, files)
                elif files and (os.path.splitext(e.name)[1].lower() not in NOT_ROM or bios and e.name.lower() != "readme.txt"):  # saves and art don't count
                    st = e.stat()
                    out.append((e.path, st.st_size, st.st_mtime_ns))
    except OSError:
        pass


def folder_snapshot():
    cfg, out = config(), []
    if cfg.get("romRoot"):
        fingerprint(cfg["romRoot"], 5, out)
    for lib in cfg["libraries"]:
        if lib["type"] == "pc":  # one folder per game: only new or removed game folders matter, not what's inside
            fingerprint(lib["path"], 1, out, files=False)
            try:  # and the shortcuts directly in it
                out += sorted(os.path.join(lib["path"], f) for f in os.listdir(lib["path"]) if f.lower().endswith((".lnk", ".url")))
            except OSError:
                pass
        elif lib["type"] not in ("game", "folder"):  # (a folder tile doesn't change with what's in it: a big movies folder isn't walked)
            fingerprint(lib["path"], 4, out)
    return sorted(out)


def in_use(path):
    """True while another program has the file open, e.g. it's still being copied in. Windows doesn't always show a
    copied file's size growing in the folder listing, so the listing alone can't tell when a copy is done."""
    if os.name != "nt":
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    # read access, no sharing: fails while anyone else has it open
    h = k32.CreateFileW(path, 0x80000000, 0, None, 3, 0x80, None)
    if h is None or h == ctypes.c_void_p(-1).value:
        return ctypes.get_last_error() == 32  # sharing violation
    k32.CloseHandle(ctypes.c_void_p(h))
    return False


MOVING = [False]  # a move into C:/Ultra-Front-End is under way: the folders aren't looked through meanwhile


def watch_folders():
    last, pending = folder_snapshot(), None
    while True:
        time.sleep(4)
        if MOVING[0]:
            continue
        snap = folder_snapshot()
        if snap == last:
            pending = None
            continue
        new_files = [e[0] for e in set(snap) - set(last) if len(e) == 3]
        if snap == pending and not any(in_use(f) for f in new_files):  # changed, then settled, and nothing's still copying
            try:
                scan()
            except Exception as e:
                print("rescan failed:", e)
            apply_soon()  # a BIOS file dropped in: set its emulator up
            last, pending = snap, None
        else:
            pending = snap


# Genres from Steam ("Racing") and Wikipedia ("racing video game") folded into one set for the library's categories.
GENRES = [("Racing", r"racing|kart"), ("RPG", r"role.playing|\brpg\b"), ("Platformer", r"platform"), ("Shooter", r"shooter|\bfps\b"),
          ("Fighting", r"fighting|beat .em up|brawler"), ("Sports", r"sport"), ("Simulation", r"simulat"), ("Strategy", r"strategy|tactic"),
          ("Puzzle", r"puzzle|maze"), ("Party", r"party"), ("Horror", r"horror"), ("Adventure", r"adventure"), ("Action", r"action"),
          ("Multiplayer", r"massively multiplayer|\bmmo"), ("Indie", r"indie"), ("Casual", r"casual")]


def tidy_genres(raw):
    out = []
    for name, pat in GENRES:
        if any(re.search(pat, x, re.I) for x in raw or []) and name not in out:
            out.append(name)
    return out


def public_games():
    cfg, info = config(), load("info-cache.json", {})
    return [{**{k: v for k, v in g.items() if k not in ("launch", "fallbackCover", "epic", "folder")},
             "genres": tidy_genres(((info.get(g["id"]) or {}).get("d") or {}).get("genres"))}
            for g in STATE["games"] if cfg["showUninstalled"] or g["installed"]]


# ---------------------------------------------------------------- launching
# ---------------------------------------------------------------- album: Still captures taken while playing
# Still (a screenshot/recording app) keeps every capture in its library. A play session runs from launch until the
# game's process exits (or, for Steam/Epic links, until the frontend is back in front); any Still capture taken during
# one belongs to that game, whether it came from the controller shortcut below or from Still's own keyboard shortcuts.
STILL_LIB = (os.path.expanduser("~/Library/Application Support/app.still.desktop/Library") if MAC
             else os.path.join(os.environ.get("APPDATA", ""), "app.still.desktop", "Library"))
SESSION_LOCK = threading.Lock()
ALBUM_THUMBS = os.path.join(DATA, "album-thumbs")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".gif")


def still_exe():
    p = program("/Applications/Still.app") if MAC else os.path.join(os.environ.get("LOCALAPPDATA", ""), "Still", "still.exe")
    return p if os.path.isfile(p) else None


def session_start(game_id):
    with SESSION_LOCK:
        sessions, now = load("sessions.json", []), time.time()
        for s in sessions:
            if not s.get("end"):
                s["end"] = now
        sessions.append({"game": game_id, "start": now, "end": None})
        store("sessions.json", sessions[-3000:])
    threading.Timer(0.3, warm_overlay).start()  # the in-game menu, ready before the game's window is up


def session_end(game_id=None, min_age=0):
    with SESSION_LOCK:
        sessions, now, changed, ended = load("sessions.json", []), time.time(), False, []
        for s in sessions:
            if not s.get("end") and (game_id is None or s["game"] == game_id) and now - s["start"] >= min_age:
                s["end"], changed = now, True
                ended.append(s)
        if changed:
            store("sessions.json", sessions)
    for s in ended:  # play time comes from sessions: they end however the game ends, even after the helper restarted
        record_play(s["game"], s["end"] - s["start"])


def open_session():
    return next((s for s in reversed(load("sessions.json", [])) if not s.get("end")), None)


def still_library():
    try:
        with open(os.path.join(STILL_LIB, "library.json"), encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return []
    # only well-formed entries: an id that is a plain folder name and a file name with no path in it
    return [e for e in entries if isinstance(e, dict) and re.fullmatch(r"[0-9a-fA-F-]{8,64}", str(e.get("id", "")))
            and re.fullmatch(r"[\w .-]+", str(e.get("fileName", ""))) and ".." not in e["fileName"]]


CAPTURES = os.path.join(DATA, "captures")
RECORD = {"proc": None, "entry": None}
ENCODER = [None]


def ffmpeg_path():
    if own_ffmpeg():  # the app's own copy (Settings › General › Video recording)
        return own_ffmpeg()
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe"))
    return hits[0] if hits else None


def video_encoder(ffmpeg):
    """The graphics card's encoder if there is one, so recording costs the game as little as possible. Tried once."""
    if ENCODER[0]:
        return ENCODER[0]
    for name, extra in (("h264_nvenc", ["-preset", "p3", "-cq", "23"]), ("h264_amf", ["-quality", "balanced", "-qp_i", "23", "-qp_p", "23"]),
                        ("h264_qsv", ["-preset", "faster", "-global_quality", "23"]), ("libx264", ["-preset", "ultrafast", "-crf", "23"]),
                        ("h264_mf", ["-hw_encoding", "1", "-b:v", "16M"]), ("h264_mf", ["-b:v", "16M"])):
        probe = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.1", "-c:v", name, "-f", "null", "-"],
                               capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if probe.returncode == 0:
            ENCODER[0] = (name, extra)
            return ENCODER[0]
    return None


def add_capture(entry):
    store("captures.json", load("captures.json", []) + [entry])


def take_capture(mode):
    """The frontend's own screenshots and video, kept in data/captures. Nothing here touches Still or any other capture tool."""
    if MAC:
        return None  # screenshots and recording from the in-game menu: not on a Mac yet
    session = open_session()
    if not session:
        return
    if mode == "record":
        return stop_recording() if RECORD["proc"] else start_recording(session["game"])
    from PIL import ImageGrab
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
    os.makedirs(CAPTURES, exist_ok=True)
    stamp = f"own-{int(time.time() * 1000)}"
    path = os.path.join(CAPTURES, stamp + ".png")
    shot = ImageGrab.grab()
    if shot.convert("L").getextrema()[1] < 8 and ffmpeg_path():  # all black: some games draw past Windows' screen copy
        subprocess.run([ffmpeg_path(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "ddagrab=framerate=10:draw_mouse=0,hwdownload,format=bgra",
                        "-frames:v", "1", path], capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not os.path.isfile(path):
        shot.save(path)
    add_capture({"id": stamp, "kind": "screenshot", "file": stamp + ".png", "created": time.time(), "game": session["game"], "duration": 0})


def speaker_audio(path, stop, info):
    """Write what the default speakers are playing to a raw file (Windows' WASAPI loopback), filling silences so it stays in time."""
    import ctypes
    from ctypes import wintypes as W

    def guid(text):
        g = ctypes.create_string_buffer(16)
        ctypes.windll.ole32.CLSIDFromString(text, g)
        return g

    def call(obj, slot, *types):
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[slot])

    class Format(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("tag", W.WORD), ("channels", W.WORD), ("rate", W.DWORD), ("bytes", W.DWORD), ("align", W.WORD), ("bits", W.WORD), ("extra", W.WORD)]

    ptr = ctypes.c_void_p
    ctypes.windll.ole32.CoInitialize(None)
    ctypes.windll.ole32.CoCreateInstance.argtypes = [ptr, ptr, W.DWORD, ptr, ptr]
    ctypes.windll.ole32.CoTaskMemFree.argtypes = [ptr]
    enum, dev, client, capture, mix = ptr(), ptr(), ptr(), ptr(), ptr()
    try:
        if ctypes.windll.ole32.CoCreateInstance(guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), None, 1, guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}"), ctypes.byref(enum)):
            return
        if call(enum, 4, ctypes.c_int, ctypes.c_int, ptr)(enum, 0, 1, ctypes.byref(dev)):
            return
        if call(dev, 3, ptr, W.DWORD, ptr, ptr)(dev, guid("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}"), 23, None, ctypes.byref(client)):
            return
        if call(client, 8, ptr)(client, ctypes.byref(mix)):
            return
        fmt = ctypes.cast(mix, ctypes.POINTER(Format)).contents
        rate, channels, align, bits, tag = fmt.rate, fmt.channels, fmt.align, fmt.bits, fmt.tag
        # shared mode, loopback, a one second buffer
        if call(client, 3, ctypes.c_int, W.DWORD, ctypes.c_longlong, ctypes.c_longlong, ptr, ptr)(client, 0, 0x00020000, 10000000, 0, mix, None):
            return
        if call(client, 14, ptr, ptr)(client, guid("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}"), ctypes.byref(capture)):
            return
        info.update(rate=rate, channels=channels, format="f32le" if tag == 3 or (tag == 0xFFFE and bits == 32) else f"s{bits}le")
        next_size = call(capture, 5, ptr)
        get = call(capture, 3, ptr, ptr, ptr, ptr, ptr)
        release = call(capture, 4, W.UINT)
        written = 0
        with open(path, "wb") as f:
            call(client, 10)(client)
            info["start"] = time.time()
            while not stop.is_set():
                size = W.UINT()
                if next_size(capture, ctypes.byref(size)) or not size.value:
                    behind = int((time.time() - info["start"]) * rate) - written
                    if behind > rate // 10:  # nothing playing: Windows sends nothing, so write the silence ourselves
                        f.write(bytes(behind * align))
                        written += behind
                    time.sleep(0.01)
                    continue
                data, frames, flags = ptr(), W.UINT(), W.DWORD()
                if get(capture, ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags), None, None):
                    break
                f.write(bytes(frames.value * align) if flags.value & 2 else ctypes.string_at(data, frames.value * align))
                written += frames.value
                release(capture, frames.value)
            call(client, 11)(client)
    except (OSError, ValueError):
        pass
    finally:
        if mix:
            ctypes.windll.ole32.CoTaskMemFree(mix)
        for obj in (capture, client, dev, enum):
            if obj:
                call(obj, 2)(obj)


def start_recording(game):
    ffmpeg = ffmpeg_path()
    if not ffmpeg and WIN:  # the first time: the recorder is fetched (Settings › General shows it), and the next press records
        queue_extra("recorder")
        return
    encoder = video_encoder(ffmpeg) if ffmpeg else None
    if not encoder:
        return
    os.makedirs(CAPTURES, exist_ok=True)
    stamp = f"own-{int(time.time() * 1000)}"
    RECORD["entry"] = {"id": stamp, "kind": "video", "file": stamp + ".mp4", "created": time.time(), "game": game, "duration": 0}
    audio = {"file": os.path.join(CAPTURES, stamp + ".raw"), "stop": threading.Event(), "info": {}, "video_start": 0.0}
    audio["thread"] = threading.Thread(target=speaker_audio, args=[audio["file"], audio["stop"], audio["info"]], daemon=True)
    audio["thread"].start()
    deadline = time.time() + 1.5
    while "start" not in audio["info"] and time.time() < deadline and audio["thread"].is_alive():
        time.sleep(0.01)
    RECORD["audio"] = audio
    RECORD["proc"] = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-f", "lavfi", "-i", "ddagrab=framerate=60:draw_mouse=0,hwdownload,format=bgra",
                                       "-c:v", encoder[0], *encoder[1], "-pix_fmt", "yuv420p", "-t", "3600", os.path.join(CAPTURES, stamp + ".mp4")],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def watch(proc):
        """ffmpeg reports how much video it has: the first report dates the first frame, which lines the sound up."""
        for line in proc.stdout:
            if line.startswith(b"out_time_us=") and not audio["video_start"]:
                try:
                    done = int(line.split(b"=")[1]) / 1000000
                except ValueError:
                    continue
                if done > 0:
                    audio["video_start"] = time.time() - done
    threading.Thread(target=watch, args=[RECORD["proc"]], daemon=True).start()


def add_sound(ffmpeg, video, audio):
    """Join the recorded sound to the finished video. If anything goes wrong, the silent video is kept."""
    raw, info = audio["file"], audio["info"]
    try:
        if ffmpeg and "start" in info and os.path.getsize(raw) and audio["video_start"]:
            gap = audio["video_start"] - info["start"]  # above zero: the sound began first
            joined = video + ".joined.mp4"
            timing = ["-ss", f"{gap:.3f}"] if gap > 0 else ["-itsoffset", f"{-gap:.3f}"]
            done = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", video, "-f", info["format"], "-ar", str(info["rate"]), "-ac", str(info["channels"]), *timing, "-i", raw,
                                   "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", joined],
                                  capture_output=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if done.returncode == 0 and os.path.isfile(joined):
                os.replace(joined, video)
            elif os.path.isfile(joined):
                os.remove(joined)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if os.path.isfile(raw):
        os.remove(raw)


def stop_recording():
    proc, entry, audio = RECORD["proc"], RECORD["entry"], RECORD.get("audio")
    RECORD["proc"], RECORD["entry"] = None, None
    if not proc:
        return
    try:
        proc.stdin.write(b"q")  # asks ffmpeg to finish, so the file is playable
        proc.stdin.close()
        proc.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        proc.kill()
    audio["stop"].set()
    audio["thread"].join(3)
    entry["duration"] = time.time() - entry["created"]
    video = os.path.join(CAPTURES, entry["file"])
    if os.path.isfile(video):
        add_sound(ffmpeg_path(), video, audio)
        add_capture(entry)


def recycle(path):
    """To the Recycle Bin, so anything deleted from the album can be brought back."""
    if MAC:
        return trash_mac(path)
    import ctypes
    import ctypes.wintypes as W

    class Op(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("func", W.UINT), ("src", ctypes.c_wchar_p), ("dst", ctypes.c_wchar_p), ("flags", W.WORD),
                    ("aborted", W.BOOL), ("mappings", ctypes.c_void_p), ("title", ctypes.c_wchar_p)]
    op = Op(None, 3, path + chr(0), None, 0x0454, False, None, None)  # FO_DELETE; silent, no prompt, undoable, no error box
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.aborted and not os.path.exists(path)


def delete_capture(capture_id):
    own = load("captures.json", [])
    entry = next((e for e in own if e["id"] == capture_id), None)
    if entry:
        path = os.path.join(CAPTURES, os.path.basename(entry["file"]))
        if os.path.exists(path) and not recycle(path):
            raise ValueError("That couldn't be moved to the Recycle Bin")
        store("captures.json", [e for e in own if e["id"] != capture_id])
    else:
        if not any(e["id"] == capture_id for e in still_library()):
            raise ValueError("That capture wasn't found")
        folder = os.path.realpath(os.path.join(STILL_LIB, capture_id))
        if not folder.startswith(os.path.realpath(STILL_LIB) + os.sep) or (os.path.exists(folder) and not recycle(folder)):
            raise ValueError("That couldn't be moved to the Recycle Bin")
        index = os.path.join(STILL_LIB, "library.json")
        with open(index, encoding="utf-8") as f:
            entries = json.load(f)
        tmp = index + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([e for e in entries if not (isinstance(e, dict) and e.get("id") == capture_id)], f)
        os.replace(tmp, index)
    thumb = os.path.join(ALBUM_THUMBS, capture_id + ".jpg")
    if os.path.isfile(thumb):
        os.remove(thumb)


def album():
    sessions, now, out = load("sessions.json", []), time.time(), []
    for e in load("captures.json", []):
        g = STATE["byId"].get(e["game"]) or {}
        if os.path.isfile(os.path.join(CAPTURES, os.path.basename(e["file"]))):
            out.append({"id": e["id"], "kind": e["kind"], "created": e["created"], "game": e["game"], "title": g.get("title") or "Game",
                        "cover": g.get("cover", ""), "duration": e.get("duration") or 0})
    for e in still_library():
        if not os.path.isfile(os.path.join(STILL_LIB, e["id"], e["fileName"])):
            continue  # deleted here while Still was open, so its list came back
        t = (e.get("created") or 0) / 1000
        s = next((s for s in reversed(sessions) if s["start"] - 2 <= t <= (s.get("end") or now) + 2), None)
        if not s:
            continue  # taken outside a game (desktop screenshots stay in Still only)
        g = STATE["byId"].get(s["game"]) or {}
        video = e.get("kind") != "screenshot" or e["fileName"].lower().endswith(VIDEO_EXT)
        out.append({"id": e["id"], "kind": "video" if video else "screenshot", "created": t, "game": s["game"],
                    "title": g.get("title") or "Unknown game", "cover": g.get("cover", ""), "width": e.get("width"),
                    "height": e.get("height"), "duration": e.get("duration") or 0})
    out.sort(key=lambda c: -c["created"])
    return out


def album_file(capture_id):
    own = next((e for e in load("captures.json", []) if e["id"] == capture_id), None)
    if own:
        path = os.path.join(CAPTURES, os.path.basename(own["file"]))
        return path if os.path.isfile(path) else None
    e = next((e for e in still_library() if e["id"] == capture_id), None)
    if not e:
        return None
    path = os.path.realpath(os.path.join(STILL_LIB, e["id"], e["fileName"]))
    return path if path.startswith(os.path.realpath(STILL_LIB) + os.sep) and os.path.isfile(path) else None


def album_thumb(capture_id):
    """A small JPEG for the album grid: a scaled-down screenshot, or a frame from a recording (ffmpeg)."""
    src = album_file(capture_id)
    if not src:
        return None
    os.makedirs(ALBUM_THUMBS, exist_ok=True)
    out = os.path.join(ALBUM_THUMBS, capture_id + ".jpg")
    if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    if src.lower().endswith(VIDEO_EXT):
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            return None
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "1", "-i", src, "-frames:v", "1", "-vf", "scale=640:-2", out],
                       capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out if os.path.isfile(out) else None
    from PIL import Image
    with Image.open(src) as im:
        im.thumbnail((640, 640))
        im.convert("RGB").save(out, "JPEG", quality=82)
    return out


XINPUT_START, XINPUT_BACK, XINPUT_LB, XINPUT_RB, XINPUT_GUIDE = 0x0010, 0x0020, 0x0100, 0x0200, 0x0400


def frontend_exe():
    return sys.executable if getattr(sys, "frozen", False) else os.path.join(ROOT, "Game Frontend.exe")


STARTUP_MODES = ("background", "open", "off")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command(mode):
    """What Windows runs at sign-in: the helper alone ("background": the Xbox/Steam button and the tray can open the window
    any time), or the helper and then the window ("open")."""
    return {"background": f'"{frontend_exe()}" --background', "open": f'"{frontend_exe()}" --background --open'}.get(mode)


def autostart_copy():
    """Only the copy that's really used writes the sign-in entry: not a source run, a build in the project folder or a
    test copy on another port, which would take the entry from it."""
    return (WIN or MAC) and getattr(sys, "frozen", False) and not os.path.isdir(os.path.join(ROOT, ".git")) and PORT == 8137


SETUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UltraFrontEnd"  # Settings > Apps entry (setup_ui.py)


def note_installed_version():
    """Settings > Apps shows the version Setup installed: after this copy updates itself, it shows this one instead."""
    if not getattr(sys, "frozen", False):
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETUP_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            where = str(winreg.QueryValueEx(k, "InstallLocation")[0]).rstrip("\\/")
            if os.path.normcase(os.path.abspath(where)) == os.path.normcase(os.path.abspath(ROOT)):
                winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
    except OSError:
        pass


def message_box(text, flags):
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, text, "Ultra Front End", flags | 0x10000 | 0x40000)  # foreground, topmost


def set_autostart(mode):
    if not autostart_copy():
        return
    if MAC:
        return set_autostart_mac(mode)
    import winreg
    command = startup_command(mode)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        for name in ("Game Frontend",) + (() if command else ("Ultra Front End",)):  # the old name, and the entry itself when off
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
        if command:
            winreg.SetValueEx(k, "Ultra Front End", 0, winreg.REG_SZ, command)


# ---------- games kept on screen when the in-game menu opens ----------
# SDL games (and so many Steam games) minimize as they lose the focus, which the in-game menu takes. Programs started from
# here are told not to (top of this file); games Steam starts only hear it from the Windows account's own settings, so
# Settings › General › Keep games on screen (on unless turned off) puts it there, and turning it off takes it away again.
SDL_KEEP = "SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"


def keep_on_screen(on):
    """Set or clear SDL's switch in the Windows account's environment (HKCU\\Environment), and tell Windows, so programs
    started from now on get it. Leaves a value someone set to something else alone. Returns True if it changed."""
    if not WIN:
        return False
    import ctypes
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                current = str(winreg.QueryValueEx(k, SDL_KEEP)[0])
            except OSError:
                current = None
            if on and current is None:
                winreg.SetValueEx(k, SDL_KEEP, 0, winreg.REG_SZ, "0")
            elif not on and current == "0":
                winreg.DeleteValue(k, SDL_KEEP)
            else:
                return False
    except OSError:
        return False
    result = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(ctypes.c_void_p(0xFFFF), 0x001A, 0, "Environment", 0x0002, 3000, ctypes.byref(result))  # WM_SETTINGCHANGE, to every window
    return True


def sync_keep_on_screen():
    """At start: the account's setting follows Settings (on unless turned off)."""
    if WIN and getattr(sys, "frozen", False) and "--port" not in sys.argv:
        keep_on_screen(config().get("keepOnScreen", True))


# ---------- emulators in borderless fullscreen ----------
# A game in exclusive fullscreen minimizes as the in-game menu takes the focus (the game pauses while the menu opens).
# Just before an emulator starts (its settings file closed), a setting that allows exclusive fullscreen is switched to
# borderless: only a line already in the file changes, nothing is added, and the file is copied to <name>.bak-borderless
# the first time. Part of Settings › General › Keep games on screen.
BORDERLESS = [  # (emulator program pattern, settings files near the program or in the user's folders, line pattern, replacement)
    (r"^rpcs3", ["{dir}/config/config.yml", "{dir}/config.yml"], r"^(\s*Exclusive Fullscreen Mode:\s*)(Automatic|Enable)\s*$", r"\g<1>Disable"),
    (r"eden|eglantine|yuzu|suyu|sudachi|citron", ["{appdata}/eglantine/config/qt-config.ini", "{appdata}/eden/config/qt-config.ini",  # (newer Eglantine has its own folder)
                                                 "{appdata}/yuzu/config/qt-config.ini", "{dir}/user/config/qt-config.ini"],
     r"^(fullscreen_mode=)1\s*$", r"\g<1>0"),  # 0 borderless windowed, 1 exclusive
    (r"^dolphin", ["{appdata}/Dolphin Emulator/Config/GFX.ini", "{dir}/User/Config/GFX.ini"], r"^(BorderlessFullscreen\s*=\s*)False\s*$", r"\g<1>True"),
    (r"^duckstation", ["{documents}/DuckStation/settings.ini", "{dir}/settings.ini"], r"^(ExclusiveFullscreenControl\s*=\s*)(Automatic|Allowed)\s*$", r"\g<1>Disallowed"),
    (r"^pcsx2", ["{documents}/PCSX2/inis/PCSX2.ini", "{dir}/inis/PCSX2.ini"], r"^(ExclusiveFullscreenControl\s*=\s*)(-1|1)\s*$", r"\g<1>0"),
    (r"^retroarch", ["{dir}/retroarch.cfg"], r'^(video_windowed_fullscreen\s*=\s*)"false"\s*$', r'\g<1>"true"'),
]


def make_borderless(program):
    """Switch this emulator's own settings to borderless fullscreen where they'd allow exclusive. Returns the files changed."""
    name = os.path.basename(program or "").lower()
    places = {"dir": os.path.dirname(program or ""), "appdata": os.environ.get("APPDATA", ""), "documents": os.path.join(os.path.expanduser("~"), "Documents")}
    changed = []
    for pattern, files, line, repl in BORDERLESS:
        if not re.search(pattern, name):
            continue
        for f in files:
            path = os.path.normpath(f.format(**places))
            try:
                with open(path, encoding="utf-8", newline="") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            new = re.sub(line, repl, text, flags=re.M)
            if new == text:
                continue
            try:
                if not os.path.exists(path + ".bak-borderless"):
                    shutil.copy2(path, path + ".bak-borderless")
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(new)
                changed.append(path)
            except OSError:
                pass
    return changed


def sync_autostart():
    """Keep the sign-in entry pointing at this exe, wherever it has been moved since, once setup has been through it."""
    if not autostart_copy() or not profile().get("setupDone"):
        return
    if MAC:
        return set_autostart(config().get("startup"))
    import winreg
    mode = config().get("startup")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            current = winreg.QueryValueEx(k, "Ultra Front End")[0]
    except OSError:
        current = None
    if current != startup_command(mode):
        set_autostart(mode)


RUNNING = {}  # game id -> the process its launch started (a launcher may hand over to a child, see process_tree)
SEEN_PIDS = {}  # that process' pid -> {every descendant seen: when it started}, since a launcher that exits cuts the game off from it (game_tree)


def process_birth(pid):
    """When this process started, or 0 if it has gone. Windows reuses pids, so a pid alone doesn't say it is still the same program."""
    if MAC:
        return plat_mac.process_birth(pid)
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return 0
    times = [ctypes.c_ulonglong() for _ in range(4)]
    ok = k32.GetProcessTimes(h, *[ctypes.byref(x) for x in times])
    code = ctypes.c_ulong()
    live = k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259  # STILL_ACTIVE
    k32.CloseHandle(h)
    return times[0].value if ok and live else 0


def process_tree(pid):
    """The launched process and its descendants that are still running (launchers hand over to the game itself)."""
    if MAC:
        return plat_mac.process_tree(pid)
    import ctypes
    import ctypes.wintypes as W

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", W.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e, parents = Entry(), {}
    e.dwSize = ctypes.sizeof(Entry)
    if k32.Process32FirstW(snap, ctypes.byref(e)):
        while True:
            parents[e.th32ProcessID] = e.th32ParentProcessID
            if not k32.Process32NextW(snap, ctypes.byref(e)):
                break
    k32.CloseHandle(snap)
    tree = {pid}  # even if it has exited: its children still name it as their parent
    while True:
        more = {p for p, pp in parents.items() if pp in tree and p not in tree}
        if not more:
            break
        tree |= more
    return tree & set(parents)


SPAWN_LOCK = threading.Lock()
PORT_DIRS = {}  # launched pid -> the folder of a PC port


# Games should be started by the frontend window when it's open: Steam only gives a Steam Controller to programs it started
# itself and their children, and the helper in the tray isn't one. The window asks for work at /api/spawn/next.
SPAWN = {"cond": threading.Condition(), "jobs": [], "seen": 0.0, "done": {}, "next": 0}


class WindowProcess:
    """A game the frontend window started, with the part of Popen the helper uses."""
    def __init__(self, pid):
        self.pid, self.birth = pid, process_birth(pid)

    def poll(self):
        return None if self.birth and process_birth(self.pid) == self.birth else 0

    def wait(self):
        while self.poll() is None:
            time.sleep(1)


def spawn_via_window(cmd, cwd):
    with SPAWN["cond"]:
        if time.time() - SPAWN["seen"] > 25:
            return None
        SPAWN["next"] += 1
        job = SPAWN["next"]
        SPAWN["jobs"].append({"id": job, "cmd": cmd, "cwd": cwd})
        SPAWN["cond"].notify_all()
        SPAWN["cond"].wait_for(lambda: job in SPAWN["done"], timeout=6)
        pid = SPAWN["done"].pop(job, 0)
    return WindowProcess(pid) if pid else None


def spawn_next():
    """Long poll for the frontend window: the next program to start."""
    with SPAWN["cond"]:
        SPAWN["seen"] = time.time()
        SPAWN["cond"].wait_for(lambda: SPAWN["jobs"], timeout=20)
        SPAWN["seen"] = time.time()
        return SPAWN["jobs"].pop(0) if SPAWN["jobs"] else {}


def spawn_done(job, pid):
    with SPAWN["cond"]:
        SPAWN["done"][job] = pid
        SPAWN["cond"].notify_all()


def spawn(cmd, cwd, window=True):
    window = window and not re.search(r"azahar", os.path.basename(cmd[0]), re.I)  # it freezes at start under Steam's overlay
    proc = spawn_via_window(cmd, cwd) if WIN and window else None
    return proc or local_spawn(cmd, cwd)


def local_spawn(cmd, cwd):
    """Start a game. The packaged exe's unpack folder is on its DLL search path and children inherit it, so an emulator would
    load our vcruntime140.dll instead of the system's (RPCS3 refuses to run on it): clear that for the moment of starting."""
    bundle = getattr(sys, "_MEIPASS", None)
    if MAC:
        return subprocess.Popen(cmd, cwd=cwd, env=plat_mac.child_env() if bundle else None)
    if not (WIN and bundle):
        return start_program(cmd, cwd)
    import ctypes
    # nor where it was unpacked: Steam started from here would hand that on to the frontend it launches, which would then run
    # from this copy's unpack folder and lose it when this copy goes
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}
    env["PATH"] = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if not p.startswith(bundle))
    set_dir = ctypes.windll.kernel32.SetDllDirectoryW
    set_dir.argtypes = [ctypes.c_wchar_p]
    with SPAWN_LOCK:
        set_dir(None)
        try:
            return start_program(cmd, cwd, env)
        finally:
            set_dir(bundle)


def start_program(cmd, cwd, env=None):
    """Popen, or for a program that insists on running as administrator (Windows refuses it with error 740), Windows'
    "Run as administrator", which asks first. Either way the game is followed while it runs."""
    try:
        return subprocess.Popen(cmd, cwd=cwd, env=env)
    except OSError as e:
        if not WIN or getattr(e, "winerror", 0) != 740:
            raise
    return run_as_admin(cmd, cwd)


def run_as_admin(cmd, cwd):
    import ctypes
    import ctypes.wintypes as W

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("fMask", W.ULONG), ("hwnd", W.HWND), ("lpVerb", W.LPCWSTR), ("lpFile", W.LPCWSTR), ("lpParameters", W.LPCWSTR),
                    ("lpDirectory", W.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", W.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", W.LPCWSTR),
                    ("hkeyClass", W.HKEY), ("dwHotKey", W.DWORD), ("hIcon", W.HANDLE), ("hProcess", W.HANDLE)]
    shell, k32 = ctypes.WinDLL("shell32", use_last_error=True), ctypes.WinDLL("kernel32")
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(Info)]
    k32.GetProcessId.argtypes = k32.CloseHandle.argtypes = [W.HANDLE]
    info = Info(cbSize=ctypes.sizeof(Info), fMask=0x40 | 0x100, lpVerb="runas", lpFile=cmd[0], lpParameters=subprocess.list2cmdline(cmd[1:]),
                lpDirectory=cwd or None, nShow=1)  # NOCLOSEPROCESS | NOASYNC, shown normally
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        if ctypes.get_last_error() == 1223:
            raise ValueError("This game needs administrator rights, and Windows' permission prompt was cancelled")
        raise ValueError("This game needs administrator rights, and Windows couldn't start it that way")
    try:
        pid = k32.GetProcessId(info.hProcess)
    finally:
        k32.CloseHandle(info.hProcess)
    return WindowProcess(pid)


def folder_processes(folder):
    """Running programs whose exe lives in this folder or below it."""
    if MAC:
        return plat_mac.folder_processes(folder)
    import ctypes
    import ctypes.wintypes as W
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, W.DWORD, ctypes.c_wchar_p, ctypes.POINTER(W.DWORD)]
    pids, got = (W.DWORD * 4096)(), W.DWORD()
    ctypes.windll.psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got))
    root, found = os.path.normcase(folder.rstrip("\\/")) + os.sep, set()
    for pid in pids[:got.value // 4]:
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            buf, n = ctypes.create_unicode_buffer(1024), W.DWORD(1024)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and os.path.normcase(buf.value).startswith(root):
                found.add(pid)
            k32.CloseHandle(h)
    return found


def game_tree(pid):
    """Everything still running from a launch, following the game after its launcher has exited."""
    if not WIN and not MAC:
        return set()
    seen = SEEN_PIDS.setdefault(pid, {pid: process_birth(pid)})

    def follow():
        for p, born in list(seen.items()):
            now = process_birth(p)
            if now != born or not now:
                seen.pop(p, None)  # exited, or its pid now belongs to some other program (two threads walk this)
                if now:
                    continue
            found = {q: process_birth(q) for q in process_tree(p)}  # an exited launcher's children still name it as their parent
            seen.update({q: at for q, at in found.items() if not at or at >= born})
    follow()
    if not seen and pid in PORT_DIRS:  # a launcher gone before its child could be followed: look for the port's own programs
        seen.update({q: process_birth(q) for q in folder_processes(PORT_DIRS[pid])})
        follow()
    return set(seen)


def wait_game(game, proc, start):
    """Runs until the game has really ended: a launcher exiting isn't the game exiting."""
    last = time.time()
    while True:  # often at first: a launcher can be gone in moments, and its children are only found from a pid seen in time
        if game_tree(proc.pid) or proc.poll() is None:
            last = time.time()
        elif time.time() - last > 3:
            break
        time.sleep(0.2 if time.time() - start < 30 else 2)
    record_play(game["id"])  # last played; the time itself is counted when its session ends (session_end)
    if RUNNING.get(game["id"]) is proc:  # not if the game has been started again meanwhile
        del RUNNING[game["id"]]
        session_end(game["id"])
    SEEN_PIDS.pop(proc.pid, None)


FOCUS = [0]
LAUNCHING = set()  # games whose launch screen is still up; the page asks /api/launching


EXITED_EARLY, LAUNCH_CANCEL = set(), set()


def hold_until_fullscreen(game_id, pid, timeout=25):
    """Keep the frontend's launch screen on top, hiding emulator and launcher windows, until the game fills the screen."""
    if not WIN:
        return LAUNCHING.discard(game_id)
    import ctypes
    import ctypes.wintypes as W
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
    frontend = frontend_window()
    if frontend:
        user32.SetWindowPos(frontend, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    w, h = screen_size()

    def fullscreen_window(tree):
        found = []

        def cb(hwnd, _):
            p, r = ctypes.c_ulong(), W.RECT()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(p))
            user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
            if p.value in tree and user32.IsWindowVisible(ctypes.c_void_p(hwnd)) and r.right - r.left >= w and r.bottom - r.top >= h:
                found.append(hwnd)
            return True
        user32.EnumWindows(proto(cb), 0)
        return found[0] if found else None

    def run():
        deadline, window = time.time() + timeout, None
        while time.time() < deadline and not window and game_id not in LAUNCH_CANCEL:
            time.sleep(0.25)
            tree = game_tree(pid)
            if not tree and time.time() > deadline - timeout + 5:
                EXITED_EARLY.add(game_id)  # gone in 5 s with no window: the launch screen says so
                break
            window = fullscreen_window(tree)
        time.sleep(0.6 if window else 0)  # let it draw its first frame
        if frontend:
            user32.SetWindowPos(frontend, ctypes.c_void_p(-2), 0, 0, 0, 0, 0x0013)  # HWND_NOTOPMOST
        if window:
            take_foreground(window)
            behind_game(frontend, window)
        LAUNCHING.discard(game_id)
        if game_id in LAUNCH_CANCEL:  # B on the launch screen: leave the game where it is
            return LAUNCH_CANCEL.discard(game_id)
        focus_process(pid, timeout=8)
    threading.Thread(target=run, daemon=True).start()


RUN_NOW = {}  # game id -> (window, process id), kept current by watch_running
RUN_DIRS = [0.0, {}]


def game_folders():
    """Install folder -> game id, for spotting games however they were started. Refreshed once a minute."""
    if time.time() - RUN_DIRS[0] < 60:
        return RUN_DIRS[1]
    found, sp = {}, steam_path()
    add = lambda path, game: found.__setitem__(os.path.normcase(os.path.normpath(path)) + os.sep, game)
    libs = [sp] if sp else []
    if sp:
        try:
            for v in (ci(vdf(read(os.path.join(sp, "steamapps", "libraryfolders.vdf"))), "libraryfolders") or {}).values():
                if isinstance(v, dict) and v.get("path"):
                    libs.append(v["path"])
        except OSError:
            pass
    ids = {str(g.get("appid")): g["id"] for g in STATE["games"] if g.get("appid")}
    for lib in dict.fromkeys(os.path.normcase(os.path.normpath(p)) for p in libs):
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                st = ci(vdf(read(acf)), "AppState") or {}
            except OSError:
                continue
            if ids.get(str(ci(st, "appid"))) and ci(st, "installdir"):
                add(os.path.join(lib, "steamapps", "common", ci(st, "installdir")), ids[str(ci(st, "appid"))])
    for item in glob.glob(os.path.join(EPIC_DIR, "**", "*.item"), recursive=True):
        try:
            m = json.loads(read(item))
            if m.get("InstallLocation") and f"epic-{m.get('AppName')}" in STATE["byId"]:
                add(m["InstallLocation"], f"epic-{m['AppName']}")
        except (OSError, ValueError):
            pass
    for g in STATE["games"]:
        L = g.get("launch") or {}
        if g.get("folder"):
            add(g["folder"], g["id"])
        elif L.get("type") == "exe" and not L.get("noFolder") and len(os.path.dirname(L.get("exe", ""))) > 12:  # never a whole drive or Windows itself
            add(os.path.dirname(L["exe"]), g["id"])
    RUN_DIRS[0], RUN_DIRS[1] = time.time(), found
    return found


def watch_running():
    """Which games have a window open, started from here or not: by install folder, plus anything this helper started."""
    import ctypes
    import ctypes.wintypes as W
    user32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, W.DWORD, ctypes.c_wchar_p, ctypes.POINTER(W.DWORD)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def image(pid):
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return ""
        buf, size = ctypes.create_unicode_buffer(1024), W.DWORD(1024)
        ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        k32.CloseHandle(h)
        return os.path.normcase(buf.value) if ok else ""

    while True:
        time.sleep(3)
        try:
            windows = []

            def cb(hwnd, _):
                p, r = ctypes.c_ulong(), W.RECT()
                h = ctypes.c_void_p(hwnd)
                user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                user32.GetWindowRect(h, ctypes.byref(r))
                if user32.IsWindowVisible(h) and (user32.IsIconic(h) or (r.right - r.left >= 300 and r.bottom - r.top >= 200)):
                    windows.append((hwnd, p.value))
                return True
            user32.EnumWindows(proto(cb), 0)
            folders, now = game_folders(), {}
            paths = {pid: image(pid) for pid in {w[1] for w in windows}}
            for hwnd, pid in windows:
                hit = max((d for d in folders if paths[pid].startswith(d)), key=len, default=None)
                if hit and "game frontend" not in paths[pid]:
                    now.setdefault(folders[hit], (hwnd, pid))
            for game, proc in list(RUNNING.items()):
                tree = game_tree(proc.pid)
                if tree and game not in now:
                    window = next((w for w in windows if w[1] in tree), None)
                    now[game] = window or (None, proc.pid)
            RUN_NOW.clear()
            RUN_NOW.update(now)
            if RECORD["proc"] and RECORD["entry"]["game"] not in now and time.time() - RECORD["entry"]["created"] > 10:
                stop_recording()  # the game has closed
        except Exception:
            pass


def hud_visible():
    """Only over a game: not on the frontend, and not behind the in-game menu."""
    return bool(RUN_NOW) and not overlay_open() and not frontend_in_front()


def hud_installed():
    import hud
    return bool(hud.presentmon(DATA))


def hud_mode(cycle=False):
    import hud
    if cycle:
        hud.MODE[0] = hud.MODES[(hud.MODES.index(hud.MODE[0]) + 1) % len(hud.MODES)]
        store("hud.json", {"mode": hud.MODE[0]})
    return hud.MODE[0]


def running_resume(game_id):
    if MAC:
        entry = RUN_NOW.get(game_id)
        return bool(entry) and plat_mac.activate(entry[1])
    import ctypes
    hwnd = (RUN_NOW.get(game_id) or (None, 0))[0]
    if hwnd:
        if ctypes.windll.user32.IsIconic(ctypes.c_void_p(hwnd)):
            ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
        take_foreground(hwnd)
    return bool(hwnd)


def running_close(game_id):
    if MAC:
        entry = RUN_NOW.pop(game_id, None)
        if entry:
            plat_mac.kill_tree(entry[1])
        return session_end(game_id)
    entry = RUN_NOW.pop(game_id, None)
    if entry:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(entry[1])], capture_output=True)
    session_end(game_id)


def hold_steam_launch(game_id, timeout=30):
    """Steam games: keep the launch screen over Steam's own windows until a window from the game's install folder appears.
    The timeout matters: if Steam itself is asking something (a cloud conflict, say), it comes into view by then."""
    import ctypes
    import ctypes.wintypes as W
    user32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, W.DWORD, ctypes.c_wchar_p, ctypes.POINTER(W.DWORD)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    frontend = frontend_window()
    if frontend:
        user32.SetWindowPos(frontend, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)  # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE

    def image(pid):
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        buf, size = ctypes.create_unicode_buffer(1024), W.DWORD(1024)
        ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        k32.CloseHandle(h)
        return buf.value.lower() if ok else ""

    def game_window():
        found = []

        def cb(hwnd, _):
            p, r = ctypes.c_ulong(), W.RECT()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(p))
            user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
            if user32.IsWindowVisible(ctypes.c_void_p(hwnd)) and r.right - r.left >= 600 and r.bottom - r.top >= 300 and "steamapps" in image(p.value):
                found.append(hwnd)
            return True
        user32.EnumWindows(proto(cb), 0)
        return found[0] if found else None

    def run():
        deadline, window = time.time() + timeout, None
        while time.time() < deadline and not window:
            time.sleep(0.3)
            window = game_window()
        time.sleep(0.6 if window else 0)  # let it draw its first frame
        if frontend:
            user32.SetWindowPos(frontend, ctypes.c_void_p(-2), 0, 0, 0, 0, 0x0013)  # HWND_NOTOPMOST
        if window:
            take_foreground(window)
            behind_game(frontend, window)
        LAUNCHING.discard(game_id)
    threading.Thread(target=run, daemon=True).start()


def take_foreground(hwnd):
    """Windows refuses the foreground to a background program, unless it shares input with the window that has it."""
    if MAC:
        return plat_mac.activate(hwnd)  # on a Mac the 'window' is the program's pid
    import ctypes
    user32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.SetForegroundWindow.argtypes = user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    theirs, ours = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None), k32.GetCurrentThreadId()
    user32.keybd_event(0x12, 0, 0, OWN_KEYS)  # a tap of Alt also counts as this program's input
    user32.keybd_event(0x12, 0, 2, OWN_KEYS)
    attached = theirs and theirs != ours and user32.AttachThreadInput(ours, theirs, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(ours, theirs, False)


def behind_game(frontend, game):
    """Put the frontend's window just under the game's, now and again a moment later: dropping topmost lifts a window above
    every normal one, and some games make their real window after the first, so the game could end up underneath."""
    if MAC:
        return
    import ctypes
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    def place():
        if frontend and game and user32.IsWindow(ctypes.c_void_p(game)):
            user32.SetWindowPos(frontend, game, 0, 0, 0, 0, 0x0013)  # after the game's window; SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    place()
    threading.Timer(1.5, place).start()


def focus_process(pid, timeout=120):
    """Bring the launched game's window to the front once it exists. The helper runs in the background (the tray), and
    Windows won't let a background process' children take the foreground by themselves, so a game would open behind the
    fullscreen frontend. Keeps watching a few seconds after the first window for launchers that hand over to the game."""
    if MAC:
        return focus_process_mac(pid, timeout)
    if not WIN:
        return
    import ctypes
    import ctypes.wintypes as W
    user32 = ctypes.windll.user32
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def windows_of(pids):
        found = []

        def cb(hwnd, _):
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value in pids and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):  # top-level, not owned
                r = W.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                if r.right - r.left >= 300 and r.bottom - r.top >= 200:
                    found.append((hwnd, (r.right - r.left) * (r.bottom - r.top)))
            return True
        user32.EnumWindows(proto(cb), 0)
        return [h for h, _ in sorted(found, key=lambda x: -x[1])]

    FOCUS[0] += 1
    token = FOCUS[0]

    def run():
        # Only the latest request runs, or two windows pass the focus back and forth and the screen flickers. Each window is
        # brought forward once, plus a couple of tries if something else (Steam's menu) takes it back; never restored
        # unless minimized, since that alone makes a fullscreen window redraw.
        deadline, settled, shown, tries = time.time() + timeout, None, set(), 0
        while time.time() < deadline and FOCUS[0] == token and (settled is None or time.time() < settled):
            time.sleep(0.5)
            tree = game_tree(pid)
            if not tree:
                return
            wins = windows_of(tree)
            fg = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(fg))
            if not wins or fg.value in tree and wins[0] in shown:
                continue
            if wins[0] in shown and tries >= 2:
                return
            tries += wins[0] in shown
            hwnd = wins[0]
            if fg.value not in tree or hwnd not in shown:  # it can have the focus and still be under the frontend
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                take_foreground(hwnd)
            if settled is None or wins[0] not in shown:
                settled = time.time() + 20  # a launcher's window, or a slow emulator's, may give way to the game's: keep watching
            shown.add(hwnd)
    threading.Thread(target=run, daemon=True).start()


# ---------- in-game overlay ----------
# Hold View + Start in a game: a see-through topmost window opens over it, like Steam's, while the game keeps running. It's a
# second copy of the program with --overlay showing app/overlay.html.
OVERLAY = {"proc": None, "game": None, "pids": [], "opened": 0.0, "shown": False}
OVERLAY_LOCK = threading.Lock()
OVERLAY_COND = threading.Condition()  # the overlay process waits on this to be shown or hidden (/api/overlay/wake)


def overlay_alive():
    return OVERLAY["proc"] is not None and OVERLAY["proc"].poll() is None


def overlay_open():
    """The menu is on screen over the game (its process may also be waiting, hidden, for the next time)."""
    return overlay_alive() and OVERLAY["shown"]


def overlay_show(shown):
    with OVERLAY_COND:
        OVERLAY["shown"] = shown
        OVERLAY_COND.notify_all()


def overlay_process(warm):
    """Start the overlay program: warm (hidden, waiting) as a game starts, or shown at once if none was ready."""
    with OVERLAY_LOCK:
        if overlay_alive():
            return OVERLAY["proc"]
        proc = subprocess.Popen([frontend_exe(), "--overlay", *(["--warm"] if warm else [])], cwd=os.path.dirname(frontend_exe()))
        OVERLAY["proc"] = proc

    def wait():
        proc.wait()
        overlay_finish(proc)
    threading.Thread(target=wait, daemon=True).start()
    return proc


def warm_overlay():
    """Made ahead while the game is still starting (so no window of ours appears once it's playing): opening the menu
    is then only the slide."""
    if WIN and not MAC and getattr(sys, "frozen", False) and open_session() and not overlay_alive():
        overlay_process(warm=True)


def overlay_wake(want, timeout=25):
    """The overlay process asks: wait until the menu is wanted ("open") or put away ("hide"). "quit" once the game is over."""
    with OVERLAY_COND:
        OVERLAY_COND.wait_for(lambda: OVERLAY["shown"] == (want == "open"), timeout=timeout)
        if OVERLAY["shown"] == (want == "open"):
            return {want: True}
    if want == "open" and not open_session():
        return {"quit": True}
    return {"wait": True}


def fullscreen_process():
    """The process of the foreground window, if that window has no title bar and covers the whole screen."""
    if MAC:
        return plat_mac.fullscreen_pid()
    import ctypes
    import ctypes.wintypes as W
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = user32.GetForegroundWindow()
    r, pid = W.RECT(), ctypes.c_ulong()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    style = user32.GetWindowLongW(ctypes.c_void_p(hwnd), -16) & 0xFFFFFFFF
    w, h = screen_size()
    if own_window(hwnd):  # the frontend fills the screen too, but it's no game
        return 0
    return pid.value if r.right - r.left >= w and r.bottom - r.top >= h and not style & 0x00C00000 else 0


def toggle_overlay():
    """View + Start: open the overlay over the game being played, close it again, or just open the frontend if no game is."""
    if MAC:
        return open_frontend()  # no in-game menu window on a Mac yet: the frontend's own Quick Access instead
    if overlay_open():  # the overlay slides itself out, then resumes; closed here if it doesn't within a few seconds
        proc = OVERLAY["proc"]
        pad_emit("dismiss", "helper")
        threading.Timer(3, lambda: OVERLAY["proc"] is proc and overlay_open() and overlay_action("resume")).start()
        return
    adopt_game()
    session = open_session()
    running = RUNNING.get(session["game"]) if session else None
    tree = game_tree(running.pid) if running else set()
    if session and not tree:  # a launcher that handed over, or a store game: only a window filling the screen counts
        pid = fullscreen_process()
        tree = process_tree(pid) if pid else set()
    if not tree:
        return open_frontend()
    with OVERLAY_LOCK:
        OVERLAY.update(game=session["game"], pids=sorted(tree), opened=time.time())
    overlay_process(warm=False)  # the waiting one if there is one (it's woken below), else one shown straight away
    overlay_show(True)


def overlay_finish(proc=None):
    """Forget the overlay, once, however it ended."""
    with OVERLAY_LOCK:
        if proc is not None and OVERLAY["proc"] is not proc:
            return
        OVERLAY["pids"], OVERLAY["proc"] = [], None
    overlay_show(False)



# Keys that save a state in each emulator: (modifier, key) as virtual key codes, sent to the game, which keeps the focus.
STATE_KEYS = [(r"dolphin|mesen|melonds", (0x10, 0x70)), (r"azahar|lime3ds|citra", (0x11, 0x43))]  # Shift+F1, Ctrl+C


LOAD_KEYS = [(r"dolphin|mesen|melonds", (0x70,)), (r"azahar|lime3ds|citra", (0x11, 0x56))]  # F1, Ctrl+V


def state_keys(game_id, table=None):
    emu = os.path.basename((STATE["byId"].get(game_id) or {}).get("launch", {}).get("emu", "")).lower()
    return next((keys for pat, keys in (table or STATE_KEYS) if emu and re.search(pat, emu)), None)


def game_in_front(pids):
    """Make sure a save key would reach the game, which hands it the focus: the overlay holds it while it's up."""
    if MAC:
        return plat_mac.activate(pids[0]) if pids else False
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    tree = set(pids)
    for p in pids:
        tree |= process_tree(p)
    found = []

    def cb(hwnd, _):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in tree and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            found.append(hwnd)
        return True
    for _ in range(2):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        if pid.value in tree:
            return True
        user32.EnumWindows(proto(cb), 0)
        if found:
            take_foreground(found[0])
        time.sleep(0.4)
    return False


def press_keys(keys):
    if MAC:
        return None  # sending keys to another app needs macOS' Accessibility permission: not yet
    import ctypes
    user32 = ctypes.windll.user32
    # The modifier goes down well before the key: Dolphin takes F1 alone as Load, and one press with both at once does Save and Load.
    for vk in keys:
        user32.keybd_event(vk, user32.MapVirtualKeyW(vk, 0), 0, OWN_KEYS)
        time.sleep(0.12)
    for vk in reversed(keys):
        user32.keybd_event(vk, user32.MapVirtualKeyW(vk, 0), 2, OWN_KEYS)
        time.sleep(0.12)


NOW_PLAYING = r"""
[void][Windows.Foundation.IAsyncOperation`1,Windows.Foundation,ContentType=WindowsRuntime]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$as = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $as.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(3000) | Out-Null; $t.Result }
$mgrT = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
$propT = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties,Windows.Media.Control,ContentType=WindowsRuntime]
$streamT = [Windows.Storage.Streams.IRandomAccessStreamWithContentType,Windows.Storage.Streams,ContentType=WindowsRuntime]
$inT = [Windows.Storage.Streams.IInputStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$s = (Await ($mgrT::RequestAsync()) $mgrT).GetCurrentSession()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
if ($s) {
  $p = Await ($s.TryGetMediaPropertiesAsync()) $propT
  $art = ''
  try {  # the player's album art. PowerShell only reaches the stream as a .NET one through reflection, by its IInputStream side
    if ($p.Thumbnail) {
      $st = Await ($p.Thumbnail.OpenReadAsync()) $streamT
      $net = [System.IO.WindowsRuntimeStreamExtensions].GetMethod('AsStreamForRead', [type[]]@($inT)).Invoke($null, @($st))
      $ms = New-Object System.IO.MemoryStream
      $net.CopyTo($ms)
      if ($ms.Length -gt 0 -and $ms.Length -le 4MB) { $art = [Convert]::ToBase64String($ms.ToArray()) }
    }
  } catch {}
  @{ title = $p.Title; artist = $p.Artist; playing = ($s.GetPlaybackInfo().PlaybackStatus -eq 'Playing'); art = $art; app = $s.SourceAppUserModelId } | ConvertTo-Json -Compress
} else { '{}' }
"""
NP_ART = {"key": "", "data": b"", "type": ""}  # the latest album art, served at /api/nowplaying/art


def now_playing():
    """The song Windows' media controls show (Spotify, a browser, ...), for the overlay."""
    import base64
    code = base64.b64encode(NOW_PLAYING.encode("utf-16-le")).decode()
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", code], capture_output=True, timeout=8, creationflags=0x08000000)  # no console
        out = json.loads(r.stdout.decode("utf-8", "replace").strip() or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
    MEDIA_APP[0] = out.pop("app", "") or MEDIA_APP[0]
    art = out.pop("art", "") or ""
    if art:  # kept here and served by its own address: the page asks for it again only when the picture changes
        import hashlib
        try:
            data = base64.b64decode(art)
        except ValueError:
            data = b""
        if data:
            key = hashlib.sha1(data).hexdigest()[:12]
            if key != NP_ART["key"]:
                kind = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg" if data[:2] == b"\xff\xd8" else "image/bmp" if data[:2] == b"BM" else ""
                NP_ART.update(key=key, data=data, type=kind or "application/octet-stream")
            out["art"] = f"/api/nowplaying/art?v={key}"
    return out


def overlay_tip(title):
    """Once per game: a game seen to minimize when the menu opens (the overlay learns it, overlay-games.json) still pauses
    for a moment then, so the menu says how to stop that. Empty when there's nothing to say, or it was said before."""
    learned, said = load("overlay-games.json", {}), load("overlay-tips.json", [])
    exes = {os.path.basename(process_image(p) or "").lower() for p in OVERLAY["pids"]} - {""}
    exe = next((e for e in sorted(exes) if learned.get(e)), None)
    if not exe or exe in said:
        return ""
    store("overlay-tips.json", said + [exe])
    return (f"{title} pauses for a moment when this menu opens, because it runs in true fullscreen. "
            "Set it to borderless window in its own display settings to keep it running.")


def overlay_state(tip=False):
    g = STATE["byId"].get(OVERLAY["game"]) or {}
    session = open_session() or {}
    return {"open": overlay_open(), "title": g.get("title", "Game"), "cover": g.get("cover", ""), "minutes": g.get("minutes", 0),
            "session": int((time.time() - session.get("start", time.time())) / 60), "recording": bool(RECORD["proc"]), "hud": hud_mode() if hud_installed() else None, "savestate": bool(state_keys(OVERLAY["game"])),
            "battery": PAD_BATTERY[0] if time.time() - PAD_RAW[1] < 60 else None,
            **({"tip": overlay_tip(g.get("title", "This game"))} if tip and WIN else {})}


MEDIA_KEYS = {"media-prev": 0xB1, "media-play": 0xB3, "media-next": 0xB0}  # VK_MEDIA_PREV_TRACK, _PLAY_PAUSE, _NEXT_TRACK


def bring_back_game(pids):
    """The game's main window to the front, restored if it minimized itself: the biggest window of the game's processes,
    or a minimized one (which focus_process doesn't see). True if there was one."""
    if not WIN or not pids:
        return False
    import ctypes
    import ctypes.wintypes as W
    user32 = ctypes.WinDLL("user32")
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows.argtypes = [proto, ctypes.c_void_p]
    for f in (user32.IsWindowVisible, user32.IsIconic):
        f.argtypes = [ctypes.c_void_p]
    user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    tree = set()
    for p in pids:
        tree |= process_tree(p) or {p}
    found = []

    def cb(hwnd, _):
        if hwnd and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):
            pid, r = ctypes.c_ulong(), W.RECT()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in tree:
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                iconic = bool(user32.IsIconic(hwnd))
                found.append((not iconic, (r.right - r.left) * (r.bottom - r.top) if not iconic else 0, hwnd, iconic))
        return True
    user32.EnumWindows(proto(cb), 0)
    if not found:
        return False
    _, _, hwnd, iconic = max(found)
    if iconic:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    take_foreground(hwnd)
    return True


def overlay_action(action):
    proc, game, pids = OVERLAY["proc"], OVERLAY["game"], list(OVERLAY["pids"])
    if action in MEDIA_KEYS:  # the music in Windows' media controls (Spotify, a browser, ...): the keys work whatever has the focus
        return press_keys((MEDIA_KEYS[action],))
    if action in ("savestate", "loadstate"):  # the menu stays open
        keys = state_keys(game, LOAD_KEYS if action == "loadstate" else None)
        if game_in_front(pids):  # the game has to have the focus for its keys, then the overlay takes it back
            press_keys(keys or ())
            menu = frontend_window("Ultra Front End Overlay")
            if menu:
                take_foreground(menu)
        return None
    if proc is None:
        return
    if action != "close" and pids:  # the game in front first, so closing the overlay doesn't hand the focus to some other window
        bring_back_game(pids)
        time.sleep(0.1)
    if action == "close":  # the game's over: the menu goes with it
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        overlay_finish(proc)
    else:  # put away, ready for the next time: hidden by its own program (it waits on /api/overlay/wake)
        overlay_show(False)
    if action == "close":
        for pid in pids:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        session_end(game)
        open_frontend()
    elif pids:
        focus_process(pids[0], timeout=6)
        if action == "screenshot":
            threading.Timer(0.8, take_capture, ["screenshot"]).start()
        elif action == "record":  # after the overlay has gone, so it isn't in the video
            threading.Timer(0.8, take_capture, ["record"]).start()


OPENING = [0.0]


def steam_shortcut_id(running=True):
    """The frontend's id as a non-Steam game, if Steam is running (running=False: whether Steam has one at all). Opened through
    Steam, a Steam Controller acts as a gamepad; opened any other way it stays in Steam's desktop layout, as a mouse."""
    root = steam_path()
    if not root or (running and not folder_processes(root)):
        return 0
    exe = os.path.normcase(frontend_exe())
    for f in glob.glob(os.path.join(root, "userdata", "*", "config", "shortcuts.vdf")):
        try:
            with open(f, "rb") as fh:
                entries = re.findall(rb"\x02appid\x00(.{4})\x01AppName\x00([^\x00]*)\x00\x01Exe\x00([^\x00]*)\x00", fh.read(), re.S | re.I)
        except OSError:
            continue
        # the shortcut to this exe, whatever it's called in Steam; else one with the frontend's name
        for appid, name, target in sorted(entries, key=lambda e: os.path.normcase(e[2].decode("utf-8", "replace").strip('" ')) != exe):
            if os.path.normcase(target.decode("utf-8", "replace").strip('" ')) == exe or name.decode("utf-8", "replace").lower() in ("game frontend", "ultra front end"):
                return (int.from_bytes(appid, "little") << 32) | 0x02000000
    return 0




def black_cover(timeout=12):
    """A black screen while Steam starts the frontend, hiding Steam's launching popup. It lifts once the frontend's window
    is up, whose intro starts on black too. A plain Windows window, so it's there at once, and it can never outlast timeout."""
    if MAC:
        return
    import ctypes
    import ctypes.wintypes as W

    def run():
        user32 = ctypes.windll.user32
        user32.CreateWindowExW.restype = ctypes.c_void_p
        user32.CreateWindowExW.argtypes = [W.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        user32.DestroyWindow.argtypes = [ctypes.c_void_p]
        user32.PeekMessageW.argtypes = [ctypes.POINTER(W.MSG), ctypes.c_void_p, W.UINT, W.UINT, W.UINT]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        ctypes.windll.gdi32.GetStockObject.restype = ctypes.c_void_p
        ctypes.windll.kernel32.GetModuleHandleW.restype = ctypes.c_void_p

        class Kind(ctypes.Structure):
            _fields_ = [("style", W.UINT), ("proc", ctypes.c_void_p), ("extra", ctypes.c_int), ("window_extra", ctypes.c_int), ("module", ctypes.c_void_p), ("icon", ctypes.c_void_p),
                        ("cursor", ctypes.c_void_p), ("brush", ctypes.c_void_p), ("menu", ctypes.c_wchar_p), ("name", ctypes.c_wchar_p)]
        module = ctypes.windll.kernel32.GetModuleHandleW(None)
        # its own window kind with the true black brush: a Static's SS_BLACKRECT is the system's frame colour, which is grey
        user32.RegisterClassW(ctypes.byref(Kind(0, ctypes.cast(user32.DefWindowProcW, ctypes.c_void_p), 0, 0, module, None, None,
                                                ctypes.windll.gdi32.GetStockObject(4), None, "UltraFrontEndCover")))
        w, h = screen_size()
        # WS_EX_TOPMOST | WS_EX_TOOLWINDOW; WS_POPUP | WS_VISIBLE
        cover = user32.CreateWindowExW(0x88, "UltraFrontEndCover", None, 0x90000000, 0, 0, w, h, None, None, module, None)
        if not cover:
            return
        user32.ShowCursor(False)
        msg, deadline, seen = W.MSG(), time.time() + timeout, 0.0
        while time.time() < deadline:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            front = frontend_window()
            if front and user32.IsWindowVisible(front):
                seen = seen or time.time()
                if time.time() - seen > 0.7:  # let it paint its own black first
                    break
            time.sleep(0.02)
        user32.ShowCursor(True)
        user32.DestroyWindow(cover)
    threading.Thread(target=run, daemon=True).start()


def process_image(pid):
    """The exe a process runs, or "" if it can't be read."""
    if MAC:
        return plat_mac.process_image(pid)
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    buf, size = ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
    ok = k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(size))
    k32.CloseHandle(ctypes.c_void_p(h))
    return buf.value if ok else ""


def process_name(pid):
    return os.path.basename(process_image(pid)) or "?"


SYSTEM32 = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32")
POWERSHELL = os.path.join(SYSTEM32, "WindowsPowerShell", "v1.0", "powershell.exe")
# The command line and folder reach PowerShell as variables, so no path can break the script's quoting
START_ALONE = ("try { $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -ErrorAction Stop "
               "-Arguments @{CommandLine = $env:UFE_LINE; CurrentDirectory = $env:UFE_DIR}; exit [int]$r.ReturnValue } catch { exit 1 }")


def start_alone(args):
    """Start the exe as a program of its own, as if from the desktop: through WMI its parent isn't this process, so Steam
    doesn't count it as part of a window it launched, and it gets a clean environment (its own unpacked copy)."""
    if MAC:
        try:
            subprocess.Popen([frontend_exe()] + list(args), start_new_session=True, env=plat_mac.child_env())
            return True
        except OSError:
            return False
    env = dict(os.environ, UFE_LINE=subprocess.list2cmdline([frontend_exe()] + args), UFE_DIR=ROOT)
    try:
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(START_ALONE.encode("utf-16-le")).decode()],
                           capture_output=True, timeout=60, env=env, creationflags=0x08000000)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def own_window(hwnd):
    """Whether a window belongs to this program (the exe, or Python running it from source). Windows' shell keeps windows of
    its own titled like the page (Windows.Internal.Shell.TabProxyWindow, in explorer), and they outlive the frontend's
    window: looked up by title alone, one of those passes for the frontend, which then never opens."""
    if MAC:
        return False
    import ctypes
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    image = process_image(pid.value)
    # any exe in this program's folder (whatever it's named, and the .old.exe an update leaves running), or Python from source
    return bool(image) and (os.path.normcase(os.path.dirname(image)) == os.path.normcase(ROOT) or os.path.basename(image).lower().startswith("python"))


def frontend_window(title="Ultra Front End"):
    """The frontend's own top-level window with this exact title, or 0."""
    if MAC:
        return 0
    import ctypes
    user32 = ctypes.windll.user32
    user32.FindWindowExW.restype = ctypes.c_void_p
    user32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    hwnd = None
    while True:
        hwnd = user32.FindWindowExW(None, hwnd, None, title)
        if not hwnd or own_window(hwnd):
            return hwnd or 0


IN_FRONT = [0.0, False]  # checked often (every frame of the controller loop): the answer is kept a quarter second


def frontend_in_front():
    """Whether the frontend (or its in-game menu) is the window in front. While the frontend shows, Windows can report one of
    its shell windows with the same title as the active one (see own_window), so that counts when the frontend's own window
    is what's on screen."""
    if MAC:
        return plat_mac.front_pid() == os.getpid()
    if time.time() - IN_FRONT[0] < 0.25:
        return IN_FRONT[1]
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = user32.GetForegroundWindow()
    front = bool(hwnd) and foreground_title().startswith("Ultra Front End") and (own_window(hwnd) or on_screen(frontend_window()))
    IN_FRONT[0], IN_FRONT[1] = time.time(), front
    return front


def on_screen(hwnd):
    """Whether this window is the one showing in the middle of the screen (not minimized, nothing over it)."""
    if MAC:
        return False
    if not hwnd:
        return False
    import ctypes
    import ctypes.wintypes as W
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = user32.GetAncestor.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [W.POINT]
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    w, h = screen_size()
    return not user32.IsIconic(ctypes.c_void_p(hwnd)) and user32.GetAncestor(user32.WindowFromPoint(W.POINT(w // 2, h // 2)), 2) == hwnd  # GA_ROOT


def raise_window(hwnd, seconds=10):
    """Bring the frontend's own window to the front, restoring it if it was minimized (focus_process looks for a game's biggest
    window, which a minimized one never is). Keeps at it for a few seconds: Steam's own menu can open on the same press."""
    if MAC:
        return plat_mac.activate(os.getpid())
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    h = ctypes.c_void_p(hwnd)
    FOCUS[0] += 1  # and any game still being brought forward stops trying
    token = FOCUS[0]

    def run():
        deadline, tries = time.time() + seconds, 0
        while time.time() < deadline and tries < 3 and FOCUS[0] == token and user32.IsWindow(h):
            if user32.GetForegroundWindow() != h.value and not (frontend_in_front() and on_screen(h.value)):
                if user32.IsIconic(h):
                    user32.ShowWindow(h, 9)  # SW_RESTORE
                take_foreground(h.value)
                tries += 1
            time.sleep(0.5)
    threading.Thread(target=run, daemon=True).start()


def steam_windows():
    """Steam's own top-level windows on screen (its main window and chats): {hwnd: title}."""
    return windows_of("steamwebhelper.exe")


def windows_of(exe):
    """A program's top-level windows on screen, by its .exe name: {hwnd: title}."""
    import ctypes
    import ctypes.wintypes as W
    user32 = ctypes.WinDLL("user32")  # its own copy: these argtypes stay here
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows.argtypes = [proto, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    found = {}

    def cb(hwnd, _):
        if not hwnd or not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # on screen, top-level, not owned
            return True
        pid, r = ctypes.c_ulong(), W.RECT()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        if (user32.IsIconic(hwnd) or (r.right - r.left >= 300 and r.bottom - r.top >= 200)) and process_name(pid.value).lower() == exe:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            found[hwnd] = buf.value
        return True
    user32.EnumWindows(proto(cb), 0)
    return found


def open_in_steam(target, title="Steam", timeout=8):
    """Open a steam:// page and bring its window in front of the frontend. The helper isn't the program in front, so Windows
    opens Steam's window behind the fullscreen frontend, and pressing A seemed to do nothing. title: the window wanted (a
    friend's name for a chat; Steam's main window is called Steam). A window that wasn't there before wins: Steam made it for this."""
    if not WIN:
        return open_target(target)
    import ctypes
    user32 = ctypes.WinDLL("user32")  # its own copy: these argtypes stay here
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    before = steam_windows()
    FOCUS[0] += 1  # a frontend raise still going stops, so it doesn't pull the frontend back over Steam
    token = FOCUS[0]
    open_target(target)

    def run():
        deadline, start, shown = time.time() + (timeout if before else 60), time.time(), None  # Steam not open yet: starting and signing in takes a while
        while time.time() < deadline and FOCUS[0] == token:
            time.sleep(0.25)
            now = steam_windows()
            new = [h for h in now if h not in before]
            named = [h for h, t in now.items() if t == title] or [h for h, t in now.items() if title.lower() in t.lower()]
            pick = (new or (named if time.time() - start > 0.75 else []) or [None])[0]  # an old window: once Steam has had a moment to make a new one
            if not pick:
                continue
            if user32.GetForegroundWindow() == pick:
                if shown and time.time() - shown > 1.5:  # in front and staying there
                    return
                shown = shown or time.time()
                continue
            if user32.IsIconic(pick):
                user32.ShowWindow(pick, 9)  # SW_RESTORE
            take_foreground(pick)
            shown = None
    threading.Thread(target=run, daemon=True).start()


def open_frontend():
    """The Xbox button: bring the frontend's window to the front, or open it."""
    if MAC:
        return plat_mac.activate(os.getpid())  # the window lives in this process
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = frontend_window()
    if hwnd:
        import ctypes.wintypes
        pid, r = ctypes.c_ulong(), ctypes.wintypes.RECT()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        button_log(f"  raising the open window {hwnd:#x} of pid {pid.value} ({process_name(pid.value)}), visible={bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd)))} "
                   f"minimized={bool(user32.IsIconic(ctypes.c_void_p(hwnd)))} at {r.left},{r.top} {r.right - r.left}x{r.bottom - r.top}")
        raise_window(hwnd)
    elif not os.path.isfile(frontend_exe()) or time.time() - OPENING[0] <= 8:  # its window takes a moment: a double-click asks twice
        button_log("  already opening")
    else:
        OPENING[0] = time.time()
        game_id = steam_shortcut_id()
        button_log(f"  opening through {'Steam' if game_id else 'the exe'}")
        if not game_id:  # with its own unpacked copy: this helper's goes when the helper does, and a newer build replaces it
            proc = subprocess.Popen([frontend_exe()], cwd=os.path.dirname(frontend_exe()), env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1"))
            return focus_process(proc.pid, timeout=30)
        black_cover()
        time.sleep(0.05)  # on screen before Steam's popup can be
        open_target(f"steam://rungameid/{game_id}")

        def bring_forward():
            for _ in range(100):
                time.sleep(0.2)
                hwnd = frontend_window()
                if hwnd:
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    return focus_process(pid.value, timeout=10)
        threading.Thread(target=bring_forward, daemon=True).start()
# Menu navigation straight from XInput (Xbox pads, and the Steam Controller or any pad Steam Input presents as one), so the
# frontend works with a controller even when the browser's own gamepad support doesn't see it.
PAD_BUTTONS = {0x1000: "ok", 0x2000: "back", 0x8000: "options", 0x0010: "options", 0x0100: "prevTab", 0x0200: "nextTab"}  # Start, like Y: the game's menu
PAD_DIRS = {"up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008}
PAD = {"seq": 0, "events": [], "cond": threading.Condition(), "pads": 0, "seen": 0.0, "last": {}}
XSTATE = {}  # XInput slot: (when, buttons, lt, rt, lx, ly, rx, ry), the latest of each pad, for the controller tester


def pad_emit(action, src="xinput"):
    with PAD["cond"]:
        now = time.time()
        # A Steam Controller reaches us twice: through its own report and, in a game Steam started, as XInput. Its own report
        # wins while it's in use; the XInput copies (whose repeats fall at other moments) would move the highlight twice.
        if src == "steam":
            PAD["steam_seen"] = now
        elif src != "helper" and now - PAD.get("steam_seen", 0) < 1.5:
            return
        if now - PAD["last"].get(action, 0) < 0.08:
            return
        PAD["last"][action] = now
        PAD["seq"] += 1
        PAD["events"] = (PAD["events"] + [(PAD["seq"], action, overlay_open())])[-50:]  # each press goes to the overlay or the frontend, never both
        PAD["cond"].notify_all()


def pad_wait(after, overlay=False, timeout=20):
    """Long poll for the page: actions after `after`, waiting up to `timeout` seconds for the next one."""
    with PAD["cond"]:
        if after > PAD["seq"]:  # the page just opened, or the helper restarted: catch up without replaying old presses
            return {"seq": PAD["seq"], "actions": [], "pads": PAD["pads"]}
        PAD["cond"].wait_for(lambda: PAD["seq"] > after, timeout=timeout)
        return {"seq": PAD["seq"], "actions": [a for n, a, o in PAD["events"] if n > after and o == overlay], "pads": PAD["pads"]}


def watch_controller():
    """In a game, hold View (Back) and press RB for a Still screenshot, or LB to record. Read straight from XInput so it
    works while the game has the screen. Also ends link-launched sessions once the frontend is back in front."""
    import ctypes
    import ctypes.wintypes as W

    class Pad(ctypes.Structure):
        _fields_ = [("buttons", W.WORD), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte), ("lx", ctypes.c_short),
                    ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]

    class State(ctypes.Structure):
        _fields_ = [("packet", W.DWORD), ("pad", Pad)]
    try:
        xinput = ctypes.WinDLL("xinput1_4")
    except OSError:
        return
    try:
        get_state = xinput[100]  # XInputGetStateEx: like XInputGetState, but also reports the Xbox (guide) button
    except (AttributeError, OSError):
        get_state = xinput.XInputGetState
    user32 = ctypes.windll.user32
    held, last_fire, last_fg, last_open, front, repeat, combo, zoom_at = {}, 0.0, 0.0, 0.0, False, {}, {}, 0.0
    while True:
        time.sleep(0.016 if front else 0.04)
        now = time.time()
        n = user32.GetWindowTextLengthW(user32.GetForegroundWindow())
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(user32.GetForegroundWindow(), title, n + 1)
        front = title.value.startswith("Ultra Front End") and frontend_in_front()
        if front and now - last_fg > 2:  # the frontend is in front again: a game started through a link has ended
            last_fg = now
            session = open_session()
            running = RUNNING.get(session["game"]) if session else None
            alive = overlay_open() or (session and session["game"] in RUN_NOW)  # the in-game menu is up, or the game's window is still open (say the helper restarted while it ran)
            if not (running and game_tree(running.pid)) and not alive:  # a slow game can still be loading behind the frontend
                session_end(min_age=20)
        pads, dirs = 0, set()
        for i in range(4):
            st = State()
            if get_state(i, ctypes.byref(st)) != 0:
                held.pop(i, None)
                XSTATE.pop(i, None)
                continue
            pads += 1
            b, was = st.pad.buttons, held.get(i, 0)
            held[i] = b
            XSTATE[i] = (now, b, st.pad.lt, st.pad.rt, st.pad.lx, st.pad.ly, st.pad.rx, st.pad.ry)
            pressed = b & ~was
            if b & XINPUT_BACK and pressed & (XINPUT_RB | XINPUT_LB) and now - last_fire > 1 and open_session():
                last_fire = now
                threading.Thread(target=take_capture, args=["record" if pressed & XINPUT_LB else "screenshot"], daemon=True).start()
            # The Xbox button opens the frontend, but Steam keeps that button for itself while it runs (and a Steam
            # Controller's Steam button always), so holding View + Start does the same and gets through Steam Input.
            chord = b & XINPUT_BACK and b & XINPUT_START
            if (not front or overlay_open()) and config().get("guideOpens") and (pressed & XINPUT_GUIDE or chord) and now - last_open > 2:
                last_open = now
                toggle_overlay()
            if b & XINPUT_BACK and pressed & ~XINPUT_BACK:
                combo[i] = True
            if was & XINPUT_BACK and not b & XINPUT_BACK and not combo.pop(i, False) and front and not overlay_open():
                pad_emit("system")  # View pressed on its own (not View + a bumper or Start): Quick Access
            if not (front or overlay_open()) or b & XINPUT_BACK:  # menus only while the frontend has the screen; View+bumper is the capture combo
                continue
            for bit, action in PAD_BUTTONS.items():
                if pressed & bit:
                    pad_emit(action)
            if b & 0x00C0 == 0x00C0 and pressed & 0x00C0:  # L3 and R3 together: zoom back to normal (a post in News)
                pad_emit("zoomReset")
            if abs(st.pad.ry) > 12000 and now >= zoom_at:  # the right stick zooms a post smoothly while it's held
                zoom_at = now + 0.05
                pad_emit("zoomIn" if st.pad.ry > 0 else "zoomOut")
            lx, ly, dead = st.pad.lx, st.pad.ly, 18000
            for d, bit in PAD_DIRS.items():
                stick = {"up": ly > dead, "down": ly < -dead, "left": lx < -dead, "right": lx > dead}[d]
                if b & bit or stick:
                    dirs.add(d)
        PAD["pads"] = pads
        for d in ("up", "down", "left", "right"):  # held directions repeat like a key: once, then steadily after a pause
            if d not in dirs:
                repeat.pop(d, None)
            elif d not in repeat:
                repeat[d] = now + 0.38
                pad_emit(d)
            elif now >= repeat[d] and (d in ("left", "right") or not overlay_open()):  # the short overlay menu: left and right only (volume)
                repeat[d] = now + 0.11
                pad_emit(d)


def adopt_game():
    """A library game filling the screen with no session open (started outside the frontend, or still running when the
    helper restarted): its session starts now, so the Steam button and View + Start open the overlay over it."""
    if open_session():
        return None
    pid = fullscreen_process()
    game = next((g for g, (_, p) in list(RUN_NOW.items()) if pid and p == pid), None)
    if game:
        session_start(game)
    return game


def playing():
    """Is a game on screen, or the overlay over one?"""
    if overlay_open():
        return True
    adopt_game()
    session = open_session()
    running = RUNNING.get(session["game"]) if session else None
    return bool(session and ((running and game_tree(running.pid)) or fullscreen_process()))


def audio_volume(level=None, delta=None, mute=None):
    """The default speakers through Windows' Core Audio. Returns {"volume": 0-100, "muted": bool}. level, delta and mute change it first."""
    if MAC:
        return plat_mac.audio_volume(level, delta, mute)
    import ctypes
    from ctypes import wintypes as W

    def guid(text):
        g = ctypes.create_string_buffer(16)
        ctypes.windll.ole32.CLSIDFromString(text, g)
        return g

    def call(obj, slot, *types):
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[slot])

    ctypes.windll.ole32.CoInitialize(None)
    ctypes.windll.ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    enum, dev, vol = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if ctypes.windll.ole32.CoCreateInstance(guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), None, 1, guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}"), ctypes.byref(enum)):
            raise OSError("No sound device")
        if call(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)(enum, 0, 1, ctypes.byref(dev)):  # speakers, multimedia
            raise OSError("No sound device")
        if call(dev, 3, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.c_void_p)(dev, guid("{5CDF2C82-841E-4546-9722-0CF74078229A}"), 1, None, ctypes.byref(vol)):
            raise OSError("No sound device")
        now, muted = ctypes.c_float(), W.BOOL()
        call(vol, 9, ctypes.c_void_p)(vol, ctypes.byref(now))
        if delta is not None:
            level = round(now.value * 100) + delta  # whole steps: Windows keeps the level as a fraction that drifts
            if delta > 0 and mute is None:
                mute = False  # turning it up unmutes, as Windows' own volume keys do
        if level is not None:
            call(vol, 7, ctypes.c_float, ctypes.c_void_p)(vol, max(0.0, min(100.0, float(level))) / 100, None)
        if mute is not None:
            call(vol, 14, W.BOOL, ctypes.c_void_p)(vol, bool(mute), None)
        call(vol, 9, ctypes.c_void_p)(vol, ctypes.byref(now))
        call(vol, 15, ctypes.c_void_p)(vol, ctypes.byref(muted))
        return {"volume": round(now.value * 100), "muted": bool(muted.value)}
    finally:
        for obj in (vol, dev, enum):
            if obj:
                call(obj, 2)(obj)



# ---------------------------------------------------------------- Quick Access: sound output, controllers, Wi-Fi, focus, brightness
def _com():
    import ctypes
    from ctypes import wintypes as W

    def guid(text):
        g = ctypes.create_string_buffer(16)
        ctypes.windll.ole32.CLSIDFromString(text, g)
        return g

    def call(obj, slot, *types):
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(vtable[slot])
    ctypes.windll.ole32.CoInitialize(None)
    ctypes.windll.ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    return ctypes, W, guid, call


def sound_outputs():
    """The speakers, headsets and TVs Windows can play through, and which one it uses now: [{"id", "name", "on"}]."""
    if not WIN:
        return []
    ctypes, W, guid, call = _com()

    class PROPKEY(ctypes.Structure):
        _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", W.DWORD)]
    key = PROPKEY()
    ctypes.memmove(key.fmtid, guid("{a45c254e-df1c-4efd-8020-67d146a850e0}"), 16)
    key.pid = 14  # the device's friendly name
    enum, col, out = ctypes.c_void_p(), ctypes.c_void_p(), []
    if ctypes.windll.ole32.CoCreateInstance(guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), None, 1, guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}"), ctypes.byref(enum)):
        return []
    try:
        default = ""
        dev = ctypes.c_void_p()
        if not call(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)(enum, 0, 1, ctypes.byref(dev)):
            p = ctypes.c_void_p()
            call(dev, 5, ctypes.c_void_p)(dev, ctypes.byref(p))
            default = ctypes.wstring_at(p.value) if p.value else ""
            ctypes.windll.ole32.CoTaskMemFree(p)
            call(dev, 2)(dev)
        if call(enum, 3, ctypes.c_int, W.DWORD, ctypes.c_void_p)(enum, 0, 1, ctypes.byref(col)):  # playback devices that are active
            return []
        n = W.UINT()
        call(col, 3, ctypes.c_void_p)(col, ctypes.byref(n))
        for i in range(n.value):
            dev, store = ctypes.c_void_p(), ctypes.c_void_p()
            if call(col, 4, W.UINT, ctypes.c_void_p)(col, i, ctypes.byref(dev)):
                continue
            p = ctypes.c_void_p()
            call(dev, 5, ctypes.c_void_p)(dev, ctypes.byref(p))
            dev_id = ctypes.wstring_at(p.value) if p.value else ""
            ctypes.windll.ole32.CoTaskMemFree(p)
            name = dev_id
            if not call(dev, 4, W.DWORD, ctypes.c_void_p)(dev, 0, ctypes.byref(store)):
                var = (ctypes.c_byte * 24)()
                if not call(store, 5, ctypes.c_void_p, ctypes.c_void_p)(store, ctypes.byref(key), ctypes.byref(var)):
                    if ctypes.cast(var, ctypes.POINTER(ctypes.c_ushort))[0] == 31:  # VT_LPWSTR
                        name = ctypes.wstring_at(ctypes.cast(ctypes.addressof(var) + 8, ctypes.POINTER(ctypes.c_void_p))[0])
                    ctypes.windll.ole32.PropVariantClear(ctypes.byref(var))
                call(store, 2)(store)
            call(dev, 2)(dev)
            out.append({"id": dev_id, "name": name, "on": dev_id == default})
        return out
    finally:
        for obj in (col, enum):
            if obj:
                call(obj, 2)(obj)


def set_sound_output(dev_id):
    """Windows plays everything through this device from now on, as choosing it in the taskbar's sound menu does."""
    if dev_id not in {d["id"] for d in sound_outputs()}:
        raise ValueError("That sound device isn't connected any more")
    ctypes, W, guid, call = _com()
    pc = ctypes.c_void_p()
    if ctypes.windll.ole32.CoCreateInstance(guid("{870af99c-171d-4f9e-af0d-e63df40c2bc9}"), None, 1, guid("{f8679f50-850a-41cf-9c72-430f290290c8}"), ctypes.byref(pc)):
        raise OSError("Windows wouldn't switch the sound device")
    try:
        for role in (0, 1, 2):  # games and system sounds, music and video, calls
            call(pc, 13, ctypes.c_wchar_p, ctypes.c_int)(pc, dev_id, role)
    finally:
        call(pc, 2)(pc)


def xinput_pads():
    """Each connected Xbox-style controller: its slot, battery ("empty", "low", "medium", "full", "wired" or None) and if it's wireless."""
    if not WIN:
        return []
    import ctypes
    try:
        xi = ctypes.WinDLL("xinput1_4")
    except OSError:
        return []

    class Batt(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ubyte), ("level", ctypes.c_ubyte)]
    out = []
    for i in range(4):
        if i not in XSTATE:
            continue
        b = Batt()
        xi.XInputGetBatteryInformation(i, 0, ctypes.byref(b))
        wired, wireless = b.type == 1, b.type in (2, 3)
        out.append({"slot": i, "battery": "wired" if wired else ["empty", "low", "medium", "full"][b.level & 3] if wireless else None, "wireless": wireless})
    return out


def xinput_off(slot):
    """Turns a wireless Xbox-style controller off, like holding its Xbox button (XInput's power-off call, ordinal 103)."""
    import ctypes
    for name in ("xinput1_4", "xinput1_3"):
        try:
            fn = ctypes.WinDLL(name)[103]
        except (OSError, AttributeError):
            continue
        if fn(int(slot)) == 0:
            return True
    raise OSError("This controller can't be turned off from here: hold its own button")


def wifi_status():
    """The Wi-Fi network this PC is on and its signal (0-100), or None on a PC without Wi-Fi."""
    if not WIN:
        return None
    try:
        r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=5, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError):
        return None
    info = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition(":")
        if v.strip():
            info.setdefault(k.strip().lower(), v.strip())
    if "state" not in info:
        return None  # no Wi-Fi adapter
    if "software off" in r.stdout.lower() or "hardware off" in r.stdout.lower():
        return {"connected": False, "name": "", "signal": None, "off": True}
    connected = info.get("state", "").lower() == "connected"
    sig = re.sub(r"\D", "", info.get("signal", ""))
    return {"connected": connected, "name": info.get("ssid", "") if connected else "", "signal": int(sig) if sig else None}


def wifi_networks():
    """Wi-Fi networks in range, strongest first: [{"ssid", "signal", "secure", "saved", "on"}]. Saved ones connect with one press."""
    if not WIN:
        return []
    run = lambda *a: subprocess.run(["netsh", "wlan", *a], capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
    try:
        listing, profiles = run("show", "networks", "mode=bssid"), run("show", "profiles")
    except (OSError, subprocess.SubprocessError):
        return []
    saved = {m.strip() for m in re.findall(r":\s*(.+)$", "\n".join(l for l in profiles.splitlines() if "Profile" in l), re.M)}
    current = (wifi_status() or {}).get("name", "")
    nets, cur = {}, None
    for line in listing.splitlines():
        m = re.match(r"\s*SSID \d+\s*:\s*(.*)$", line)
        if m:
            cur = m.group(1).strip()
            if cur:
                nets.setdefault(cur, {"ssid": cur, "signal": 0, "secure": True, "saved": cur in saved, "on": cur == current})
            continue
        if not cur:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "authentication":
            nets[cur]["secure"] = v.lower() != "open"
            nets[cur]["auth"] = "wpa3" if "wpa3" in v.lower() and "wpa2" not in v.lower() else "wpa2"
        elif k == "signal":
            nets[cur]["signal"] = max(nets[cur]["signal"], int(re.sub(r"\D", "", v) or 0))
    return sorted(nets.values(), key=lambda n: (not n["on"], not n["saved"], -n["signal"]))


def wifi_connect(ssid):
    """Joins a Wi-Fi network this PC has been on before (Windows keeps its password)."""
    net = next((n for n in wifi_networks() if n["ssid"] == ssid), None)
    if not net:
        raise ValueError("That network isn't in range any more")
    if not net["saved"]:
        return "password" if net["secure"] else wifi_join_new(ssid, "")  # a new secured network: the page asks for its password
    r = subprocess.run(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"], capture_output=True, text=True, timeout=15, creationflags=0x08000000)
    if r.returncode:
        raise OSError("Windows couldn't join that network")
    return "joining"


def _bt():
    import ctypes
    from ctypes import wintypes as W

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [(n, W.WORD) for n in ("y", "mo", "dow", "d", "h", "mi", "s", "ms")]

    class DEVINFO(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("Address", ctypes.c_ulonglong), ("ulClassofDevice", W.ULONG), ("fConnected", W.BOOL),
                    ("fRemembered", W.BOOL), ("fAuthenticated", W.BOOL), ("stLastSeen", SYSTEMTIME), ("stLastUsed", SYSTEMTIME),
                    ("szName", ctypes.c_wchar * 248)]

    class SEARCH(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("fReturnAuthenticated", W.BOOL), ("fReturnRemembered", W.BOOL), ("fReturnUnknown", W.BOOL),
                    ("fReturnConnected", W.BOOL), ("fIssueInquiry", W.BOOL), ("cTimeoutMultiplier", ctypes.c_ubyte), ("hRadio", W.HANDLE)]
    bt = ctypes.WinDLL("bthprops.cpl")
    bt.BluetoothFindFirstDevice.restype = W.HANDLE
    return ctypes, W, bt, DEVINFO, SEARCH


# Bluetooth audio: sending audio to it (A2DP) and headset calls (hands-free)
BT_AUDIO = ("{0000110b-0000-1000-8000-00805f9b34fb}", "{0000111e-0000-1000-8000-00805f9b34fb}")


def bt_audio_devices():
    """Paired Bluetooth headphones and speakers: [{"addr", "name", "connected"}]. None on a PC without Bluetooth."""
    if not WIN:
        return None
    try:
        ctypes, W, bt, DEVINFO, SEARCH = _bt()
    except OSError:
        return None
    sp = SEARCH(ctypes.sizeof(SEARCH), 1, 1, 0, 1, 0, 0, None)
    info = DEVINFO(); info.dwSize = ctypes.sizeof(DEVINFO)
    h = bt.BluetoothFindFirstDevice(ctypes.byref(sp), ctypes.byref(info))
    if not h:
        return [] if ctypes.windll.kernel32.GetLastError() in (259, 0) else None  # no devices, or no Bluetooth radio
    out = []
    try:
        while True:
            if (info.ulClassofDevice >> 8) & 0x1F == 4:  # major class: audio and video
                out.append({"addr": f"{info.Address:012x}", "name": info.szName or "Bluetooth audio", "connected": bool(info.fConnected), "kind": bt_kind(info.ulClassofDevice)})
            info = DEVINFO(); info.dwSize = ctypes.sizeof(DEVINFO)
            if not bt.BluetoothFindNextDevice(W.HANDLE(h), ctypes.byref(info)):
                break
    finally:
        bt.BluetoothFindDeviceClose(W.HANDLE(h))
    return sorted(out, key=lambda d: (not d["connected"], d["name"].lower()))


def bt_audio_connect(addr, connect=True):
    """Connects (or disconnects) paired Bluetooth headphones or a speaker by turning its audio services on (or off)."""
    ctypes, W, bt, DEVINFO, SEARCH = _bt()
    info = DEVINFO(); info.dwSize = ctypes.sizeof(DEVINFO); info.Address = int(addr, 16)
    if bt.BluetoothGetDeviceInfo(None, ctypes.byref(info)):
        raise ValueError("That Bluetooth device isn't paired any more")
    ok = False
    for svc in BT_AUDIO:
        g = ctypes.create_string_buffer(16)
        ctypes.windll.ole32.CLSIDFromString(svc, g)
        if connect:  # off then on again makes Windows reconnect it now
            bt.BluetoothSetServiceState(None, ctypes.byref(info), g, 0)
        ok = bt.BluetoothSetServiceState(None, ctypes.byref(info), g, 1 if connect else 0) == 0 or ok
    if not ok:
        raise OSError("Windows couldn't reach it: check it's switched on and nearby")


RADIO_PS1 = r"""param([string]$Kind = '', [string]$State = '')
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
$null = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
if ($Kind -and $State) {
  $r = $radios | Where-Object { "$($_.Kind)" -eq $Kind } | Select-Object -First 1
  if ($r) { $null = Await ($r.SetStateAsync($State)) ([Windows.Devices.Radios.RadioAccessStatus]) }
  Start-Sleep -Milliseconds 800
  $radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
}
$radios | ForEach-Object { "$($_.Kind)=$($_.State)" }
"""


def radios(kind=None, on=None):
    """Windows' radios ({"WiFi": True, "Bluetooth": False}), switching one on or off first, as the taskbar's quick settings do."""
    if not WIN:
        return {}
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "ufe-radio.ps1")
    with open(path, "w", encoding="utf-8") as f:
        f.write(RADIO_PS1)
    args = ["-Kind", kind, "-State", "On" if on else "Off"] if kind else []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", path, *args],
                           capture_output=True, text=True, timeout=20, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError):
        return {}
    return {k: v == "On" for k, _, v in (l.strip().partition("=") for l in r.stdout.splitlines()) if v}


def wifi_join_new(ssid, password):
    """Joins a network this PC hasn't been on: a Windows Wi-Fi profile is made with the password typed in, then used."""
    net = next((n for n in wifi_networks() if n["ssid"] == ssid), None)
    if not net:
        raise ValueError("That network isn't in range any more")
    if net["secure"] and len(password) < 8:
        raise ValueError("Wi-Fi passwords are at least 8 characters")
    import tempfile
    from xml.sax.saxutils import escape
    auth = {"wpa3": "WPA3SAE"}.get(net.get("auth", ""), "WPA2PSK") if net["secure"] else "open"
    security = (f"<authEncryption><authentication>{auth}</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>"
                f"<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>{escape(password)}</keyMaterial></sharedKey>"
                if net["secure"] else "<authEncryption><authentication>open</authentication><encryption>none</encryption><useOneX>false</useOneX></authEncryption>")
    xml = (f'<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1"><name>{escape(ssid)}</name>'
           f"<SSIDConfig><SSID><name>{escape(ssid)}</name></SSID></SSIDConfig><connectionType>ESS</connectionType><connectionMode>auto</connectionMode>"
           f"<MSM><security>{security}</security></MSM></WLANProfile>")
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml)
        r = subprocess.run(["netsh", "wlan", "add", "profile", f"filename={path}", "user=current"], capture_output=True, text=True, timeout=15, creationflags=0x08000000)
    finally:
        try:
            os.remove(path)  # the password stays only in Windows' own Wi-Fi profile
        except OSError:
            pass
    if r.returncode:
        raise OSError("Windows wouldn't save that network")
    subprocess.run(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"], capture_output=True, timeout=15, creationflags=0x08000000)
    for _ in range(10):  # a wrong password just never connects: wait a little, then say so
        time.sleep(1.5)
        if (wifi_status() or {}).get("name") == ssid:
            return "joined"
    subprocess.run(["netsh", "wlan", "delete", "profile", f"name={ssid}"], capture_output=True, timeout=15, creationflags=0x08000000)
    raise ValueError("Couldn't join: check the password and try again")



def bt_kind(cod):
    """What a Bluetooth audio device is, from its class: "headphones" (headsets, earbuds) or "speaker" (speakers, soundbars, TVs)."""
    return "headphones" if (cod >> 2) & 0x3F in (1, 2, 6) else "speaker"


def bt_forget(addr):
    """Removes a paired Bluetooth device from Windows, so it can be paired again from scratch."""
    ctypes, W, bt, DEVINFO, SEARCH = _bt()
    a = ctypes.c_ulonglong(int(addr, 16))
    if bt.BluetoothRemoveDevice(ctypes.byref(a)) not in (0, 1168):  # 1168: already gone
        raise OSError("Windows wouldn't forget that device")

def bt_scan():
    """Bluetooth headphones and speakers nearby that aren't paired yet (they must be in pairing mode). Takes about 10 seconds."""
    ctypes, W, bt, DEVINFO, SEARCH = _bt()
    sp = SEARCH(ctypes.sizeof(SEARCH), 0, 0, 1, 0, 1, 8, None)  # look for new devices for 8 x 1.28 s
    info = DEVINFO(); info.dwSize = ctypes.sizeof(DEVINFO)
    h = bt.BluetoothFindFirstDevice(ctypes.byref(sp), ctypes.byref(info))
    out = []
    if not h:
        return out
    try:
        while True:
            if (info.ulClassofDevice >> 8) & 0x1F == 4 and not info.fRemembered and not info.fAuthenticated:
                out.append({"addr": f"{info.Address:012x}", "name": info.szName or "Bluetooth audio device", "kind": bt_kind(info.ulClassofDevice)})
            info = DEVINFO(); info.dwSize = ctypes.sizeof(DEVINFO)
            if not bt.BluetoothFindNextDevice(W.HANDLE(h), ctypes.byref(info)):
                break
    finally:
        bt.BluetoothFindDeviceClose(W.HANDLE(h))
    return out


BT_PAIR_PS1 = r"""param([string]$Address)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Bluetooth.BluetoothDevice, Windows.Devices.Bluetooth, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType = WindowsRuntime] | Out-Null
$dev = Await ([Windows.Devices.Bluetooth.BluetoothDevice]::FromBluetoothAddressAsync([Convert]::ToUInt64($Address, 16))) ([Windows.Devices.Bluetooth.BluetoothDevice])
if (-not $dev) { 'nodevice'; exit 1 }
$pairing = $dev.DeviceInformation.Pairing
if ($pairing.IsPaired) { 'paired-already'; exit 0 }
$custom = $pairing.Custom
$null = $custom.add_PairingRequested({ param($s, $e) $e.Accept() })
$kinds = [Windows.Devices.Enumeration.DevicePairingKinds]'ConfirmOnly, ConfirmPinMatch, DisplayPin, ProvidePin'
$res = Await ($custom.PairAsync($kinds)) ([Windows.Devices.Enumeration.DevicePairingResult])
"$($res.Status)"
"""


def bt_pair_windows(addr):
    """Pairs through Windows' own pairing (the same as Settings), which also sets up the device's sound. The app accepts
    the pairing request itself, so nothing needs a click. True when it's paired."""
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "ufe-btpair.ps1")
    with open(path, "w", encoding="utf-8") as f:
        f.write(BT_PAIR_PS1)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", path, addr],
                           capture_output=True, text=True, timeout=60, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError):
        return False
    out = r.stdout.strip().splitlines()[-1:] or [""]
    return out[0] in ("Paired", "AlreadyPaired", "paired-already")


def bt_pair(addr):
    """Pairs new Bluetooth headphones or a speaker, then connects it, all from here: the app answers Bluetooth's pairing
    question itself (accepting the code headphones offer, or 0000 for old ones), so Windows shows no prompt to click."""
    if bt_pair_windows(addr):
        return  # Windows connects it and adds its sound output by itself
    ctypes, W, bt, DEVINFO, SEARCH = _bt()
    info = DEVINFO(); info.dwSize = ctypes.sizeof(DEVINFO); info.Address = int(addr, 16)
    bt.BluetoothGetDeviceInfo(None, ctypes.byref(info))

    class PARAMS(ctypes.Structure):
        _fields_ = [("deviceInfo", DEVINFO), ("method", ctypes.c_int), ("io", ctypes.c_int), ("req", ctypes.c_int), ("value", W.ULONG)]

    class RESPONSE(ctypes.Structure):
        _fields_ = [("addr", ctypes.c_ulonglong), ("method", ctypes.c_int), ("data", ctypes.c_ubyte * 32), ("negative", ctypes.c_ubyte)]

    answered = []

    @ctypes.WINFUNCTYPE(W.BOOL, ctypes.c_void_p, ctypes.POINTER(PARAMS))
    def on_auth(_, p):
        r = RESPONSE()
        r.addr, r.method = p.contents.deviceInfo.Address, p.contents.method
        if p.contents.method == 1:  # an old device asks for a PIN: headphones use 0000
            r.data[:4] = list(b"0000"); r.data[16] = 4
        else:  # numeric comparison / passkey: accept what the device offers (it has no screen to compare)
            ctypes.memmove(r.data, ctypes.byref(W.ULONG(p.contents.value)), 4)
        answered.append(bt.BluetoothSendAuthenticationResponseEx(None, ctypes.byref(r)))
        return True

    handle = W.HANDLE()
    bt.BluetoothRegisterForAuthenticationEx(ctypes.byref(info), ctypes.byref(handle), on_auth, None)
    try:
        err = bt.BluetoothAuthenticateDeviceEx(None, None, ctypes.byref(info), None, 0)  # MITM protection not required: headphones have no screen
    finally:
        if handle:
            bt.BluetoothUnregisterAuthentication(handle)
    if err not in (0, 183):  # 183: already paired
        raise OSError("Pairing didn't finish: put it in pairing mode and try again")
    bt_audio_connect(addr, True)


DND_KEY = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"


def do_not_disturb(on=None):
    """Windows' notification banners off (True) or back on (False); None only reads it. This user's banners, nothing else."""
    import winreg
    if on is not None:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DND_KEY) as k:
            winreg.SetValueEx(k, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0, winreg.REG_DWORD, 0 if on else 1)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DND_KEY) as k:
            return winreg.QueryValueEx(k, "NOC_GLOBAL_SETTING_TOASTS_ENABLED")[0] == 0
    except OSError:
        return False


def screen_brightness(level=None):
    """The built-in screen's brightness (0-100) on laptops and handhelds; None where Windows can't set it (most monitors and TVs)."""
    if not WIN:
        return None
    script = ("$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop; "
              + (f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={int(level)}}} | Out-Null; " if level is not None else "")
              + "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=10, creationflags=0x08000000)
        val = re.findall(r"\d+", r.stdout)
        return int(val[0]) if r.returncode == 0 and val else None
    except (OSError, subprocess.SubprocessError):
        return None




BT_BATTERY = {"at": 0.0, "items": [], "busy": False}


def bt_batteries():
    """Battery levels Windows has for Bluetooth devices (headphones, controllers): [{"name", "level"}]. Reading them
    takes a few seconds, so it runs in the background at most every 2 minutes and Quick Access shows the last answer.
    Some devices (AirPods among them) don't tell Windows their battery at all."""
    if WIN and not BT_BATTERY["busy"] and time.time() - BT_BATTERY["at"] > 120:
        BT_BATTERY["busy"] = True

        def read():
            script = ("Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^(BTHENUM|BTHLE|BTHLEDEVICE)\\\\' } | "
                      "Get-PnpDeviceProperty -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2' -ErrorAction SilentlyContinue | Where-Object Data -ne $null | "
                      "ForEach-Object { (Get-PnpDevice -InstanceId $_.InstanceId).FriendlyName + '|' + $_.Data }")
            try:
                r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=60, creationflags=0x08000000)
                items = {}
                for line in r.stdout.splitlines():
                    name, _, level = line.strip().rpartition("|")
                    if name and level.isdigit():
                        items.setdefault(name, int(level))
                BT_BATTERY["items"] = [{"name": n, "level": v} for n, v in items.items()]
            except (OSError, subprocess.SubprocessError):
                pass
            finally:
                BT_BATTERY.update(at=time.time(), busy=False)
        threading.Thread(target=read, daemon=True).start()
    return BT_BATTERY["items"]

# ---------------------------------------------------------------- AirPods battery, from what they broadcast nearby
# AirPods (and Beats) keep sending a short Bluetooth Low Energy message for Apple devices near them: Apple's
# manufacturer data (company 0x004C), message type 0x07. It holds each earbud's and the case's battery in tens of
# percent and what's charging. Any PC can hear it without pairing or a driver; it's sent while the case is open or
# they're in use. Written from the message's published layout (as Android's OpenPods reads it).
PODS = {"seen": {}, "started": False}
POD_MODELS = {0x2002: "AirPods", 0x200F: "AirPods", 0x2013: "AirPods", 0x2019: "AirPods 4", 0x201B: "AirPods 4",
              0x200E: "AirPods Pro", 0x2014: "AirPods Pro", 0x2024: "AirPods Pro", 0x2027: "AirPods Pro 3", 0x200A: "AirPods Max",
              0x201F: "AirPods Max"}


def pods_decode(data):
    """{"model", "left", "right", "case", "charging": {...}} from one message (levels 0-100, None when not reported)."""
    if len(data) < 8 or data[0] != 0x07:
        return None
    model = data[3] | data[4] << 8
    hexs = data.hex()
    flip = (int(hexs[10], 16) & 0x02) == 0  # which nibble is the left earbud
    level = lambda n: None if n > 10 else n * 10  # 15: not reported (out of the case, or the case is closed)
    left, right = int(hexs[12 if flip else 13], 16), int(hexs[13 if flip else 12], 16)
    charge = int(hexs[14], 16)
    return {"model": POD_MODELS.get(model, "Beats" if model >> 8 == 0x20 else "AirPods"), "left": level(left), "right": level(right),
            "case": level(int(hexs[15], 16)), "charging": {"left": bool(charge & (0b10 if flip else 0b01)), "right": bool(charge & (0b01 if flip else 0b10)),
                                                         "case": bool(charge & 0b100)}}


def pods_watch():
    """Listens for AirPods' broadcasts in the background, from the first time Quick Access asks."""
    if PODS["started"] or not WIN:
        return
    PODS["started"] = True
    try:
        from winrt.windows.devices.bluetooth.advertisement import BluetoothLEAdvertisementWatcher, BluetoothLEScanningMode
    except Exception:
        return

    def got(_, e):
        try:
            for m in e.advertisement.manufacturer_data:
                if m.company_id == 0x004C:
                    d = pods_decode(bytes(m.data))
                    if d:
                        PODS["seen"][str(e.bluetooth_address)] = {**d, "rssi": e.raw_signal_strength_in_dbm, "t": time.time()}
        except Exception:
            pass
    try:
        w = BluetoothLEAdvertisementWatcher()
        w.scanning_mode = BluetoothLEScanningMode.PASSIVE
        w.add_received(got)
        w.start()
        PODS["watcher"] = w  # kept, so it keeps listening
    except Exception:
        log_error()


def pods_battery():
    """The nearest AirPods' battery, if any were heard in the last two minutes (the strongest signal: yours, not a neighbour's)."""
    pods_watch()
    now = time.time()
    near = [p for p in PODS["seen"].values() if now - p["t"] < 120 and p["rssi"] > -80 and (p["left"] is not None or p["right"] is not None)]
    if not near:
        return None
    p = max(near, key=lambda p: p["rssi"])
    return {k: p[k] for k in ("model", "left", "right", "case", "charging")}


MEDIA_APP = ['']  # the app Windows' media controls last named (Spotify, a browser...), from now_playing


def audio_sessions(set_pids=None, level=None):
    """Each program playing sound on the speakers now: [{"pid", "name", "volume" 0-100, "muted"}], Windows' volume mixer.
    With set_pids and level, those programs' volume is set first (0-100)."""
    if not WIN:
        return []
    ctypes, W, guid, call = _com()
    enum, dev, mgr, sess_enum, out = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p(), []
    if ctypes.windll.ole32.CoCreateInstance(guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), None, 1, guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}"), ctypes.byref(enum)):
        return []
    try:
        if call(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)(enum, 0, 1, ctypes.byref(dev)):
            return []
        if call(dev, 3, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.c_void_p)(dev, guid("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"), 1, None, ctypes.byref(mgr)):
            return []
        if call(mgr, 5, ctypes.c_void_p)(mgr, ctypes.byref(sess_enum)):
            return []
        n = ctypes.c_int()
        call(sess_enum, 3, ctypes.c_void_p)(sess_enum, ctypes.byref(n))
        for i in range(n.value):
            ctl, ctl2, vol = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
            if call(sess_enum, 4, ctypes.c_int, ctypes.c_void_p)(sess_enum, i, ctypes.byref(ctl)):
                continue
            try:
                if call(ctl, 0, ctypes.c_void_p, ctypes.c_void_p)(ctl, guid("{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}"), ctypes.byref(ctl2)):
                    continue
                pid = W.DWORD()
                call(ctl2, 14, ctypes.c_void_p)(ctl2, ctypes.byref(pid))
                if call(ctl, 0, ctypes.c_void_p, ctypes.c_void_p)(ctl, guid("{87CE5498-68D6-44E5-9215-6DA47EF883D8}"), ctypes.byref(vol)):
                    continue
                if set_pids is not None and pid.value in set_pids and level is not None:
                    call(vol, 3, ctypes.c_float, ctypes.c_void_p)(vol, max(0.0, min(1.0, level / 100)), None)
                v, m = ctypes.c_float(), W.BOOL()
                call(vol, 4, ctypes.c_void_p)(vol, ctypes.byref(v))
                call(vol, 6, ctypes.c_void_p)(vol, ctypes.byref(m))
                if pid.value:
                    out.append({"pid": pid.value, "name": process_name(pid.value), "volume": round(v.value * 100), "muted": bool(m.value)})
            finally:
                for obj in (vol, ctl2, ctl):
                    if obj:
                        call(obj, 2)(obj)
        return out
    finally:
        for obj in (sess_enum, mgr, dev, enum):
            if obj:
                call(obj, 2)(obj)


def mixer_groups(sessions=None):
    """The three volumes Quick Access shows: the game that's running, the music or video player Windows' media controls
    name, and Ultra Front End's own sounds. {"game": [pids], "media": [pids], "ui": [pids]}"""
    sessions = sessions if sessions is not None else audio_sessions()
    groups = {"game": [], "media": [], "ui": []}
    session = open_session()
    run = RUNNING.get(session["game"]) if session else None
    game_pids = set(game_tree(run.pid)) | {run.pid} if run else set()
    if session and session["game"] in RUN_NOW:
        game_pids.add(RUN_NOW[session["game"]][1])
    mine = {os.getpid()} | set(process_tree(os.getpid()))
    aumid = MEDIA_APP[0] or ""  # "Spotify.exe", or a Store app's "SpotifyAB.SpotifyMusic_...!Spotify"
    app = re.sub(r"\.exe$", "", aumid.split("!")[-1] if "!" in aumid else os.path.basename(aumid), flags=re.I).lower()
    for s in sessions:
        name = (s["name"] or "").lower()
        if s["pid"] in game_pids:
            groups["game"].append(s["pid"])
        elif s["pid"] in mine or name.startswith("ultrafrontend") or name.startswith("game frontend"):
            groups["ui"].append(s["pid"])
        elif app and app in name:
            groups["media"].append(s["pid"])
    return groups


def mixer_view():
    """Volume (0-100) of each group that's playing sound now, or None for one that isn't."""
    sessions = audio_sessions()
    groups, by_pid = mixer_groups(sessions), {s["pid"]: s for s in sessions}
    return {k: (round(sum(by_pid[p]["volume"] for p in pids) / len(pids)) if pids else None) for k, pids in groups.items()}


def mixer_set(group, delta):
    """Turns one group's volume up or down (all its programs together)."""
    sessions = audio_sessions()
    pids = mixer_groups(sessions).get(group) or []
    if not pids:
        raise ValueError("Nothing is playing there right now")
    now = round(sum(s["volume"] for s in sessions if s["pid"] in pids) / len(pids))
    audio_sessions(set(pids), max(0, min(100, now + int(delta))))
    return mixer_view()


def qa_view():
    """Everything Quick Access shows beyond volume and music, read fresh each time it opens."""
    view = {"outputs": [], "pads": [], "wifi": None, "dnd": False, "brightness": None, "bt": None}
    for k, fn in (("outputs", sound_outputs), ("pads", xinput_pads), ("wifi", wifi_status), ("dnd", do_not_disturb), ("brightness", screen_brightness),
                  ("bt", bt_audio_devices), ("batteries", bt_batteries), ("pods", pods_battery), ("mixer", mixer_view)):
        try:
            view[k] = fn()
        except Exception:
            log_error()
    view["steamBattery"] = PAD_BATTERY[0] if time.time() - PAD_RAW[1] < 60 else None
    return view

def system_power(action):
    """The power menu. Restart and shut down wait a few seconds, so the frontend can say what's happening."""
    if MAC:
        return plat_mac.system_power(action)
    if action == "sleep":
        import ctypes
        # SetSuspendState(hibernate=False). Through rundll32 its arguments are garbage, so a PC with hibernation on hibernates.
        threading.Timer(1.0, lambda: ctypes.WinDLL("powrprof").SetSuspendState(False, False, False)).start()
        return
    cmd = {"restart": ["shutdown", "/r", "/t", "3"], "shutdown": ["shutdown", "/s", "/t", "3"]}.get(action)
    if not cmd:
        raise ValueError("No such power action")
    subprocess.Popen([os.path.join(SYSTEM32, cmd[0] + ".exe")] + cmd[1:], creationflags=0x08000000)  # no console window


def steam_downloads():
    """What Steam is downloading or has queued, from its app manifests, plus anything the frontend is unpacking."""
    out = []
    sp = steam_path()
    libs = [sp] if sp else []
    if sp:
        try:
            for v in (ci(vdf(read(os.path.join(sp, "steamapps", "libraryfolders.vdf"))), "libraryfolders") or {}).values():
                if isinstance(v, dict) and v.get("path"):
                    libs.append(v["path"])
        except OSError:
            pass
    seen = set()
    for lib in dict.fromkeys(os.path.normcase(os.path.normpath(p)) for p in libs):
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                st = ci(vdf(read(acf)), "AppState") or {}
            except OSError:
                continue
            appid, flags = ci(st, "appid"), int(ci(st, "StateFlags") or 0)
            done, total = int(ci(st, "BytesDownloaded") or 0), int(ci(st, "BytesToDownload") or 0)
            if appid in seen or not (flags & 2 or 0 < total != done):
                continue
            seen.add(appid)
            g = next((x for x in STATE["games"] if str(x.get("appid")) == str(appid)), {})
            out.append({"id": g.get("id", ""), "title": ci(st, "name") or appid, "cover": g.get("cover", ""), "done": done, "total": total,
                        "status": "Downloading" if flags & 1536 else "Update queued" if flags & 2 else "Queued"})
    for gid in list(UNPACKING):
        g = STATE["byId"].get(gid) or {}
        out.append({"id": gid, "title": g.get("title", "Game"), "cover": g.get("cover", ""), "done": 0, "total": 0, "status": "Unpacking"})
    return sorted(out, key=lambda d: d["status"] != "Downloading")


PLAYERS = {}


def steam_players(appid):
    """Players in a game right now, from Steam's public count (the same number SteamDB shows). No key needed; cached for a minute."""
    hit = PLAYERS.get(appid)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    r = http_json("https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?" + urllib.parse.urlencode({"appid": appid}), timeout=6)
    count = r.get("response", {}).get("player_count")
    PLAYERS[appid] = (time.time(), count)
    return count


FRIENDS = [0.0, []]


def steam_friends():
    """Steam friends with who's online and what they're playing. The Steam key stays here; cached for a minute."""
    acc = load("accounts.json", {}).get("steam")
    if not acc:
        raise ValueError("Connect your Steam account in Settings first")
    if time.time() - FRIENDS[0] < 60:
        return FRIENDS[1]
    base = "https://api.steampowered.com/"
    q = urllib.parse.urlencode({"key": acc["key"], "steamid": acc["steamid"], "relationship": "friend"})
    try:
        ids = [f["steamid"] for f in http_json(base + "ISteamUser/GetFriendList/v1/?" + q).get("friendslist", {}).get("friends", [])]
    except urllib.error.HTTPError:
        raise ValueError("Steam won't share your friends list. Set it to Public in your Steam privacy settings.") from None
    people = []
    for i in range(0, len(ids), 100):
        q = urllib.parse.urlencode({"key": acc["key"], "steamids": ",".join(ids[i:i + 100])})
        people += http_json(base + "ISteamUser/GetPlayerSummaries/v2/?" + q).get("response", {}).get("players", [])
    states = {1: "Online", 2: "Busy", 3: "Away", 4: "Snooze", 5: "Looking to trade", 6: "Looking to play"}
    out = [{"id": p.get("steamid", ""), "name": p.get("personaname", "Friend"), "avatar": p.get("avatarmedium", ""), "game": p.get("gameextrainfo", ""),
            "status": p.get("gameextrainfo") or states.get(p.get("personastate", 0), "Offline"), "online": bool(p.get("personastate"))} for p in people]
    out.sort(key=lambda f: (not f["game"], not f["online"], f["name"].lower()))
    FRIENDS[0], FRIENDS[1] = time.time(), out
    return out


def button_log(line):
    try:
        with open(os.path.join(DATA, "steam-button.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    except OSError:
        pass


def steam_button_gesture():
    """The Steam button: one press in a game toggles the overlay; elsewhere a double-press or hold (a single press stays
    Steam's) opens the frontend."""
    title = foreground_title()
    button_log(f"front='{title[:50]}' overlay={overlay_open()} session={bool(open_session())}")
    try:
        if frontend_in_front() and not overlay_open():
            pad_emit("system", "steam")  # on the frontend itself: its system panel
        elif config().get("guideOpens"):
            toggle_overlay()
    except Exception as e:
        button_log(f"  failed: {e!r}")
        raise


def foreground_title():
    if MAC:
        return ""
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = ctypes.c_void_p(user32.GetForegroundWindow())
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)
    return title.value


PAD_BATTERY = [None, 0.0]
PAD_RAW = [b"", 0.0]  # the latest report, for the tester in Settings > Controllers
# Report 0x42: (byte, bit) of each menu control; the left stick is two signed words at bytes 10 and 12. D-pad directions repeat.
STEAM_PAD = {"system": (3, 6), "ok": (2, 0), "back": (2, 1), "options": (2, 3), "start": (2, 6), "up": (3, 5), "down": (3, 2), "left": (3, 4), "right": (3, 3), "prevTab": (4, 3), "nextTab": (3, 1)}
STEAM_ALIAS = {"start": "options"}  # Start (Menu), like Y: the game's menu


def pad_motion(path, on):
    """Steam leaves the controller's motion sensors off. SDL's Steam Controller driver sends this same setting: raw accelerometer and gyro."""
    import ctypes
    import ctypes.wintypes as W
    k32, hid = ctypes.windll.kernel32, ctypes.windll.hid
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    hid.HidD_SetFeature.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.ULONG]
    h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
    if h in (None, ctypes.c_void_p(-1).value):
        return
    hid.HidD_SetFeature(h, bytes([1, 0x87, 3, 48, 24 if on else 0]).ljust(64, bytes(1)), 64)
    k32.CloseHandle(h)


def wii_key(scan, down):
    """Keys Dolphin takes as Wii Remote motion (see dolphin_shake_key): F13 shake, F14 tilt left, F15 tilt right. Scan codes, so DirectInput sees them."""
    import ctypes
    ctypes.windll.user32.keybd_event(0, scan, 8 if down else 10, OWN_KEYS)  # KEYEVENTF_SCANCODE, and KEYUP


def dolphin_shake_key():
    """With Wii motion on (Settings > Controllers): add F13 to Wii Remote 1's shake and F14/F15 to its tilt, keeping what is
    mapped there; the helper presses those keys when the Steam Controller is shaken or tilted. The first change keeps a copy
    of Dolphin's file as WiimoteNew.ini.bak. Run by the window process, which is the one that starts Dolphin."""
    if not config().get("wiiMotion"):
        return
    p = os.path.join(os.environ.get("APPDATA", ""), "Dolphin Emulator", "Config", "WiimoteNew.ini")
    try:
        with open(p, encoding="utf-8", newline="") as f:
            s = f.read()
        if "F13" not in s and not os.path.exists(p + ".bak"):
            shutil.copyfile(p, p + ".bak")
        head, mark, rest = s.partition("[Wiimote2]")
        lines = []
        for line in head.splitlines(True):
            if line.startswith("Shake/") and "F13" not in line:
                line = line.rstrip() + " | `DInput/0/Keyboard Mouse:F13`" + chr(13) + chr(10)
            if line.startswith("Options/") and "Tilt/Left" not in "".join(lines):
                lines += ["Tilt/Left = `DInput/0/Keyboard Mouse:F14`" + chr(13) + chr(10), "Tilt/Right = `DInput/0/Keyboard Mouse:F15`" + chr(13) + chr(10)]
            lines.append(line)
        new = "".join(lines)
        if new != head:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(new + mark + rest)
    except OSError:
        pass


# ---------- Steam's desktop keys kept out of games Steam didn't start ----------
# Steam turns a controller into keyboard and mouse for any program it didn't launch itself (its Desktop Layout: B is
# Escape, A is Enter, the d-pad arrow keys...). An emulator started from here reads the controller itself and got those
# keys too: B took Eden out of fullscreen, and quits RetroArch. While such a game is in front, a key that was faked
# (not typed) and arrives while a controller button or stick is in use is dropped. A real keyboard always gets through,
# and so do this program's own keys (marked OWN_KEYS).
OWN_KEYS = 0x55464531  # "UFE1", in the extra info of every key this program presses
KEY_GUARD = {"on": False, "hook": None, "thread": 0, "dropped": set(), "count": 0}


def pad_in_use():
    """A controller button is down, or a stick or trigger pushed, right now: an Xbox pad through XInput, or a Steam
    Controller through its own reports."""
    import ctypes
    r, at = PAD_RAW[0], PAD_RAW[1]
    if r and time.time() - at < 0.5:
        sticks = [int.from_bytes(r[i:i + 2], "little", signed=True) for i in (10, 12)]
        if r[2] or r[3] or r[4] & 0xFE or any(abs(v) > 9000 for v in sticks):
            return True
    try:
        xinput = KEY_GUARD.get("xinput") or ctypes.WinDLL("xinput1_4")
        KEY_GUARD["xinput"] = xinput
    except OSError:
        return False
    st = (ctypes.c_ubyte * 16)()
    for i in range(4):
        if xinput.XInputGetState(i, st) == 0:
            buttons = st[4] | st[5] << 8
            lx, ly = int.from_bytes(bytes(st[8:10]), "little", signed=True), int.from_bytes(bytes(st[10:12]), "little", signed=True)
            if buttons or st[6] > 30 or st[7] > 30 or abs(lx) > 9000 or abs(ly) > 9000:
                return True
    return False


def key_guard_hook():
    """The low-level keyboard hook's own thread (Windows calls it there): installed while a guarded game is in front."""
    import ctypes
    import ctypes.wintypes as W
    user32, k32 = ctypes.windll.user32, ctypes.windll.kernel32

    class KB(ctypes.Structure):
        _fields_ = [("vk", W.DWORD), ("scan", W.DWORD), ("flags", W.DWORD), ("time", W.DWORD), ("extra", ctypes.c_size_t)]
    proto = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, W.WPARAM, W.LPARAM)
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, W.WPARAM, W.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, proto, ctypes.c_void_p, W.DWORD]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    k32.GetModuleHandleW.restype = ctypes.c_void_p  # a 64-bit handle: cut to 32 bits, the hook isn't set

    def on_key(code, wparam, lparam):
        try:
            if code == 0 and KEY_GUARD["on"]:
                k = ctypes.cast(lparam, ctypes.POINTER(KB)).contents
                up = wparam in (0x101, 0x105)  # WM_KEYUP, WM_SYSKEYUP
                if k.flags & 0x10 and k.extra != OWN_KEYS:  # LLKHF_INJECTED, and not ours
                    if up and k.vk in KEY_GUARD["dropped"]:
                        KEY_GUARD["dropped"].discard(k.vk)
                        return 1
                    if not up and (pad_in_use() or (time.sleep(0.012) or pad_in_use())):  # (Steam can be a moment ahead of our read)
                        KEY_GUARD["dropped"].add(k.vk)
                        KEY_GUARD["count"] += 1
                        return 1
        except Exception:
            pass
        return user32.CallNextHookEx(None, code, wparam, lparam)
    callback = proto(on_key)
    KEY_GUARD["thread"] = k32.GetCurrentThreadId()
    hook = user32.SetWindowsHookExW(13, callback, k32.GetModuleHandleW(None), 0)  # WH_KEYBOARD_LL
    KEY_GUARD["hook"] = hook
    if not hook:
        KEY_GUARD["thread"] = 0
        return
    msg = W.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:  # until WM_QUIT from watch_key_guard
        pass
    if hook:
        user32.UnhookWindowsHookEx(hook)
    KEY_GUARD.update(hook=None, thread=0)


def guarded_game_in_front():
    """A game started from here that Steam didn't start (so Steam types its desktop keys into it) has the screen."""
    session = open_session()
    g = STATE["byId"].get(session["game"]) if session else None
    if not g or g.get("appid") or (g.get("launch") or {}).get("uri", "").startswith("steam:"):
        return False  # Steam's own games get the controller as a gamepad: nothing to keep out
    running = RUNNING.get(session["game"])
    tree = game_tree(running.pid) if running else set()
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(ctypes.c_void_p(user32.GetForegroundWindow()), ctypes.byref(pid))
    if pid.value in tree:
        return True
    # still running from before the helper restarted (an update mid-game), so not followed: the program in front is the
    # game's emulator, or the game's own program, windowed or not
    L = g.get("launch") or {}
    program = L.get("emu") or L.get("exe") or ""
    image = process_image(pid.value) if pid.value else ""
    return bool(program and image) and os.path.normcase(os.path.abspath(image)) == os.path.normcase(os.path.abspath(program))


def watch_key_guard():
    """The keyboard hook exists only while a guarded game is in front, so nothing else on the PC ever goes through it."""
    import ctypes
    while True:
        try:
            on = bool(open_session()) and guarded_game_in_front()
        except Exception:
            on = False
        was, KEY_GUARD["on"] = KEY_GUARD["on"], on
        if on and not KEY_GUARD["thread"]:
            threading.Thread(target=key_guard_hook, daemon=True).start()
        elif not on and KEY_GUARD["thread"]:
            ctypes.windll.user32.PostThreadMessageW(KEY_GUARD["thread"], 0x0012, 0, 0)  # WM_QUIT: the hook goes
            KEY_GUARD["thread"] = 0
        if on and not was:
            threading.Thread(target=keep_steam_keyboard_shut, daemon=True).start()
        time.sleep(0.25 if on else 0.5)


STEAM_KEYBOARD = "Steam Input On-screen Keyboard"  # steamwebhelper's window, a new one for each time it opens


def keep_steam_keyboard_shut():
    """Steam's Desktop Layout puts its on-screen keyboard on X (not a key, so the hook can't catch it): in a guarded game
    it's closed as it appears, checked 50 times a second. If it won't close, it's hidden."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    while KEY_GUARD["on"]:
        hwnd = user32.FindWindowW("SDL_app", STEAM_KEYBOARD)
        if hwnd and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(0.08)
            if user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                user32.ShowWindow(ctypes.c_void_p(hwnd), 0)  # SW_HIDE
            KEY_GUARD["keyboards"] = KEY_GUARD.get("keyboards", 0) + 1
        time.sleep(0.02)


def steam_button_reader(path, active):
    """Steam keeps its button away from XInput, but the controller's own reports can be read alongside it: 2026 Steam
    Controller, report 0x42, byte 4 bit 0."""
    import ctypes
    import ctypes.wintypes as W
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_void_p]
    k32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.CreateFileW(path, 0x80000000, 3, None, 3, 0, None)  # read, shared with Steam
    if h in (None, ctypes.c_void_p(-1).value):
        active.discard(path)
        return
    buf, got = ctypes.create_string_buffer(256), W.DWORD()
    down, pressed, released, fired = False, 0.0, 0.0, False
    held, repeat, checked, menus = set(), {}, 0.0, False
    motion, motion_sent, shake_until, tilt, roll = False, 0.0, 0.0, 0, 0.0
    while k32.ReadFile(h, buf, 256, ctypes.byref(got), None):  # waits for each report, about 260 a second
        if got.value >= 3 and buf.raw[0] == 0x43:  # battery report: charge state, then level in percent (SDL's Steam Controller driver)
            PAD_BATTERY[0], PAD_BATTERY[1] = buf.raw[2], time.time()
            continue
        if got.value < 14 or buf.raw[0] != 0x42:
            continue
        now, on, r = time.time(), bool(buf.raw[4] & 1), buf.raw
        PAD_RAW[0], PAD_RAW[1] = r[:30], now
        if now - checked > 0.1:
            checked, menus = now, overlay_open() or frontend_in_front()
            dolphin = foreground_title().startswith("Dolphin") and not menus and bool(config().get("wiiMotion"))
            if dolphin and now - motion_sent > 5:  # again every so often: Steam or a sleeping controller can turn it off
                motion_sent = now
                threading.Thread(target=pad_motion, args=[path, True], daemon=True).start()
            elif motion and not dolphin:
                motion_sent = 0.0
                threading.Thread(target=pad_motion, args=[path, False], daemon=True).start()
                if shake_until:
                    shake_until = 0.0
                    wii_key(0x64, False)
                if tilt:
                    wii_key(tilt, False)
                    tilt = 0
            motion = dolphin
        if motion and got.value >= 46:
            ax, ay, az, gx, gy, gz = struct.unpack_from("<6h", r, 34)  # 16384 is 1 g; 32768 is 2000 degrees a second
            if ax * ax + ay * ay + az * az > 24576 ** 2 or gx * gx + gy * gy + gz * gz > 20000 ** 2:  # past 1.5 g, or a hard flick
                if not shake_until:
                    wii_key(0x64, True)
                shake_until = now + 0.2
            elif shake_until and now > shake_until:
                shake_until = 0.0
                wii_key(0x64, False)
            roll += (ax - roll) * 0.05  # smoothed, so a shake doesn't read as a tilt. Right side down makes this negative
            want = 0x66 if roll < -3300 else 0x65 if roll > 3300 else tilt if abs(roll) > 2400 else 0  # about 12 degrees, letting go at 8
            if want != tilt and not shake_until:
                if tilt:
                    wii_key(tilt, False)
                if want:
                    wii_key(want, True)
                tilt = want
        if menus:  # navigation: Steam leaves this controller as a mouse for anything it didn't launch itself
            lx, ly = int.from_bytes(r[10:12], "little", signed=True), int.from_bytes(r[12:14], "little", signed=True)
            state = {k for k, (byte, bit) in STEAM_PAD.items() if r[byte] >> bit & 1}
            state |= {d for d, hit in (("up", ly > 18000), ("down", ly < -18000), ("left", lx < -18000), ("right", lx > 18000)) if hit}
            for k in state - held:
                pad_emit(STEAM_ALIAS.get(k, k), "steam")
                repeat[k] = now + 0.38
            for k in state & set(repeat) & {"up", "down", "left", "right"}:  # directions only; in the short overlay menu just left and right (volume)
                if now >= repeat[k] and (k in ("left", "right") or not overlay_open()):
                    repeat[k] = now + 0.11
                    pad_emit(k, "steam")
            held = state
        else:
            held, repeat = set(), {}
        if on and not down:
            if playing():  # in a game one press is enough
                fired = True
                threading.Thread(target=steam_button_gesture, daemon=True).start()
            elif now - released < 0.4 and not fired:
                fired = True
                threading.Thread(target=steam_button_gesture, daemon=True).start()
            pressed = now
        elif on and now - pressed > 0.6 and not fired:
            fired = True
            threading.Thread(target=steam_button_gesture, daemon=True).start()
        elif down and not on:
            released = 0.0 if fired else now  # after a gesture, the next press starts afresh
            fired = False
        down = on
    k32.CloseHandle(h)
    active.discard(path)


def watch_steam_button():
    """Keep a reader on each Valve controller interface, picking up controllers as they connect."""
    import ctypes
    import ctypes.wintypes as W

    class GUID(ctypes.Structure):
        _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_ubyte * 8)]

    class Iface(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("guid", GUID), ("flags", W.DWORD), ("res", ctypes.c_void_p)]
    setup = ctypes.windll.setupapi
    setup.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setup.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), ctypes.c_wchar_p, ctypes.c_void_p, W.DWORD]
    setup.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), W.DWORD, ctypes.POINTER(Iface)]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Iface), ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    guid, active = GUID(), set()
    ctypes.windll.hid.HidD_GetHidGuid(ctypes.byref(guid))
    while True:
        devs = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)  # present, device interfaces
        i, iface = 0, Iface()
        iface.cbSize = ctypes.sizeof(Iface)
        while setup.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(guid), i, ctypes.byref(iface)):
            i += 1
            buf = ctypes.create_string_buffer(1024)
            ctypes.cast(buf, ctypes.POINTER(W.DWORD))[0] = 8
            if setup.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(iface), buf, 1024, None, None):
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                if "vid_28de" in path.lower() and path not in active:
                    active.add(path)
                    threading.Thread(target=steam_button_reader, args=[path, active], daemon=True).start()
        setup.SetupDiDestroyDeviceInfoList(devs)
        time.sleep(30)


def played_seconds(p, game_id, sessions=None):
    """Time played as seconds. Logs from before 1.2.7 kept whole minutes per launch (rounded down, so short launches
    counted nothing) and missed launches the helper wasn't watching to the end: those take the session total if larger."""
    if "seconds" not in p:
        if sessions is None:
            sessions = load("sessions.json", [])
        total = sum(min(s["end"] - s["start"], 8 * 3600) for s in sessions if s.get("game") == game_id and s.get("end"))
        p["seconds"] = max(p.get("minutes", 0) * 60, int(total))
    return p["seconds"]


def record_play(game_id, seconds=0):
    log = load("playlog.json", {})
    p = log.setdefault(game_id, {"lastPlayed": 0, "minutes": 0, "seconds": 0})
    p["lastPlayed"] = int(time.time())
    p["seconds"] = played_seconds(p, game_id) + int(seconds)
    p["minutes"] = p["seconds"] // 60
    store("playlog.json", log)
    g = STATE["byId"].get(game_id)
    if g:
        g["lastPlayed"] = p["lastPlayed"]
        g["minutes"] = max(g["minutes"], p["minutes"])


UNPACK_ERRORS, UNPACKING = {}, set()  # read by the page through /api/unpack while it waits for a zipped game


def unpacked_rom(game, L):
    """Unpack a zipped game into data/unpacked (once; reused while the archive is unchanged) and return the game file inside."""
    src = L["rom"]
    dest = os.path.join(DATA, "unpacked", safe_name(game["id"]))
    stamp = f"{os.path.getsize(src)}:{int(os.path.getmtime(src))}"
    marker = dest + ".done"
    if not (os.path.isdir(dest) and os.path.isfile(marker) and read(marker) == stamp):
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest)
        if src.lower().endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(src) as z:
                root = os.path.realpath(dest)
                for m in z.infolist():  # never write outside the folder ("zip slip")
                    if not os.path.realpath(os.path.join(dest, m.filename)).startswith(root + os.sep):
                        raise ValueError("That archive has unsafe paths in it")
                z.extractall(dest)
        else:
            if not SEVEN_ZIP:
                raise ValueError("Install 7-Zip to play .7z games")
            r = subprocess.run([SEVEN_ZIP, "x", "-y", "-spe", f"-o{dest}", src], capture_output=True, timeout=1800)
            if r.returncode != 0:
                raise ValueError("Couldn't unpack that .7z")
        with open(marker, "w", encoding="utf-8") as f:
            f.write(stamp)
    files = [os.path.join(d, n) for d, _, ns in os.walk(dest) for n in ns]
    for ext in L.get("exts") or []:  # the console's preferred type first (e.g. .cue before .bin), the biggest if several
        hits = [f for f in files if os.path.basename(f).lower() == ext or f.lower().endswith(ext)]
        if hits:
            return max(hits, key=os.path.getsize)
    if not files:
        raise ValueError("That archive is empty")
    return max(files, key=os.path.getsize)


def screen_size():
    """The main screen's real resolution in pixels (ignores Windows display scaling)."""
    if MAC:
        return plat_mac.screen_size()
    try:
        import ctypes
        user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
        user32.GetDC.restype = ctypes.c_void_p
        user32.GetDC.argtypes, gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p], [ctypes.c_void_p, ctypes.c_int]
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        dc = user32.GetDC(None)
        w, h = gdi32.GetDeviceCaps(dc, 118), gdi32.GetDeviceCaps(dc, 117)  # DESKTOPHORZRES, DESKTOPVERTRES
        user32.ReleaseDC(None, dc)
        return (w, h) if w and h else (1920, 1080)
    except (OSError, AttributeError):
        return 1920, 1080


def run_emulator(game, L, rom):
    if re.search(r"kyty", os.path.basename(L["emu"]), re.I) and os.path.basename(rom).lower() == "eboot.bin":
        rom = os.path.dirname(rom)  # Kyty loads the whole game folder (eboot.bin, sce_sys, ...)
    args = launch_args(game, L, rom)
    proc = spawn([program(L["emu"])] + args, os.path.dirname(L["emu"].rstrip("/")))
    RUNNING[game["id"]] = proc
    hold_until_fullscreen(game["id"], proc.pid)
    threading.Thread(target=wait_game, args=[game, proc, time.time()], daemon=True).start()


def launch(game):
    L = game["launch"]
    if L["type"] == "none":
        raise ValueError(L["message"])
    running = RUNNING.get(game["id"])
    if running and WIN and game_tree(running.pid):  # already playing: bring it back instead of a second copy
        focus_process(running.pid, timeout=5)
        return "running"
    if game["id"] in RUN_NOW:  # never a second copy, however this was asked for
        running_resume(game["id"])
        return "running"
    if game["id"] in LAUNCHING:  # already on its way
        return "running"
    if L["type"] == "exe" and not os.path.exists(L["exe"]):
        raise ValueError("The selected program is missing. Change app location from the game menu.")
    if L["type"] == "emu" and not os.path.exists(L.get("emu") or ""):
        raise ValueError(f"The emulator for {game.get('system') or 'this console'} is missing. Choose it again in Settings › Systems.")
    if L["type"] == "emu" and WIN and config().get("keepOnScreen", True):
        try:
            make_borderless(L["emu"])  # exclusive fullscreen would pause the game whenever the in-game menu opens
        except Exception:
            log_error()
    if L["type"] != "uri":
        LAUNCHING.add(game["id"])
    session_start(game["id"])  # Still captures from now until it ends belong to this game
    try:
        started = start_game(game, L)
        if started != "unpacking":  # that one is recorded once it has unpacked and started
            record_play(game["id"])
        return started
    except Exception:  # it never started: nothing is on its way and no session is open, so updates and the next try aren't held up
        LAUNCHING.discard(game["id"])
        session_end(game["id"])
        raise


def start_game(game, L):
    if L["type"] == "uri":
        steam = os.path.join(steam_path() or "", "steam.exe")
        if WIN and L["uri"].startswith("steam://rungameid/") and os.path.isfile(steam):
            LAUNCHING.add(game["id"])
            hold_steam_launch(game["id"])
            local_spawn([steam, "-silent", L["uri"]], os.path.dirname(steam))  # -silent: no main Steam window
        else:
            open_target(L["uri"])
        return
    if L["type"] == "exe":
        cmd, cwd = [program(L["exe"]), *L.get("args", [])], L.get("cwd") or os.path.dirname(L["exe"].rstrip("/"))
    else:  # emulator: no shell, the ROM path is passed as a single argument
        rom = L["rom"]
        try:
            apply_bios(game.get("system"), wait=False)  # the console's BIOS files set up in its emulator first (not waiting on an install already doing it)
        except Exception:
            log_error()
        if (os.path.splitext(rom)[1].lower() in ARCHIVES and not ZIP_OK.search(os.path.basename(L["emu"]))
                and game.get("system") not in ZIP_GAMES):
            # this emulator can't read archives: unpack (once, kept for next time) in the background, then start it
            def unpack_and_run():
                try:
                    run_emulator(game, L, unpacked_rom(game, L))
                    record_play(game["id"])
                except Exception as e:
                    UNPACK_ERRORS[game["id"]] = str(e) or "The game couldn't be unpacked"
                    LAUNCHING.discard(game["id"])
                    session_end(game["id"])
                finally:
                    UNPACKING.discard(game["id"])
            UNPACK_ERRORS.pop(game["id"], None)
            UNPACKING.add(game["id"])
            threading.Thread(target=unpack_and_run, daemon=True).start()
            return "unpacking"
        return run_emulator(game, L, rom)
    proc = spawn(cmd, cwd)
    RUNNING[game["id"]] = proc
    if WIN and re.search(r"[\\/]Ports[\\/]", L["exe"]):  # a port's folder is its own, unlike an emulator's shared install
        PORT_DIRS[proc.pid] = cwd
    hold_until_fullscreen(game["id"], proc.pid)
    threading.Thread(target=wait_game, args=[game, proc, time.time()], daemon=True).start()


def change_app_location(game_id, reset=False):
    if game_id not in STATE["byId"]:
        raise ValueError("Game not found")
    exe = None if reset else pick("file", "Choose the game or launcher program" + ("" if MAC else " (.exe)"))
    if not reset and not exe:
        return {"cancelled": True}
    if not reset and MAC and not (exe.lower().endswith(".app") or os.access(exe, os.X_OK)):
        raise ValueError("Choose an app or a program")
    if not reset and not MAC and (not os.path.isfile(exe) or not exe.lower().endswith(".exe")):
        raise ValueError("Choose an existing Windows program (.exe)")
    overrides = load("overrides.json", {})
    entry = overrides.setdefault(game_id, {})
    if reset:
        entry.pop("appPath", None)
        if not entry:
            overrides.pop(game_id, None)
    else:
        entry["appPath"] = os.path.abspath(exe)
    store("overrides.json", overrides)
    scan()
    return {"ok": True}


# ---------------------------------------------------------------- native file pickers
PICK_LOCK = threading.Lock()


def pick_mac(kind, title):
    q = title.replace("\\", "").replace('"', "'")
    script = f'POSIX path of (choose {"folder" if kind == "dir" else "file"} with prompt "{q}")'
    r = subprocess.run(["osascript", "-e", 'tell application "System Events" to activate', "-e", script], capture_output=True, text=True)
    path = r.stdout.strip()
    return path.rstrip("/") if r.returncode == 0 and path else None


def pick(kind, title, filetypes=None):
    if MAC:
        with PICK_LOCK:
            return pick_mac(kind, title)
    with PICK_LOCK:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        try:
            if kind == "dir":
                path = filedialog.askdirectory(parent=root, title=title, mustexist=True)
            else:
                path = filedialog.askopenfilename(parent=root, title=title, filetypes=filetypes or [("Programs", "*.exe")])
            return os.path.normpath(path) if path else None
        finally:
            root.destroy()


LOCAL_PROVIDERS = {"ea": "EA app", "ubisoft": "Ubisoft Connect", "gog": "GOG", "rockstar": "Rockstar Games", "battlenet": "Battle.net"}


# ---------------------------------------------------------------- EA app, Ubisoft Connect, GOG, Battle.net: installed games
# None of them share your owned-games list without their own sign-in, so (like "Installed Steam games") this finds what
# each launcher has installed on this PC from the entries it writes to Windows' installed-programs list, and starts
# games through the launcher so sign-in, updates and cloud saves still work.
SERVICE_SCANS = ("ea", "ubisoft", "gog", "battlenet")   # each has an on/off option "<id>Local" (on by default)
OPTION_KEYS = ("steamLocal", "onlineCovers", "showUninstalled", "artBackground", "guideOpens", "wiiMotion", "keepOnScreen", "usageCheckin") + tuple(p + "Local" for p in SERVICE_SCANS)
SERVICE_APPS = {
    "ea": [r"C:\Program Files\Electronic Arts\EA Desktop\EA Desktop\EADesktop.exe"],
    "ubisoft": [r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe", r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\upc.exe"],
    "battlenet": [r"C:\Program Files (x86)\Battle.net\Battle.net.exe", r"C:\Program Files\Battle.net\Battle.net.exe"],
    "gog": [r"C:\Program Files (x86)\GOG Galaxy\GalaxyClient.exe", r"C:\Program Files\GOG Galaxy\GalaxyClient.exe"],
}
# Battle.net starts a game by its product code; games not listed here start from their own launcher program instead.
BNET_CODES = {"wow": "WoW", "d3": "D3", "pro": "Pro", "hs_beta": "WTCG", "heroes": "Hero", "s1": "S1", "s2": "S2", "w3": "W3",
              "fenris": "Fen", "osi": "OSI"}


def service_app(provider):
    return next((p for p in SERVICE_APPS[provider] if os.path.isfile(p)), None)


def installed_programs():
    """Windows' installed-programs list (what Settings > Apps shows): key name, title, folder and uninstall command."""
    import winreg
    out = []
    for hive, path in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    key = winreg.EnumKey(root, i)
                    with winreg.OpenKey(root, key) as k:
                        def val(name):
                            try:
                                return str(winreg.QueryValueEx(k, name)[0] or "")
                            except OSError:
                                return ""
                        out.append({"key": key, "name": val("DisplayName"), "location": val("InstallLocation").strip('"'),
                                    "uninstall": val("UninstallString")})
                except OSError:
                    continue
    return out


def service_game(provider, key, title, folder, launch, cfg):
    gid_, title = gid(provider, key), re.sub(r"\s*[™®©]\s*", " ", title).strip()  # "Battlefield™ 2042": cleaner for artwork searches
    img = find_image([folder], {"cover", "boxart", "poster", title}) if folder and os.path.isdir(folder) else None
    cover = local_art(gid_, img) if img else (online_cover(title) if cfg["onlineCovers"] else "")
    return {"id": gid_, "title": title, "group": LOCAL_PROVIDERS[provider], "source": LOCAL_PROVIDERS[provider], "installed": True,
            "minutes": 0, "lastPlayed": 0, "cover": cover, "launch": launch, "folder": folder}


def scan_ea(programs, cfg):
    games = []
    for p in programs:
        folder = p["location"]
        data = os.path.join(folder, "__Installer", "installerdata.xml") if folder else ""
        if not p["name"] or not (os.path.isfile(data) or "eainstaller" in p["uninstall"].lower()) or not os.path.isdir(folder):
            continue
        offer = re.search(r"<contentID>\s*([\w.:-]+)\s*</contentID>", read(data) if os.path.isfile(data) else "")
        if offer and service_app("ea"):
            launch = {"type": "uri", "uri": "origin2://game/launch?offerIds=" + urllib.parse.quote(offer.group(1))}
        else:
            exe = best_exe(folder)
            if not exe:
                continue
            launch = {"type": "exe", "exe": exe, "args": []}
        games.append(service_game("ea", p["key"], clean_title(p["name"]), folder, launch, cfg))
    return games


def scan_ubisoft(programs, cfg):
    import winreg
    names = {p["key"][len("Uplay Install "):]: p["name"] for p in programs if p["key"].startswith("Uplay Install ")}
    games = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs")
    except OSError:
        return []
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                game_id = winreg.EnumKey(root, i)
                with winreg.OpenKey(root, game_id) as k:
                    folder = os.path.normpath(str(winreg.QueryValueEx(k, "InstallDir")[0]))
            except OSError:
                continue
            if not re.fullmatch(r"\d+", game_id) or not os.path.isdir(folder):
                continue
            title = names.get(game_id) or os.path.basename(folder.rstrip("\\/"))
            games.append(service_game("ubisoft", game_id, clean_title(title), folder, {"type": "uri", "uri": f"uplay://launch/{game_id}/0"}, cfg))
    return games


def scan_battlenet(programs, cfg):
    app, games = service_app("battlenet"), []
    for p in programs:
        u = p["uninstall"]
        m = re.search(r"--uid=([\w-]+)", u)
        folder = p["location"]
        if not m or not re.search(r"battle\.net|blizzard", u, re.I) or not p["name"] or not os.path.isdir(folder or ""):
            continue
        uid = m.group(1).lower()
        code = BNET_CODES.get(uid) or BNET_CODES.get(uid.split("_")[0])
        if code and app:
            launch = {"type": "exe", "exe": app, "args": [f"--exec=launch {code}"]}
        else:  # Blizzard games ship a "<Game> Launcher.exe" that goes through Battle.net
            own = [f for f in glob.glob(os.path.join(folder, "* Launcher.exe")) if "battle.net" not in f.lower()]
            exe = own[0] if own else best_exe(folder)
            if not exe:
                continue
            launch = {"type": "exe", "exe": exe, "args": []}
        games.append(service_game("battlenet", uid, clean_title(p["name"]), folder, launch, cfg))
    return games


def scan_gog(programs, cfg):
    """GOG games: GOG Galaxy and GOG's own offline installers both list each installed game under GOG.com\\Games in the
    registry. With Galaxy installed a game starts through it (cloud saves, achievements); otherwise its own program starts."""
    import winreg
    app, games = service_app("gog"), []
    for path in (r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"):
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    game_id = winreg.EnumKey(root, i)
                    with winreg.OpenKey(root, game_id) as k:
                        def val(name):
                            try:
                                return str(winreg.QueryValueEx(k, name)[0] or "")
                            except OSError:
                                return ""
                        title, folder, exe, args, depends = val("gameName"), val("path"), val("exe"), val("launchParam"), val("dependsOn")
                except OSError:
                    continue
                if not re.fullmatch(r"\d+", game_id) or depends or not title or not os.path.isdir(folder):  # dependsOn: a DLC, not a game
                    continue
                if any(g["id"] == gid("gog", game_id) for g in games):
                    continue
                if app:
                    launch = {"type": "exe", "exe": app, "args": ["/command=runGame", f"/gameId={game_id}", f"/path={folder}"]}
                elif exe and os.path.isfile(exe):
                    launch = {"type": "exe", "exe": exe, "args": args.split() if args else []}
                else:
                    found = best_exe(folder)
                    if not found:
                        continue
                    launch = {"type": "exe", "exe": found, "args": []}
                games.append(service_game("gog", game_id, clean_title(title), folder, launch, cfg))
    return games


# ---------------------------------------------------------------- game launchers: installed from setup or Settings when missing
# (id, name, winget package). Each comes from its maker through winget, like the emulators, in the same install queue.
LAUNCHERS = [("steam", "Steam", "Valve.Steam"), ("epic", "Epic Games Launcher", "EpicGames.EpicGamesLauncher"),
             ("ea", "EA app", "ElectronicArts.EADesktop"), ("ubisoft", "Ubisoft Connect", "Ubisoft.Connect"),
             ("gog", "GOG Galaxy", "GOG.Galaxy"), ("battlenet", "Battle.net", "Blizzard.BattleNet"),
             ("rockstar", "Rockstar Games Launcher", "RockstarGames.Launcher")]
LAUNCHER_FILES = {
    "epic": [r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
             r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
             r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"],
    "rockstar": [r"C:\Program Files\Rockstar Games\Launcher\Launcher.exe", r"C:\Program Files (x86)\Rockstar Games\Launcher\Launcher.exe"],
}


def launcher_installed(lid):
    if lid == "steam":
        return bool(steam_path())
    if lid in SERVICE_APPS:
        return bool(service_app(lid))
    return any(os.path.isfile(f) for f in LAUNCHER_FILES.get(lid, []))


def queue_launcher(lid):
    entry = next((l for l in LAUNCHERS if l[0] == lid), None)
    if not entry or not WIN:
        raise ValueError("No such launcher")
    with QUEUE_COND:
        if not any(j.get("launcher") == lid and j["state"] in ("waiting", "installing") for j in QUEUE["jobs"]):
            new_batch()
            QUEUE["next"] += 1
            QUEUE["jobs"].append({"id": QUEUE["next"], "emulator": entry[1], "package": (entry[2], "launcher"), "systems": [], "launcher": lid,
                                  "state": "waiting", "error": ""})
    queue_install([])  # starts the worker if need be and wakes it


def launchers_view():
    out = []
    for lid, name, _ in LAUNCHERS:
        job = next((j for j in reversed(QUEUE["jobs"]) if j.get("launcher") == lid), None)
        out.append({"id": lid, "name": name, "installed": launcher_installed(lid), "job": job_info(job) if job else None})
    return out


def add_library(kind, provider=None):
    if provider and (provider not in LOCAL_PROVIDERS or kind not in ("pc", "game")):  # (not "folder")
        raise ValueError("Unknown game service")
    cfg = config()
    if kind == "pc":
        path = pick("dir", "Choose a folder of PC games (one game per subfolder)")
        if not path:
            return None
        lib = {"type": "pc", "path": path, "name": os.path.basename(path) or path}
    elif kind == "folder":
        path = pick("dir", "Choose a folder to open from the home screen")
        if not path:
            return None
        lib = {"type": "folder", "path": path, "name": "Folders", "title": os.path.basename(path.rstrip("\\/")) or path}
    elif kind == "game":
        path = pick("file", "Choose the game's .exe")
        if not path:
            return None
        lib = {"type": "game", "path": path, "name": "PC Ports", "title": title_for_exe(path)}
    elif kind == "roms":
        path = pick("dir", "Choose a folder of ROMs for one system")
        if not path:
            return None
        emu = pick("file", "Choose the emulator that plays these games")
        if not emu:
            return None
        s = detect_system(path)
        lib = {"type": "roms", "path": path, "name": s["system"], "emulator": emu, "args": emulator_args(emu, s["cores"], s["system"]),
               "exts": s["exts"], "thumbs": s["thumbs"]}
    else:
        raise ValueError("Unknown library type")
    if provider:
        lib["name"] = LOCAL_PROVIDERS[provider]
        lib["provider"] = provider
    lib["id"] = gid("lib", lib["type"] + lib["path"])
    if kind == "game":  # adding a game means seeing it: one hidden earlier (by this name or another) is shown again
        overrides = load("overrides.json", {})
        o = overrides.get(gid("pc", path))
        if o and o.pop("hidden", None):
            if not o:
                overrides.pop(gid("pc", path))
            store("overrides.json", overrides)
            if any(x["id"] == lib["id"] for x in cfg["libraries"]):
                return next(x for x in cfg["libraries"] if x["id"] == lib["id"])
    if any(x["id"] == lib["id"] for x in cfg["libraries"]):
        raise ValueError("That library is already added")
    cfg["libraries"].append(lib)
    store("config.json", cfg)
    return lib


def settings_view():
    cfg, accounts = config(), load("accounts.json", {})
    libs = [{"id": l["id"], "type": l["type"], "name": l["name"], "path": l["path"], "emulator": l.get("emulator"),
             "provider": l.get("provider"), "count": STATE["counts"].get("lib:" + l["id"], 0)} for l in cfg["libraries"]]
    acc = {}
    if "steam" in accounts:
        acc["steam"] = {"label": accounts["steam"]["steamid"], "count": STATE["counts"].get("Steam account", 0)}
    if "epic" in accounts:
        acc["epic"] = {"label": accounts["epic"].get("name") or "connected", "count": STATE["counts"].get("Epic account", 0)}
    if "sgdb" in accounts:
        acc["sgdb"] = {"label": "API key saved"}
    if "ra" in accounts:
        acc["ra"] = {"label": accounts["ra"]["user"], "points": accounts["ra"].get("points", 0)}
    extra = sorted({k.split("/", 1)[1] for k in STATE["counts"] if k.startswith("ROMs/")} - set(ROM_FOLDERS))  # folders it doesn't know
    chosen = set(cfg.get("systems") or []) | set(extra)
    platforms = [system_view(p, cfg, chosen) for p in ROM_FOLDERS + extra]
    services = {p: {"detected": bool(service_app(p)), "count": STATE["counts"].get(f"{LOCAL_PROVIDERS[p]} (installed)", 0)} for p in SERVICE_SCANS}
    return {"options": {**{k: cfg.get(k, True) for k in OPTION_KEYS}, "startup": cfg.get("startup")}, "services": services, "libraries": libs, "accounts": acc,
            "errors": STATE["errors"], "steamDetected": bool(steam_path()), "steamSuggestedId": steam_suggested_id(),
            "localSteamCount": STATE["counts"].get("Steam (installed)", 0), "romRoot": cfg.get("romRoot") or "", "platforms": platforms,
            "emuUpdates": {"checked": EMU_UPDATES["checked"], "list": [{"name": n, "to": i.get("to", ""), "systems": i["systems"], "installer": k == "winget"}
                                                                   for k in ("github", "winget") for n, i in EMU_UPDATES[k].items()]},
            "homeMove": (lambda m: {"roms": bool(m["roms"]), "emus": [os.path.basename(a) for a, _ in m["emus"]], "why": m["why"], "home": UFE_HOME})(home_move_plan(cfg)),
            "queue": queue_view(), "profile": profile(), "update": update_view(), "extras": extras_view(),
            "launchers": launchers_view() if WIN else [], "autologon": autologon_view() if WIN else {"available": False},
            **({"homeOpensUs": mac_home_opens_us()} if MAC else {})}


def profile():
    p = {"name": "", "avatar": "", "timezone": "auto", "setupDone": False, **config().get("profile", {})}
    pic = glob.glob(os.path.join(DATA, "avatar.*"))
    p["picture"] = f"/api/avatar?v={int(os.path.getmtime(pic[0]))}" if pic else ""
    return p


def default_rom_root():
    """C:\\Ultra-Front-End\\ROMs, made if it isn't there: where setup puts ROMs unless you choose another folder."""
    folder = os.path.join(UFE_HOME, "ROMs") if WIN else os.path.expanduser("~/ROMs")
    os.makedirs(folder, exist_ok=True)
    return folder


def set_rom_root(path):
    """Use this folder as the ROMs folder, with a subfolder for every system you play that doesn't have one."""
    cfg = config()
    cfg["romRoot"] = path
    found = auto_emulators(cfg)
    store("config.json", cfg)
    made = sum(ensure_folders(s, cfg) for s in cfg.get("systems") or [])
    apply_soon()
    return made, found


# ---------------------------------------------------------------- moving everything into C:\Ultra-Front-End
# For people set up before 1.2.5 (ROMs in C:\ROMs, downloaded emulators in ~\Emulators): one press in Settings moves them.
# A game's id comes from its path, so everything kept by id (playtime, favourites, art, captures...) goes to the new id.
OWN_EMUS = None  # the emulator folders Ultra Front End itself downloads into ~\Emulators (never the user's own others)
ID_STORES = ("overrides.json", "playlog.json", "ra-match.json", "info-cache.json")  # {game id: ...}
ID_LISTS = ("sessions.json", "captures.json")  # [{"game": game id, ...}]
CONFIG_TEXT = (".yml", ".yaml", ".ini", ".cfg", ".json", ".toml", ".xml", ".conf")


def own_emu_names():
    return set(GITHUB_EMUS) | {"Dolphin-2609a", "Hatari", "MAME"}


def under(path, root):
    """path is root or inside it (Windows: any case)."""
    a, b = os.path.normcase(os.path.abspath(path or "")), os.path.normcase(os.path.abspath(root)).rstrip("\\/")
    return a == b or a.startswith(b + os.sep)


def moved_path(path, moves):
    for old, new in moves:
        if path and under(path, old):
            return new + os.path.abspath(path)[len(os.path.abspath(old).rstrip("\\/")):]
    return path


def home_move_plan(cfg=None):
    """What a move would do: {"roms": (from, to) or None, "emus": [(from, to)], "why": reason it can't, or ""}."""
    cfg = cfg or config()
    plan = {"roms": None, "emus": [], "why": ""}
    if not WIN:
        return plan
    root, target = cfg.get("romRoot") or "", os.path.join(UFE_HOME, "ROMs")
    if root and os.path.isdir(root) and not under(root, UFE_HOME):
        if os.path.splitdrive(os.path.abspath(root))[0].lower() != os.path.splitdrive(target)[0].lower():
            plan["why"] = f"Your ROMs folder is on another drive ({os.path.splitdrive(root)[0]}), so it stays there"
        elif os.path.exists(target) and os.listdir(target):
            plan["why"] = f"{target} already has files in it, so your ROMs folder stays where it is"
        else:
            plan["roms"] = (os.path.abspath(root), target)
    paths = [e.get("path", "") for e in (cfg.get("emulators") or {}).values()]
    paths += [l.get("emulator") or "" for l in cfg.get("libraries", [])] + [l.get("path", "") for l in cfg.get("libraries", []) if l.get("type") == "game"]
    names = own_emu_names()
    for name in sorted(names):
        src = os.path.join(OLD_EMU_HOME, name)
        if os.path.isdir(src) and any(under(x, src) for x in paths) and not os.path.exists(os.path.join(EMU_HOME, name)):
            plan["emus"].append((src, os.path.join(EMU_HOME, name)))
    return plan


def game_id_sources(g):
    """The text a game's id was made from (its file, its game folder, or an emulator and its arguments), found by trying."""
    L = g.get("launch") or {}
    cands = []  # (program or file, its arguments): the id was made from the file, or from the program and arguments joined
    if L.get("rom"):
        f = L["rom"]
        cands.append((f, []))
        d = os.path.dirname(f)
        for _ in range(6):  # a Switch game kept as a folder: the id is the folder's
            cands.append((d, []))
            d = os.path.dirname(d)
    if L.get("exe"):
        cands += [(L["exe"], []), (L["exe"], list(L.get("args") or []))]
    prefix = g["id"].split("-", 1)[0]
    return [c for c in cands if gid(prefix, " ".join([c[0], *c[1]])) == g["id"]]


def rekey_games(mapping):
    """Everything kept by game id goes to the game's new id."""
    if not mapping:
        return
    for name in ID_STORES:
        d = load(name, {})
        if isinstance(d, dict) and any(k in mapping for k in d):
            store(name, {mapping.get(k, k): v for k, v in d.items()})
    for name in ID_LISTS:
        d = load(name, [])
        if isinstance(d, list) and any(isinstance(x, dict) and x.get("game") in mapping for x in d):
            store(name, [{**x, "game": mapping[x["game"]]} if isinstance(x, dict) and x.get("game") in mapping else x for x in d])


def fix_emulator_settings(folder, old, new):
    """A moved emulator's own settings files that name its old folder name the new one instead (RPCS3's games.yml, ...)."""
    pairs = [(old, new), (old.replace("\\", "/"), new.replace("\\", "/")), (old.replace("\\", "\\\\"), new.replace("\\", "\\\\"))]
    base = folder.rstrip("\\/").count(os.sep)
    for dirpath, dirs, files in os.walk(folder):
        if dirpath.count(os.sep) - base >= 4:
            dirs[:] = []
        for f in files:
            full = os.path.join(dirpath, f)
            try:
                if not f.lower().endswith(CONFIG_TEXT) or os.path.getsize(full) > 2 << 20:
                    continue
                with open(full, "rb") as fh:
                    raw = fh.read()
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            changed = text
            for a, b in pairs:
                changed = re.sub(re.escape(a), lambda m: b, changed, flags=re.I)
            if changed != text:
                with open(full, "w", encoding="utf-8", newline="") as fh:
                    fh.write(changed)


def held_inside(folder):
    """Which folders in this one Windows won't let go of (a program has a file in them open), as "PS5" or "PS5, PS3": each
    is renamed and straight back. "" if none is (the folder itself is what's held)."""
    held = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return ""
    for name in names:
        a = os.path.join(folder, name)
        if not os.path.isdir(a):
            continue
        b = a + ".ufe-check"
        try:
            os.rename(a, b)
            os.rename(b, a)
        except OSError:
            held.append(name)
    return ", ".join(held)


def move_to_home():
    """Settings › Libraries: the ROMs folder and Ultra Front End's own emulator downloads into C:\\Ultra-Front-End."""
    if update_busy():
        raise ValueError("Close the game first, then try again")
    cfg = config()
    plan = home_move_plan(cfg)
    moves = ([plan["roms"]] if plan["roms"] else []) + plan["emus"]
    if not moves:
        raise ValueError(plan["why"] or "Everything is already in C:\\Ultra-Front-End")
    with SCAN_LOCK:
        before = {g["id"]: game_id_sources(g) for g in STATE["games"]}
    os.makedirs(EMU_HOME, exist_ok=True)
    done, failed = [], []
    MOVING[0] = True  # (our own look through the folders could be the moment that holds one)
    try:
        for src, dst in moves:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(dst) and not os.listdir(dst):
                os.rmdir(dst)  # (the empty one a fresh setup may have made)
            for _ in range(40):  # Windows' indexer or antivirus can hold a folder for a moment: up to 20 seconds of tries
                try:
                    os.rename(src, dst)  # same drive: instant, nothing copied
                    done.append((src, dst))
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                failed.append(held_inside(src) or os.path.basename(src))
    finally:
        MOVING[0] = False
    for src, dst in done:
        if under(dst, EMU_HOME):
            fix_emulator_settings(dst, src, dst)
    if plan["roms"] and plan["roms"] in done:
        cfg["romRoot"] = plan["roms"][1]
    for e in (cfg.get("emulators") or {}).values():
        e["path"] = moved_path(e.get("path", ""), done)
        if isinstance(e.get("args"), list):
            e["args"] = [moved_path(a, done) if isinstance(a, str) and os.path.isabs(a) else a for a in e["args"]]
    for l in cfg.get("libraries", []):
        for k in ("path", "emulator"):
            if l.get(k):
                l[k] = moved_path(l[k], done)
        if isinstance(l.get("args"), list):
            l["args"] = [moved_path(a, done) if isinstance(a, str) and os.path.isabs(a) else a for a in l["args"]]
    store("config.json", cfg)
    mapping = {}
    for old_id, sources in before.items():
        for first, args in sources:
            new_x = " ".join([moved_path(first, done), *[moved_path(a, done) if os.path.isabs(a) else a for a in args]])
            new_id = gid(old_id.split("-", 1)[0], new_x)
            if new_id != old_id:
                mapping[old_id] = new_id
                break
    rekey_games(mapping)
    scan()
    return {"moved": [os.path.basename(d) for _, d in done], "failed": failed, "games": len(mapping)}


# ---------------------------------------------------------------- systems: the consoles you play, and their BIOS files
# Each system you choose gets ROMs\<console>\ and, when its emulator needs or can use files of the console's own, a
# ROMs\<console>\BIOS\ with a README. What's found there is set up for the emulator (BIOS_APPLY): a setting pointed at the
# folder, the emulator's own installer, arguments at launch, or (only adding, never replacing) a copy.
def need(file, short, req, why, *alts):
    """A file a console's emulator wants: shown on its page and in the README. alts: ways to recognise it (any one)."""
    return {"file": file, "short": short, "req": req, "why": why, "alts": alts}


def crc(*values, **more):
    return {"crc": values, **more}


SHAD_MODULES = ("libSceNgs2 libSceUlt libSceAvPlayer libSceAvPlayerStreaming libSceRtc libSceJpegDec libSceJpegEnc libScePngDec libScePngEnc "
                "libSceJson libSceJson2 libSceCesCs libSceAt9Enc libSceAudiodec libSceAudiodecCpu libSceAudiodecCpuDdp libSceAudiodecCpuM4aac "
                "libSceAudiodecCpuDtsHdLbr libSceAudiodecCpuHevag libSceFont libSceFontFt libSceFreeTypeOt libSceFreeTypeOl libSceFreeTypeOptOl "
                "libSceBeisobmf libSceBemp2sys libSceVideoNativeExtEssential libSceRudp libSceWkFontConfig libScePsmKitSystem libSceDepth "
                "libScePadTracker libSceMoveTracker libSceSystemGesture libSceXml").split()
SNES_CHIPS = ["dsp1.rom", "dsp1b.rom", "dsp2.rom", "dsp3.rom", "dsp4.rom", "dsp?.program.rom", "dsp?.data.rom", "st010.rom", "st011.rom",
              "st01?.program.rom", "st01?.data.rom", "st018.rom", "bs-x.bin", "sufamiturbo.sfc", "sgb1.sfc", "sgb2.sfc", "sgb_boot.bin", "sgb2_boot.bin"]
FDS = need("disksys.rom (or FdsBios.bin, 8 KB)", "disksys.rom", False, "The Famicom Disk System BIOS, for .fds games.", {"names": ["disksys.rom", "fdsbios.bin"], "sizes": (8192,)})
SWITCH = [
    need("prod.keys", "prod.keys", True, "The console’s keys. Without them games can’t be read.", {"names": ["prod.keys"]}),
    need("title.keys", "", False, "Keys for some games and add-ons.", {"names": ["title.keys"]}),
    need("key_retail.bin", "", False, "Only for amiibo.", {"names": ["key_retail.bin"]}),
    need("Firmware: the .nca files, loose, in a subfolder or as one .zip", "Firmware", True, "System fonts and menus. Many games won’t start without it.",
         {"names": ["*.nca"], "deep": True}, {"names": ["*.zip"], "zipnca": True}),
]
FLYCAST_BIOS = {"NAOMI": "naomi", "NAOMI 2": "naomi2", "Atomiswave": "awbios"}
BIOS_NEEDS = {
    "PS1": [need("PS1 BIOS (any name, 512 KB, for example scph1001.bin)", "BIOS", True,
                 "Games won’t start without it. One for each region (USA, Japan, Europe) works best.", {"sizes": (524288, 4194304, 4089584)})],
    "PS2": [need("PS2 BIOS (any name, about 4 MB)", "BIOS", True, "PCSX2 can’t start any game without it.", {"range": (4 << 20, 8 << 20)})],
    "PS3": [need("PS3UPDAT.PUP (the PS3 system update)", "PS3UPDAT.PUP", True, "The PS3 system software. It is installed into RPCS3 once; no game starts without it.",
                 {"names": ["ps3updat.pup"]}),
            need("Licence files (*.rap)", "", False, "Only for some downloaded games.", {"names": ["*.rap"]})],
    "PS4": [need("System modules (*.sprx, for example libSceNgs2.sprx)", "", False, "Some games need them for sound, video or text.",
                 {"names": [m.lower() + ".sprx" for m in SHAD_MODULES]}),
            need("System fonts, in fonts\\font and fonts\\font2", "", False, "Some games need them for text.", {"dirs": ["fonts/font", "fonts/font2"]})],
    "PS Vita": [need("Firmware update and font package (.PUP files, for example PSVUPDAT.PUP)", "Firmware", True,
                     "Most games won’t start without the firmware; the font package fixes missing text. They are installed into Vita3K once.",
                     {"names": ["*.pup"], "magic": b"SCEUF"})],
    "Switch": SWITCH,
    "Wii U": [need("keys.txt", "", False, "Only for WUD/WUX disc images.", {"names": ["keys.txt"]}),
              need("otp.bin (1 KB)", "", False, "Only for online play.", {"names": ["otp.bin"], "sizes": (1024,)}),
              need("seeprom.bin (512 bytes)", "", False, "Only for online play.", {"names": ["seeprom.bin"], "sizes": (512,)})],
    "GameCube": [need("IPL.bin, in a USA, EUR or JAP folder here for its region", "", False, "Only for the GameCube boot animation and menu.", {"names": ["ipl.bin"], "deep": True}),
                 need("dsp_rom.bin (8 KB)", "", False, "Only for the most accurate sound setting.", {"names": ["dsp_rom.bin"], "sizes": (8192,)}),
                 need("dsp_coef.bin (4 KB)", "", False, "Goes with dsp_rom.bin.", {"names": ["dsp_coef.bin"], "sizes": (4096,)}),
                 need("gba_bios.bin (16 KB)", "", False, "Only for linking a Game Boy Advance.", {"names": ["gba_bios.bin"], "sizes": (16384,)})],
    "3DS": [need("otp.bin, SecureInfo_A, LocalFriendCodeSeed_B, movable.sed", "", False, "Only for the HOME Menu and system features.",
                 {"names": ["otp.bin", "secureinfo_a", "localfriendcodeseed_b", "movable.sed"]}),
            need("seeddb.bin", "", False, "Only for a few newer games.", {"names": ["seeddb.bin"]}),
            need("shared_font.bin, keys.txt", "", False, "The system font, and extra keys.", {"names": ["shared_font.bin", "keys.txt"]})],
    "DS": [need("bios9.bin (4 KB)", "", False, "Only for the real DS menu or better accuracy, with the next two.", {"names": ["bios9.bin"], "sizes": (4096,)}),
           need("bios7.bin (16 KB)", "", False, "Goes with bios9.bin.", {"names": ["bios7.bin"], "sizes": (16384,)}),
           need("firmware.bin (256 KB)", "", False, "Goes with bios9.bin.", {"names": ["firmware.bin"], "sizes": (262144, 524288)}),
           need("dsi_bios9.bin", "", False, "DSi mode only, with the next three.", {"names": ["dsi_bios9.bin"], "sizes": (65536,)}),
           need("dsi_bios7.bin", "", False, "DSi mode only.", {"names": ["dsi_bios7.bin"], "sizes": (65536,)}),
           need("dsi_firmware.bin", "", False, "DSi mode only.", {"names": ["dsi_firmware.bin"], "sizes": (131072,)}),
           need("dsi_nand.bin", "", False, "DSi mode only.", {"names": ["dsi_nand.bin"]})],
    "GBA": [need("gba_bios.bin (16 KB)", "", False, "Only for the real boot screen; a few games run better with it.", {"names": ["gba_bios.bin"], "sizes": (16384,)})],
    "GBC": [need("gbc_bios.bin", "", False, "Only for the real boot animation.", {"names": ["gbc_bios.bin"], "sizes": (2304,)})],
    "Game Boy": [need("gb_bios.bin", "", False, "Only for the real boot screen.", {"names": ["gb_bios.bin"], "sizes": (256,)}),
                 need("sgb_bios.bin", "", False, "Only for Super Game Boy mode.", {"names": ["sgb_bios.bin"], "sizes": (256,)})],
    "SNES": [need("Chip files such as dsp1b.rom, st010.rom, st018.rom", "", False, "Only for the few games with those chips, like Super Mario Kart and Pilotwings.",
                  {"names": SNES_CHIPS})],
    "NES": [FDS],
    "FDS": [{**FDS, "short": "disksys.rom", "req": True, "why": "The Famicom Disk System BIOS. No disk game starts without it."}],
    "Xbox": [need("MCPX boot ROM (512 bytes, often mcpx_1.0.bin)", "Boot ROM", True, "The console’s boot ROM.", {"names": ["*.bin"], "sizes": (512,)}),
             need("Flash BIOS (.bin, 256 KB or 1 MB)", "BIOS", True, "The Xbox BIOS.", {"names": ["*.bin"], "sizes": (262144, 524288, 1048576)}),
             need("Hard disk image (.qcow2)", "Hard disk", True, "The Xbox hard disk.", {"names": ["*.qcow2"], "magic": b"QFI\xfb"}),
             need("eeprom.bin (256 bytes)", "", False, "Made by xemu if it’s missing.", {"names": ["*.bin"], "sizes": (256,)})],
    "Sega CD": [need("Sega CD BIOS for your games’ region (any name, for example bios_CD_U.bin)", "BIOS", True, "No CD game starts without it.",
                     {"sha256": ("fb477cdbf94c84424c2feca4fe40656d85393fe7b7b401911b45ad2eb991258c", "7133fc2dd2fe5b7d0acd53a5f10f3d00b5d31270239ad20d74ef32393e24af88",
                                 "fe608a2a07676a23ab5fd5eee2f53c9e2526d69a28aa16ccd85c0ec42e6933cb")})],
    "Master System": [need("Master System BIOS", "", False, "Only adds the boot screen.",
                           {"sha256": ("477617917a12a30f9f43844909dc2de6e6a617430f5c9a36306c86414a670d50", "67846e26764bd862f19179294347f7353a4166b62ac4198a5ec32933b7da486e")})],
    "Game Gear": [need("Game Gear BIOS", "", False, "Only adds the boot screen.", {"sha256": ("8c8a21335038285cfa03dc076100c1f0bfadf3e4ff70796f11f3dfaaab60eee2",)})],
    "64DD": [need("64DD IPL, Japan (any name)", "IPL", True, "No 64DD disk starts without it.", {"sha256": ("806400ec0df94b0755de6c5b8249d6b6a9866124c5ddbdac198bde22499bfb8b",)}),
             need("64DD IPL, US or development", "", False, "Only for disks made for those.",
                  {"sha256": ("e9fec87a45fba02399e88064b9e2f8cf0f2106e351c58279a87f05da5bc984ad", "9c2962a8b994a29e4cd04b3a6e4ed730a751414655ab6a9799ebf5fc08b79d44")})],
    "Saturn": [need("Saturn BIOS for your games’ region (any name)", "BIOS", True, "No game starts without it.", {"names": ["*"], "sizes": (524288,)})],  # every Saturn IPL is 512 KB
    "Dreamcast": [need("dc_boot.bin", "", False, "Some games run better with it.", {"names": ["dc_boot.bin"]}),
                  need("dc_flash.bin", "", False, "Goes with dc_boot.bin.", {"names": ["dc_flash.bin"]})],
    **{s: [need(f"{z}.zip", f"{z}.zip", True, "The board’s BIOS. No game starts without it.", {"names": [z + ".zip", z + ".7z"]})] for s, z in FLYCAST_BIOS.items()},
    "PC Engine CD": [need("syscard3.pce (System Card 3.0, 256 KB)", "syscard3.pce", True, "Every CD game needs it.",
                          {"names": ["syscard3.pce", "[bios] super cd-rom system (japan) (v3.0).pce"], "sizes": (262144,)}),
                     need("gecard.pce", "", False, "Only for the Games Express games.", {"names": ["gecard.pce", "[bios] games express cd card (japan).pce"], "sizes": (32768, 16384)})],
    "WonderSwan": [need("bootrom.ws, bootrom.wsc, bootrom_sc.wsc", "", False, "Only for the boot screens, when they’re turned on in Mesen.",
                        {"names": ["bootrom.ws"], "sizes": (4096,)}, {"names": ["bootrom.wsc", "bootrom_sc.wsc"], "sizes": (8192,)})],
    "Atari 7800": [need("7800.u7 (4 KB), loose or in a7800.zip", "7800.u7", True, "The 7800 BIOS. MAME won’t start a game without it.",
                        crc("5d13730c"), {"names": ["a7800.zip", "a7800.7z"]}),
                   need("c300558-001b.u7 (16 KB)", "", False, "Only for European (PAL) games.", crc("d5b61170"))],
    "Atari Lynx": [need("lynxboot.img (512 bytes)", "lynxboot.img", True, "The Lynx boot ROM. No game starts without it.", crc("e1ffecb6", "0d973c9d", sizes=(512,)))],
    "ColecoVision": [need("ColecoVision BIOS (any name, 8 KB)", "BIOS", True, "No game starts without it.", {"sha1": ("45bedc4cbdeac66c7df59e9e599195c778d86a92",)})],
    "MSX": [need("MSX system ROMs (any names)", "", False, "Only for disk, tape and BASIC software, or games that won’t run on the built-in C-BIOS.", {"names": ["*"], "range": (8192, 1 << 20)})],
    "Arcade": [need("BIOS sets, for example neogeo.zip", "", False, "Some games need their board’s BIOS set beside them or here.", {"names": ["*.zip", "*.7z"]})],
    "Neo Geo": [need("neogeo.zip", "neogeo.zip", True, "The Neo Geo BIOS. No game starts without it.", {"names": ["neogeo.zip", "neogeo.7z"]})],
    "Neo Geo CD": [need("neocdz.zip (neocd.bin and 000-lo.lo)", "neocdz.zip", True, "The Neo Geo CDZ BIOS. No game starts without it.",
                        {"names": ["neocdz.zip", "neocdz.7z"]}, crc("df9de490", "5a86cff2"))],
    "PC-FX": [need("pcfx.rom (BIOS v1.00)", "pcfx.rom", True, "No game starts without it.", {"sha256": ("4b44ccf5d84cc83daa2e6a2bee00fdafa14eb58bdf5859e96d8861a891675417",)})],
    "3DO": [need("panafz10.bin (or panafz1.bin, panafz1j.bin, goldstar.bin, sanyotry.bin…)", "BIOS", True, "A 3DO system ROM. No game starts without one.",
                 {"names": ["panafz10.bin", "panafz1.bin", "panafz1j.bin", "panafz10-norsa.bin", "panafz10e-anvil.bin", "panafz10e-anvil-norsa.bin",
                            "panafz1j-norsa.bin", "goldstar.bin", "sanyotry.bin", "3do_arcade_saot.bin"]}),
            need("Kanji ROMs (panafz1-kanji.bin and similar)", "", False, "Only for some Japanese games.", {"names": ["*kanji.bin"]})],
    "CD-i": [need("cdimono1.zip (cdi200.rom or cdi220b.rom, plus the servo and slave ROMs)", "cdimono1.zip", True, "No disc starts without it.",
                  {"names": ["cdimono1.zip", "cdimono1.7z"]}, crc("40c4e6b9", "279683ca"))],
    "Atari 5200": [need("5200.rom (2 KB)", "", False, "The real 5200 OS. A free one is built in.", crc("4248d3e3", "c2ba2613"))],
    "Intellivision": [need("exec.bin (8 KB), loose or in intv.zip", "exec.bin", True, "No game starts without it.", crc("cbce86f7"), {"names": ["intv.zip", "intv.7z"]}),
                      need("grom.bin (2 KB)", "grom.bin", True, "No game starts without it.", crc("683a4158"), {"names": ["intv.zip", "intv.7z"]})],
    "Vectrex": [need("exec_rom.bin (8 KB), loose or in vectrex.zip", "exec_rom.bin", True, "No game starts without it.", crc("ba13fb57"), {"names": ["vectrex.zip", "vectrex.7z"]})],
    "Odyssey 2": [need("o2bios.rom (1 KB), loose or in videopac.zip", "o2bios.rom", True, "No game starts without it.", crc("8016a315"),
                       {"names": ["videopac.zip", "odyssey2.zip", "videopac.7z", "odyssey2.7z"]})],
    "Pokemon Mini": [need("bios.min (4 KB)", "", False, "The real BIOS. A free one is built in.", {"names": ["bios.min"]})],
    "N-Gage": [need("N-Gage firmware: a .rpkg with its .rom, or a .vpl", "Firmware", True, "EKA2L1 runs the phone’s own system, installed once.", {"names": ["*.rpkg", "*.vpl"]})],
    "Amiga": [need("Kickstart 1.3 (A500, often kick34005.A500)", "Kickstart 1.3", True, "Most older games need it.", crc("c4f0f55f")),
              need("Kickstart 3.1 (A1200, often kick40068.A1200)", "Kickstart 3.1", True, "WHDLoad games and A1200 games need it.", crc("1483a091")),
              need("Kickstart 2.05 (A600, often kick37350.A600)", "Kickstart 2.05", True, "WHDLoad games need it.", crc("43b0df7b")),
              need("Kickstart 1.2 or 3.1 (A4000)", "", False, "Only for a few games.", crc("a6ce1636", "d6bae334"))],
    "Atari ST": [need("TOS ROM image (.img, .rom or .tos)", "", False, "Some games run better on the real TOS. Hatari’s free EmuTOS is used otherwise.",
                      {"names": ["*.img", "*.rom", "*.tos"], "sizes": (196608, 262144)})],
    "Atari 8-bit": [need("ATARIXL.ROM (16 KB)", "", False, "The real XL/XE OS. A free one is built in.", {"sizes": (16384,)}),
                    need("ATARIOSB.ROM (10 KB)", "", False, "The real 400/800 OS.", {"sizes": (10240,)}),
                    need("ATARIBAS.ROM (8 KB)", "", False, "Atari BASIC.", {"sizes": (8192,)})],
    "DOS": [need("Roland MT-32 or CM-32L ROMs, Sound Canvas ROMs, .sf2 SoundFonts", "", False, "Only for the original music of games made for them.", {"names": ["*"], "deep": True})],
    "ScummVM": [need("MT-32 ROMs (MT32_CONTROL.ROM, MT32_PCM.ROM), .sf2 SoundFonts, engine data files", "", False, "Only for the original music, or the few engines that need extra files.",
                     {"names": ["*"]})],
}
# Steps in the emulator's own menus, shown on the system's page (for what can't be set up from here)
BIOS_STEPS = {
    "PS3": "If it doesn’t install: in RPCS3 choose File › Install Firmware and pick PS3UPDAT.PUP in the BIOS folder.",
    "PS Vita": "If it doesn’t install: in Vita3K choose File › Install Firmware and pick each .PUP file in the BIOS folder, the firmware first.",
    "Switch": "Or in Eden: Tools › Install Decryption Keys, then Tools › Install Firmware.",
    "Wii": "Wii games need nothing extra. For a Wii NAND backup (nand.bin and keys.bin), in Dolphin choose Tools › Manage NAND › Import BootMii NAND Backup.",
    "3DS": "For the HOME Menu, run the Azahar Artic Setup Tool on your 3DS, then in Azahar choose File › Set Up System Files and enter the address it shows.",
    "N-Gage": "In EKA2L1, open its device installer (Install device), pick the firmware files in the BIOS folder and finish. The N-Gage shows up as RH-29.",
    "Xbox": "If it doesn’t work: in xemu choose Machine › Settings › System › Files and pick each file in the BIOS folder.",
}


class BiosLater(Exception):
    """The files can't be set up yet (the emulator is open, has never run...): said on the system's page."""


HASHES = {}  # (path, size, mtime) -> {"crc": ..., "sha1": ..., "sha256": ...}


def file_digest(path, kind, size, mtime):
    key = (path, size, mtime)
    if key not in HASHES:
        if size > 64 << 20:  # firmware updates and disk images are told apart by name and size alone
            HASHES[key] = {}
        else:
            import zlib
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:  # held open by another program, or still being copied: unknown for now, and not remembered
                return ""
            HASHES[key] = {"crc": f"{zlib.crc32(data) & 0xffffffff:08x}", "sha1": hashlib.sha1(data).hexdigest(), "sha256": hashlib.sha256(data).hexdigest()}
    return HASHES[key].get(kind, "")


def bios_files(folder):
    """(path, name, size, mtime, in a subfolder) for everything in a BIOS folder but its README."""
    out = []
    for dirpath, dirs, names in os.walk(folder):
        if dirpath.count(os.sep) - folder.count(os.sep) >= 3:
            dirs[:] = []
        for n in names:
            p = os.path.join(dirpath, n)
            if n.lower() in ("readme.txt", "thumbs.db", "desktop.ini", ".ds_store") or n.startswith(".") or not os.path.isfile(p):
                continue
            st = os.stat(p)
            out.append((p, n.lower(), st.st_size, st.st_mtime_ns, dirpath != folder))
    return out


def zip_has_nca(path):
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            return any(n.lower().endswith(".nca") for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def file_matches(alt, f):
    import fnmatch
    path, name, size, mtime, deep = f
    if deep and not alt.get("deep") and not alt.get("crc"):  # set folders (a7800\7800.u7) are searched by checksum
        return False
    if "names" in alt and not any(fnmatch.fnmatch(name, p) for p in alt["names"]):
        return False
    if "sizes" in alt and size not in alt["sizes"]:
        return False
    if "range" in alt and not alt["range"][0] <= size <= alt["range"][1]:
        return False
    try:  # one that can't be read (still being copied, held open by another program) counts as not there yet
        if "magic" in alt:
            with open(path, "rb") as fh:
                if fh.read(len(alt["magic"])) != alt["magic"]:
                    return False
        if alt.get("zipnca") and not zip_has_nca(path):
            return False
        return all(file_digest(path, k, size, mtime) in alt[k] for k in ("crc", "sha1", "sha256") if k in alt)
    except OSError:
        return False


BIOS_UNPACKED = {}  # zip path -> (size, modified) once unpacked this run; a note beside it keeps that across runs


def unpack_bios_zips(folder):
    """A BIOS often comes zipped (ps2-bios.zip): each zip in the BIOS folder is unpacked into it, once, so its files count
    and get set up. Flattened (only file names, so nothing lands outside the folder), nothing already there replaced, at
    most 2 GB, the zip kept. Returns how many files came out."""
    import zipfile
    out = 0
    try:
        zips = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".zip")]
    except OSError:
        return 0
    for z in zips:
        try:
            st = os.stat(z)
        except OSError:
            continue
        mark, stamp = z + ".unpacked", (st.st_size, int(st.st_mtime))
        if BIOS_UNPACKED.get(z) == stamp or os.path.exists(mark):
            continue
        try:
            with zipfile.ZipFile(z) as zf:
                total = 0
                for info in zf.infolist():
                    name = os.path.basename(info.filename.replace("\\", "/"))
                    if info.is_dir() or not name or name.startswith(".") or name.lower().endswith(".zip"):
                        continue
                    total += info.file_size
                    dest = os.path.join(folder, name)
                    if total > 2 << 30 or os.path.exists(dest):
                        continue
                    with zf.open(info) as src, open(dest + ".part", "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(dest + ".part", dest)
                    out += 1
            with open(mark, "w", encoding="utf-8") as f:
                f.write(f"Ultra Front End unpacked {os.path.basename(z)} into this folder. Delete this note to unpack it again.\n")
            BIOS_UNPACKED[z] = stamp
        except (OSError, zipfile.BadZipFile, RuntimeError):  # (a password-protected zip is a RuntimeError)
            BIOS_UNPACKED[z] = stamp
    return out


def bios_found(system, folder):
    """For each of the system's needs, the files in its BIOS folder that are it."""
    needs = BIOS_NEEDS.get(system, [])
    if needs and folder and os.path.isdir(folder):
        unpack_bios_zips(folder)
    try:
        files = bios_files(folder) if folder and os.path.isdir(folder) else []
    except OSError:
        files = []
    out = []
    for n in needs:
        hits = []
        for alt in n["alts"]:
            if "dirs" in alt:
                ok = all(os.path.isdir(os.path.join(folder, d)) and os.listdir(os.path.join(folder, d)) for d in alt["dirs"]) if files else False
                hits += [os.path.join(folder, d) for d in alt["dirs"]] if ok else []
            else:
                hits += [f[0] for f in files if f[0] not in hits and file_matches(alt, f)]
        out.append(hits)
    return out


def bios_state(system, folder):
    needs = BIOS_NEEDS.get(system, [])
    found = bios_found(system, folder) if needs else []
    missing = [n for n, f in zip(needs, found) if n["req"] and not f]
    label = (f"{missing[0]['short']} missing" if missing else "BIOS ✓" if any(found) else "Nothing needed") if needs else "Nothing needed"
    return {"label": label, "ok": not missing, "folder": bool(needs), "needs": [{"file": n["file"], "req": n["req"], "why": n["why"], "found": bool(f)}
                                                                              for n, f in zip(needs, found)]}


def bios_readme(system):
    needs = BIOS_NEEDS[system]
    emu = emulator_for(system) or "its emulator"
    lines = [f"{system} BIOS files", "", f"Put these files in this folder. Ultra Front End sets them up for {emu} for you",
             "(it may ask you to close the emulator first).", ""]
    for title, req in (("Needed:", True), ("Optional:", False)):
        items = [n for n in needs if n["req"] == req]
        if items:
            lines += [title] + [f"- {n['file']}: {n['why']}" for n in items] + [""]
    return "\r\n".join(lines)


def system_folder(root, system, create=False):
    """The ROMs subfolder that holds this system's games (whatever it's called), made when asked and missing."""
    try:
        for d in sorted(os.listdir(root)):
            if os.path.isdir(os.path.join(root, d)) and detect_system(os.path.join(root, d))["system"] == system:
                return os.path.join(root, d)
    except OSError:
        return None
    if create:
        os.makedirs(os.path.join(root, system), exist_ok=True)
        return os.path.join(root, system)
    return None


def bios_dir(cfg, system, create=False):
    root = cfg.get("romRoot")
    sub = root and os.path.isdir(root) and system_folder(root, system, create)
    return os.path.join(sub, "BIOS") if sub else None


def ensure_folders(system, cfg=None):
    """A chosen system's ROMs folder, and its BIOS folder with a README when its emulator can use any. True if one was made."""
    cfg = cfg or config()
    root = cfg.get("romRoot")
    if not root or not os.path.isdir(root) or system not in SYSTEM_GROUP:
        return False
    made = not system_folder(root, system)
    try:  # (a file named BIOS, or a folder named README.txt, is left alone; the other systems still get theirs)
        folder = bios_dir(cfg, system, create=True)
        if system in BIOS_NEEDS:
            for sub in {"PS4": ["fonts/font", "fonts/font2"], "GameCube": ["USA", "EUR", "JAP"]}.get(system, [""]):
                os.makedirs(os.path.join(folder, sub), exist_ok=True)
            readme, text = os.path.join(folder, "README.txt"), bios_readme(system)
            old = None
            if os.path.isfile(readme):
                with open(readme, encoding="utf-8", errors="replace", newline="") as f:  # newline="": the CRLFs as written
                    old = f.read()
            if old != text and (old is None or old.startswith(f"{system} BIOS files")):  # never over a README of the user's own
                with open(readme, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
    except OSError:
        log_error()
    return made


# --- changing an emulator's files: only while it's closed, backed up once, nothing replaced
def real_dir(exe):
    return os.path.dirname(os.path.realpath(exe))  # through WinGet's links to the real folder


def documents():
    """The Documents folder, wherever Windows keeps it (OneDrive can move it)."""
    try:
        import ctypes
        import uuid
        g = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7").bytes_le
        path = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.c_char_p(g), 0, None, ctypes.byref(path)) == 0:
            value = path.value
            ctypes.windll.ole32.CoTaskMemFree(path)
            return value
    except (OSError, AttributeError, ValueError):
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def appdata(local=False):
    return os.environ.get("LOCALAPPDATA" if local else "APPDATA") or os.path.expanduser("~")


def reg_value(key, name):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except (OSError, ImportError):
        return None


def emu_running(exe):
    return WIN and bool(folder_processes(real_dir(exe)))


def backup_once(path):
    if os.path.isfile(path) and not os.path.exists(path + ".bak"):
        shutil.copy2(path, path + ".bak")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(path + ".part", path)


def edit_text(path, change, create=False):
    """Change a settings file through change(lines) -> lines, keeping its line endings. True if it changed."""
    if not os.path.isfile(path) and not create:
        return False
    raw = ""
    if os.path.isfile(path):
        if not os.access(path, os.W_OK):
            raise ValueError(f"{os.path.basename(path)} is read-only")
        with open(path, "rb") as f:
            if f.read(2) in (b"\xff\xfe", b"\xfe\xff"):
                raise ValueError(f"{os.path.basename(path)} isn't a UTF-8 text file")
        with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
            raw = f.read()
    bom = "\ufeff" if raw.startswith("\ufeff") else ""
    nl = "\r\n" if "\r\n" in raw else "\n"
    new = bom + nl.join(change(raw[len(bom):].splitlines())) + nl
    if new == raw:
        return False
    backup_once(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path + ".part", "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(new)
        os.replace(path + ".part", path)
    except OSError:
        try:
            os.remove(path + ".part")
        except OSError:
            pass
        raise
    return True


def set_keys(lines, section, values):
    """INI or TOML: set key = value under [section], keeping every other line (and each line's own spacing)."""
    lines = list(lines)
    head = next((i for i, l in enumerate(lines) if re.fullmatch(r"\[\s*" + re.escape(section) + r"\s*\]", l.strip())), None)  # [ BIOS ] too
    spaced = not any(re.match(r"[^=\s]+=", l) for l in lines) or any(" = " in l for l in lines)
    if head is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + [f"[{section}]"] + [f"{k} = {v}" if spaced else f"{k}={v}" for k, v in values.items()]
        return lines
    end = next((i for i in range(head + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
    for k, v in values.items():
        at = next((i for i in range(head + 1, end) if "=" in lines[i] and lines[i].split("=", 1)[0].strip() == k), None)
        if at is not None:
            lines[at] = f"{k} = {v}" if " = " in lines[at] else f"{k}={v}"
        else:
            last = max([i for i in range(head, end) if lines[i].strip()])
            lines.insert(last + 1, f"{k} = {v}" if spaced else f"{k}={v}")
            end += 1
    return lines


def get_key(path, section, key):
    try:
        lines = read(path).splitlines()
    except OSError:
        return None
    inside = False
    for l in lines:
        if l.strip().startswith("["):
            inside = l.strip() == f"[{section}]"
        elif inside and "=" in l and l.split("=", 1)[0].strip() == key:
            return l.split("=", 1)[1].strip()
    return None


def toml_str(s):
    return f"'{s}'" if "'" not in s and "\n" not in s else json.dumps(s)


def add_file(src, dest):
    """Copy only into an empty place: "added", "same" (already there) or "kept" (a different file has that name)."""
    if os.path.exists(dest):
        return "same" if os.path.getsize(dest) == os.path.getsize(src) and file_sha256(dest) == file_sha256(src) else "kept"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest + ".part")
    os.replace(dest + ".part", dest)
    return "added"


def copied(results, where):
    n, kept = results.count("added"), results.count("kept")
    say = f"Copied {n} file{'s' if n != 1 else ''} into {where}" if n else f"Set up in {where}" if results.count("same") else f"Nothing to copy into {where}"
    return say + (f". {kept} left as {'they were' if kept > 1 else 'it was'}: a different file with that name is already there" if kept else "")


def add_files(paths, folder, name=None):
    return [add_file(p, os.path.join(folder, name or os.path.basename(p))) for p in paths]


def flat(found):
    return [p for hits in found for p in hits if os.path.isfile(p)]


def ran(cmd, cwd):
    """Run an emulator's own command-line installer and wait for it."""
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        pass


def stamp(path):
    st = os.stat(path)
    return f"{st.st_size}:{st.st_mtime_ns}"


# --- what each emulator does with them: (exe, BIOS folder, files found per need) -> what happened
def apply_duckstation(exe, bios, found):
    d = real_dir(exe)
    root = (d if any(os.path.isfile(os.path.join(d, n)) for n in ("portable.txt", "settings.ini")) else
            os.path.join(documents(), "DuckStation") if os.path.isdir(os.path.join(documents(), "DuckStation")) else os.path.join(appdata(True), "DuckStation"))
    ini = os.path.join(root, "settings.ini")
    if os.path.isfile(ini):  # a named BIOS that isn't in the new folder would fail to load, so they go back to "choose from the folder"
        edit_text(ini, lambda l: set_keys(l, "BIOS", {"SearchDirectory": bios, "PathNTSCU": "", "PathNTSCJ": "", "PathPAL": ""}))
        return "DuckStation looks for the BIOS in this folder"
    return copied(add_files(found[0], os.path.join(root, "bios")), "DuckStation’s BIOS folder")  # never run: it makes settings.ini itself


def apply_pcsx2(exe, bios, found):
    d = real_dir(exe)
    portable = next((os.path.join(d, n) for n in ("portable.ini", "portable.txt") if os.path.isfile(os.path.join(d, n))), None)
    root = os.path.join(d, read(portable).strip() if portable and portable.endswith(".txt") else "") if portable else os.path.join(documents(), "PCSX2")
    ini = os.path.join(root, "inis", "PCSX2.ini")
    names = [os.path.basename(p) for p in found[0]]
    if get_key(ini, "Folders", "Bios") is not None:  # only an INI PCSX2 wrote itself: a partial one makes it reset everything
        edit_text(ini, lambda l: set_keys(l, "Folders", {"Bios": bios}))
        if get_key(ini, "Filenames", "BIOS") not in names:
            edit_text(ini, lambda l: set_keys(l, "Filenames", {"BIOS": names[0]}))
        return "PCSX2 looks for the BIOS in this folder"
    extra = [os.path.join(bios, n) for n in os.listdir(bios) if n.lower().endswith((".rom1", ".rom2"))]
    return copied(add_files(found[0] + extra, os.path.join(root, "bios")), "PCSX2’s BIOS folder")


def rpcs3_paths(d):
    vfs, out = os.path.join(d, "config", "vfs.yml"), {}
    try:
        for l in read(vfs).splitlines():
            m = re.match(r'\s*"?([^":]+)"?\s*:\s*"?(.*?)"?\s*$', l)
            if m:
                out[m.group(1)] = m.group(2)
    except OSError:
        pass
    base = out.get("$(EmulatorDir)") or d + os.sep
    return [os.path.normpath((out.get(k) or default).replace("$(EmulatorDir)", base)) for k, default in
            (("/dev_flash/", "$(EmulatorDir)dev_flash/"), ("/dev_hdd0/", "$(EmulatorDir)dev_hdd0/"))]


def apply_rpcs3(exe, bios, found):
    d = real_dir(exe)
    flash, hdd = rpcs3_paths(d)
    version, say = os.path.join(flash, "vsh", "etc", "version.txt"), []
    if found[0] and not os.path.isfile(version):
        pup, state = found[0][0], load("bios-state.json", {})
        if state.get("rpcs3:" + pup) != stamp(pup):  # tried once per file: a failed install isn't retried on every scan
            ran([exe, "--headless", "--installfw", pup], d)  # not --no-gui: that refuses to install
            store("bios-state.json", {**state, "rpcs3:" + pup: stamp(pup)})
        if not os.path.isfile(version):
            raise BiosLater("RPCS3 couldn’t install PS3UPDAT.PUP. " + BIOS_STEPS["PS3"])
    if os.path.isfile(version):
        say.append("RPCS3 has the PS3 system software")
    if found[1]:
        say.append(copied(add_files(found[1], os.path.join(hdd, "home", "00000001", "exdata")), "RPCS3’s licence folder"))
    return ". ".join(say)


def full(folder):
    return os.path.isdir(folder) and bool(os.listdir(folder))


def apply_vita3k(exe, bios, found):
    d = real_dir(exe)
    portable = os.path.isdir(os.path.join(d, "portable"))
    conf = os.path.join(d, "portable", "config.yml") if portable else os.path.join(d, "config.yml")
    pref = ""
    try:
        pref = next((m.group(1).strip().strip("'\"") for m in (re.match(r"pref-path\s*:\s*(.*)$", l) for l in read(conf).splitlines()) if m), "")
    except OSError:
        pass
    fs = os.path.join(d, "portable", "fs") if portable else pref or os.path.join(appdata(), "Vita3K", "Vita3K")
    pups = sorted(found[0], key=os.path.getsize, reverse=True)  # the firmware (biggest) first, then the font package
    if full(os.path.join(fs, "vs0")):
        # the firmware's in: only a font package left to add (one PUP on its own may be just that)
        pups = (pups[1:] if len(pups) > 1 else pups) if not full(os.path.join(fs, "sa0")) else []
    state = load("bios-state.json", {})
    todo = [p for p in pups if state.get("vita3k:" + p) != stamp(p)]
    if todo and not os.path.isfile(conf):
        ran([exe, "--version"], d)  # writes its config first, or the firmware would land in the wrong folder
    for p in todo:
        ran([exe, "--firmware", p], d)
        state["vita3k:" + p] = stamp(p)
    if todo:
        store("bios-state.json", state)
    if not full(os.path.join(fs, "vs0")):
        raise BiosLater("Vita3K couldn’t install the firmware. " + BIOS_STEPS["PS Vita"])
    return "Vita3K has the PS Vita firmware" + ("" if full(os.path.join(fs, "sa0")) else " (no font package yet)")


def apply_shadps4(exe, bios, found):
    d = real_dir(exe)
    user = os.path.join(d, "user") if os.path.isdir(os.path.join(d, "user")) else os.path.join(appdata(), "shadPS4")
    conf = os.path.join(user, "config.json")
    if os.path.isfile(conf):
        def change(lines):
            data = json.loads("\n".join(lines))
            general = data.setdefault("General", {}) if isinstance(data, dict) else None
            if not isinstance(general, dict):
                raise ValueError("shadPS4’s config.json isn’t what was expected")
            if found[0]:
                general["sys_modules_dir"] = bios
            if found[1]:
                general["font_dir"] = os.path.join(bios, "fonts")
            return json.dumps(data, indent=4, ensure_ascii=False).splitlines()
        edit_text(conf, change)
        return "shadPS4 loads them from this folder"
    say = [copied(add_files(found[0], os.path.join(user, "sys_modules")), "shadPS4’s module folder")] if found[0] else []
    for sub in (["fonts/font", "fonts/font2"] if found[1] else []):
        src = os.path.join(bios, sub)
        add_files([os.path.join(src, n) for n in os.listdir(src) if os.path.isfile(os.path.join(src, n))], os.path.join(user, *sub.split("/")))
    return ". ".join(say) or "Copied the fonts into shadPS4"


def apply_eden(exe, bios, found):
    import zipfile
    d = real_dir(exe)
    root = os.path.join(d, "user") if os.path.isdir(os.path.join(d, "user")) else os.path.join(appdata(), "eden")
    nand = (get_key(os.path.join(root, "config", "qt-config.ini"), "Data%20Storage", "nand_directory") or "").strip('"')
    reg = os.path.join(os.path.normpath(nand) if nand and not nand.startswith("@") else os.path.join(root, "nand"), "system", "Contents", "registered")
    say = [copied(add_files(found[0] + found[1] + found[2], os.path.join(root, "keys")), "Eden’s keys folder")] if found[0] + found[1] + found[2] else []
    if os.path.isdir(reg) and any(n.lower().endswith(".nca") for n in os.listdir(reg)):
        say.append("Eden already has firmware, so it was left as it is")  # replacing it would mean emptying that folder first
    elif found[3]:
        n = 0
        for p in found[3]:
            if p.lower().endswith(".nca"):
                n += add_file(p, os.path.join(reg, os.path.basename(p))) == "added"
                continue
            with zipfile.ZipFile(p) as z:
                for m in z.infolist():
                    name = os.path.basename(m.filename)
                    if name.lower().endswith(".nca") and not os.path.exists(os.path.join(reg, name)):
                        os.makedirs(reg, exist_ok=True)
                        with z.open(m) as src, open(os.path.join(reg, name), "wb") as out:
                            shutil.copyfileobj(src, out)
                        n += 1
        say.append(f"Installed the firmware into Eden ({n} files)")
    return ". ".join(say)


def apply_cemu(exe, bios, found):
    d = real_dir(exe)
    user = (os.path.join(d, "portable") if os.path.isdir(os.path.join(d, "portable")) else d if os.path.isfile(os.path.join(d, "settings.xml"))
            else os.path.join(appdata(), "Cemu"))
    results = add_files(found[1] + found[2], user)
    for src in found[0]:  # keys.txt: the user's own lines stay, new disc keys are added under them
        dest = os.path.join(user, "keys.txt")
        if not os.path.exists(dest):
            results.append(add_file(src, dest))
            continue
        have = set(re.findall(r"\b[0-9a-f]{32}\b", read(dest).lower()))
        new = [l for l in read(src).splitlines() if re.fullmatch(r"\s*[0-9a-fA-F]{32}\s*(#.*)?", l) and l.split("#")[0].strip().lower() not in have]
        if new and edit_text(dest, lambda lines: lines + new):
            results.append("added")
    return copied(results, "Cemu’s folder")


def dolphin_user(exe):
    d = real_dir(exe)
    if reg_value(r"Software\Dolphin Emulator", "LocalUserConfig") or os.path.isfile(os.path.join(d, "portable.txt")):
        return os.path.join(d, "User")
    custom = reg_value(r"Software\Dolphin Emulator", "UserConfigPath")
    if custom:
        return custom
    docs = os.path.join(documents(), "Dolphin Emulator")
    return docs if os.path.isdir(docs) else os.path.join(appdata(), "Dolphin Emulator")


def apply_dolphin(exe, bios, found):
    user, results, say = dolphin_user(exe), [], []
    for p in found[0]:
        region = os.path.basename(os.path.dirname(p)).upper()
        if region in ("USA", "EUR", "JAP"):
            results.append(add_file(p, os.path.join(user, "GC", region, "IPL.bin")))
        else:
            say.append("Put IPL.bin in the USA, EUR or JAP folder for its region")
    results += add_files(found[1] + found[2], os.path.join(user, "GC"))
    ini = os.path.join(user, "Config", "Dolphin.ini")
    if found[3] and os.path.isfile(ini):
        edit_text(ini, lambda l: set_keys(l, "GBA", {"BIOS": found[3][0]}))
        say.append("Dolphin uses gba_bios.bin from this folder")
    return ". ".join(([copied(results, "Dolphin’s GC folder")] if results else []) + say)


AZAHAR_PLACES = {"otp.bin": "sysdata", "seeddb.bin": "sysdata", "shared_font.bin": "sysdata", "keys.txt": "sysdata", "secureinfo_a": "nand/rw/sys",
                 "localfriendcodeseed_b": "nand/rw/sys", "movable.sed": "nand/private"}


def apply_azahar(exe, bios, found):
    d = real_dir(exe)
    user = os.path.join(d, "user") if os.path.isdir(os.path.join(d, "user")) else os.path.join(appdata(), "Azahar")
    try:
        custom = bool(re.search(r"use_custom_storage\s*=\s*true", read(os.path.join(user, "config", "qt-config.ini"))))
    except OSError:
        custom = False
    results = [add_file(p, os.path.join(user, *AZAHAR_PLACES[os.path.basename(p).lower()].split("/"), os.path.basename(p))) for p in flat(found)
               if not (custom and AZAHAR_PLACES[os.path.basename(p).lower()].startswith("nand"))]  # a NAND moved elsewhere is set up in Azahar
    return copied(results, "Azahar’s folders") + (". Azahar keeps its NAND elsewhere: set those up with File › Set Up System Files" if custom else "")


def apply_melonds(exe, bios, found):
    d = real_dir(exe)
    conf = os.path.join(d, "portable", "melonDS.toml") if os.path.isdir(os.path.join(d, "portable")) else os.path.join(d, "melonDS.toml")
    if not os.path.isfile(conf):
        raise BiosLater("Open melonDS once and close it, then the frontend points it at these files")
    say = []
    if found[0] and found[1] and found[2]:  # all three, or melonDS couldn't start a game with its own ones switched off
        edit_text(conf, lambda l: set_keys(set_keys(l, "Emu", {"ExternalBIOSEnable": "true"}), "DS",
                                           {"BIOS9Path": toml_str(found[0][0]), "BIOS7Path": toml_str(found[1][0]), "FirmwarePath": toml_str(found[2][0])}))
        say.append("melonDS uses the DS BIOS from this folder")
    if all(found[3:7]):
        edit_text(conf, lambda l: set_keys(l, "DSi", {"BIOS9Path": toml_str(found[3][0]), "BIOS7Path": toml_str(found[4][0]),
                                                     "FirmwarePath": toml_str(found[5][0]), "NANDPath": toml_str(found[6][0])}))
        say.append("DSi mode uses the DSi files")
    return ". ".join(say) or "melonDS needs bios9.bin, bios7.bin and firmware.bin together. Until then it uses its own"


MGBA_KEYS = {"GBA": ["gba.bios"], "GBC": ["gbc.bios"], "Game Boy": ["gb.bios", "sgb.bios"]}


def mgba_apply(system):
    def apply(exe, bios, found):
        d = real_dir(exe)
        conf = os.path.join(d, "config.ini") if os.path.isfile(os.path.join(d, "portable.ini")) else os.path.join(appdata(), "mGBA", "config.ini")
        values = {k: f[0] for k, f in zip(MGBA_KEYS[system], found) if f}
        edit_text(conf, lambda l: set_keys(l, "ports.qt", {**values, "useBios": "1"}), create=True)
        return "mGBA uses the BIOS from this folder"
    return apply


def mesen_home(exe):
    d, docs = real_dir(exe), documents()
    return next((h for h in (d, os.path.join(docs, "MesenCE"), os.path.join(docs, "Mesen2")) if os.path.isfile(os.path.join(h, "settings.json"))), None)


def apply_mesen(exe, bios, found):
    home = mesen_home(exe)  # its first-time setup decides where it keeps its files
    if not home:
        raise BiosLater("Open Mesen once and finish its first-time setup, then the frontend copies these files into it")
    return copied(add_files(flat(found), os.path.join(home, "Firmware")), "Mesen’s Firmware folder")


def apply_xemu(exe, bios, found):
    d = real_dir(exe)
    conf = os.path.join(d, "xemu.toml") if os.path.isfile(os.path.join(d, "xemu.toml")) else os.path.join(appdata(), "xemu", "xemu", "xemu.toml")
    if os.path.isfile(conf) and re.search(r"^\s*files\s*(=|\.)", read(conf), re.M):  # written inline: no safe place to add the keys
        raise BiosLater(BIOS_STEPS["Xbox"])
    keys = {k: toml_str(f[0]) for k, f in zip(("bootrom_path", "flashrom_path", "hdd_path", "eeprom_path"), found) if f}
    edit_text(conf, lambda l: set_keys(l, "sys.files", keys), create=True)
    if all(found[:3]):  # while the welcome screen shows, xemu doesn't load the BIOS
        edit_text(conf, lambda l: set_keys(l, "general", {"show_welcome": "false"}))
    return "xemu uses the files in this folder"


def apply_ymir(exe, bios, found):
    d = real_dir(exe)
    conf = os.path.join(d, "Ymir.toml")
    if os.path.isfile(conf) and "[General.PathOverrides]" in read(conf).splitlines():
        edit_text(conf, lambda l: set_keys(l, "General.PathOverrides", {"IPLROMImages": toml_str(bios)}))
        return "Ymir looks for the BIOS in this folder"
    return copied(add_files(found[0], os.path.join(d, "roms", "ipl")), "Ymir’s BIOS folder")


# MAME looks for a system's ROMs in a folder named after it: loose files found by checksum go into one here
MAME_SETS = {"5d13730c": ("a7800", "7800.u7"), "d5b61170": ("a7800p", "c300558-001b.u7"), "cbce86f7": ("intv", "exec.bin"),
             "683a4158": ("intv", "ro-3-9503-003.u21"), "ba13fb57": ("vectrex", "exec_rom.bin"), "8016a315": ("videopac", "o2bios.rom"),
             "df9de490": ("neocdz", "neocd.bin"), "5a86cff2": ("neocdz", "000-lo.lo"), "40c4e6b9": ("cdimono1", "cdi200.rom"),
             "279683ca": ("cdimono1", "cdi220b.rom"), "7a3af407": ("cdimono1", "zx405037p__cdi_servo_2.1__b43t__llek9215.mc68hc705c8a_withtestrom.7201"),
             "688cda63": ("cdimono1", "zx405042p__cdi_slave_2.0__b43t__zzmk9213.mc68hc705c8a_withtestrom.7206")}


def apply_mame(exe, bios, found):
    results = []
    for f in bios_files(bios):
        p, name, size, mtime, deep = f
        if not deep and not name.endswith((".zip", ".7z")) and size <= 1 << 20:
            hit = MAME_SETS.get(file_digest(p, "crc", size, mtime))
            if hit:
                results.append(add_file(p, os.path.join(bios, *hit)))
    return (copied(results, "the BIOS folder, where MAME looks") + ". " if results.count("added") else "") + "MAME finds them here when a game starts"


def alias(name, emu):
    """Mednafen wants one exact file name in the folder: the file found is copied under it when it's called something else."""
    def apply(exe, bios, found):
        if not os.path.exists(os.path.join(bios, name)):
            add_file(found[0][0], os.path.join(bios, name))
        return f"{emu} reads {name} from this folder when a game starts"
    return apply


def apply_openmsx(exe, bios, found):
    return copied(add_files(flat(found), os.path.join(documents(), "openMSX", "share", "systemroms")), "openMSX’s system ROM folder")


def at_launch(emu):
    return lambda exe, bios, found: f"{emu} gets these files each time a game starts"


def apply_ngage(exe, bios, found):
    raise BiosLater(BIOS_STEPS["N-Gage"])


BIOS_APPLY = {
    "PS1": apply_duckstation, "PS2": apply_pcsx2, "PS3": apply_rpcs3, "PS4": apply_shadps4, "PS Vita": apply_vita3k, "Switch": apply_eden,
    "Wii U": apply_cemu, "GameCube": apply_dolphin, "3DS": apply_azahar, "DS": apply_melonds, "Xbox": apply_xemu, "Saturn": apply_ymir,
    **{s: mgba_apply(s) for s in MGBA_KEYS},
    **{s: apply_mesen for s in ("SNES", "NES", "FDS", "PC Engine CD", "WonderSwan")},
    **{s: apply_mame for s in ("Atari 7800", "Intellivision", "Vectrex", "Odyssey 2", "Neo Geo CD", "CD-i")},
    **{s: at_launch("MAME") for s in ("Arcade", "Neo Geo")},
    **{s: at_launch("ares") for s in ("Sega CD", "Master System", "Game Gear", "64DD")},
    **{s: at_launch("Flycast") for s in ("Dreamcast", "NAOMI", "NAOMI 2", "Atomiswave")},
    **{s: at_launch("RetroArch") for s in RA_BIOS},
    **{s: at_launch("Atari800") for s in ("Atari 5200", "Atari 8-bit")},
    "Atari ST": at_launch("Hatari"), "Amiga": at_launch("Amiberry"), "DOS": at_launch("DOSBox Staging"), "ScummVM": at_launch("ScummVM"),
    "Atari Lynx": alias("lynxboot.img", "Mednafen"), "PC-FX": alias("pcfx.rom", "Mednafen"),
    "ColecoVision": apply_openmsx, "MSX": apply_openmsx, "N-Gage": apply_ngage,
}
APPLIED = {}  # system -> {"msg": what happened last, "ok": False when something is left to do}
APPLY_LOCKS = {}  # one per emulator program: an installer run (RPCS3, Vita3K firmware) holds up only that emulator's systems
APPLY_LOCK = threading.Lock()  # guards APPLY_LOCKS and APPLY_SOON


def apply_bios(system, wait=True):
    """Set up the BIOS files found in this system's folder for its emulator, when there are any. wait=False (at launch):
    skipped while that emulator's files are already being set up."""
    if system not in BIOS_APPLY or MAC:  # (on a Mac the emulators' own settings hold their BIOS folders: not set up from here yet)
        return
    cfg = config()
    folder = bios_dir(cfg, system)
    found = bios_found(system, folder) if folder else []
    if not any(found):
        APPLIED.pop(system, None)
        return
    exe = cfg.get("emulators", {}).get(system, {}).get("path", "")
    name = emulator_for(system) or "its emulator"
    if not os.path.isfile(exe):
        APPLIED[system] = {"msg": f"Install {name} to use these files", "ok": False}
        return
    if emu_running(exe):
        APPLIED[system] = {"msg": f"Close {name} so the frontend can set these files up", "ok": False}
        return
    with APPLY_LOCK:
        lock = APPLY_LOCKS.setdefault(os.path.normcase(os.path.abspath(exe)), threading.Lock())
    if not lock.acquire(blocking=wait):
        return
    try:
        APPLIED[system] = {"msg": BIOS_APPLY[system](exe, folder, found), "ok": True}
    except BiosLater as e:
        APPLIED[system] = {"msg": str(e), "ok": False}
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as e:  # (an emulator config of an unexpected shape too)
        APPLIED[system] = {"msg": f"Couldn’t set them up: {e}", "ok": False}
        log_error()
    finally:
        lock.release()


APPLY_SOON = {"busy": False, "again": False}


def apply_soon():
    """Every chosen system's BIOS files, set up in the background (again once more if asked while it runs)."""
    def run():
        while True:
            for s in config().get("systems") or []:
                try:
                    apply_bios(s)
                except Exception:
                    log_error()
            with APPLY_LOCK:
                if not APPLY_SOON["again"]:
                    APPLY_SOON["busy"] = False
                    return
                APPLY_SOON["again"] = False
    with APPLY_LOCK:
        if APPLY_SOON["busy"]:
            APPLY_SOON["again"] = True
            return
        APPLY_SOON["busy"] = True
    threading.Thread(target=run, daemon=True).start()


# --- arguments worked out at launch ({auto})
def ares_firmware(prefix, regions):
    def args(rom, bios, found):
        files = bios_files(bios) if os.path.isdir(bios) else []
        out = []
        for region, digests in regions.items():
            hit = next((f[0] for f in files if not f[4] and f[2] <= 4 << 20 and file_digest(f[0], "sha256", f[2], f[3]) in digests), None)
            out += ["--setting", f"{prefix}/Firmware/BIOS.{region}={hit}"] if hit else []
        return out
    return args


SMS_WEST = ("477617917a12a30f9f43844909dc2de6e6a617430f5c9a36306c86414a670d50",)  # the US and European BIOS are one file


def atari5200_args(rom, bios, found):
    kind = None if rom.lower().endswith(".car") else {4096: "20", 8192: "19", 16384: "6", 32768: "4", 40960: "7"}.get(os.path.getsize(rom))
    return (["-cart-type", kind] if kind else []) + (["-5200_rom", found[0][0]] if found and found[0] else [])  # or it asks for the type


def amiga_args(rom, bios, found):
    now = sorted((f[1], f[2], f[3]) for f in bios_files(bios)) if os.path.isdir(bios) else []
    state = load("bios-state.json", {})
    if state.get("amiga:" + bios) == repr(now):
        return []
    store("bios-state.json", {**state, "amiga:" + bios: repr(now)})
    return ["--rescan-roms"]  # new Kickstarts: Amiberry looks through the folder again


PAL_TAG = re.compile(r"\([^)]*\b(Europe|PAL)\b[^)]*\)", re.I)


def pal_machine(ntsc, pal, pal_only):
    """MAME's PAL machine for a game tagged (Europe) or (PAL), or when only a PAL BIOS is there."""
    return lambda rom, bios, found: [pal if PAL_TAG.search(os.path.basename(rom)) or pal_only(found) else ntsc]


AUTO_ARGS = {
    "Atari 7800": pal_machine("a7800", "a7800p", lambda found: len(found) > 1 and found[1] and not found[0]),
    "Odyssey 2": pal_machine("odyssey2", "videopac", lambda found: bool(found and found[0]) and all(os.path.basename(p).lower().startswith("videopac") for p in found[0])),
    "Sega CD": ares_firmware("MegaCD", {"US": ("fb477cdbf94c84424c2feca4fe40656d85393fe7b7b401911b45ad2eb991258c",),
                                        "Japan": ("7133fc2dd2fe5b7d0acd53a5f10f3d00b5d31270239ad20d74ef32393e24af88",),
                                        "Europe": ("fe608a2a07676a23ab5fd5eee2f53c9e2526d69a28aa16ccd85c0ec42e6933cb",)}),
    "Master System": ares_firmware("MasterSystem", {"US": SMS_WEST, "Europe": SMS_WEST, "Japan": ("67846e26764bd862f19179294347f7353a4166b62ac4198a5ec32933b7da486e",)}),
    "Game Gear": ares_firmware("GameGear", {"World": ("8c8a21335038285cfa03dc076100c1f0bfadf3e4ff70796f11f3dfaaab60eee2",)}),
    "64DD": ares_firmware("Nintendo64DD", {"Japan": ("806400ec0df94b0755de6c5b8249d6b6a9866124c5ddbdac198bde22499bfb8b",),
                                           "US": ("e9fec87a45fba02399e88064b9e2f8cf0f2106e351c58279a87f05da5bc984ad",),
                                           "DEV": ("9c2962a8b994a29e4cd04b3a6e4ed730a751414655ab6a9799ebf5fc08b79d44",)}),
    "Atari 5200": atari5200_args,
    "Atari 8-bit": lambda rom, bios, found: [a for flag, f in zip(("-xlxe_rom", "-osb_rom", "-basic_rom"), found) if f for a in (flag, f[0])],
    "Atari ST": lambda rom, bios, found: ["--tos", found[0][0]] if found and found[0] else [],
    "Amiga": amiga_args,
    "DOS": lambda rom, bios, found: ["--set", f"romdir={bios}", "--set", f"soundcanvas_rom_dir={bios}"] if any(found) else [],  # only when there's something to use
}


def scummvm_id(folder):
    """A game folder's ScummVM id from a .scummvm or .svm file inside it, or let ScummVM work it out."""
    try:
        for n in os.listdir(folder):
            if n.lower().endswith((".scummvm", ".svm")):
                gid_ = read(os.path.join(folder, n)).strip().splitlines()[:1]
                if gid_ and re.fullmatch(r"[A-Za-z0-9_:-]{1,64}", gid_[0].strip()):
                    return gid_[0].strip()
    except OSError:
        pass
    return "--auto-detect"


def retroarch_cfg(system, bios):
    """A config RetroArch adds for this launch only: the BIOS folder, and never saving it into its own settings."""
    path = os.path.join(DATA, f"retroarch-{safe_name(system)}.cfg")
    write_text(path, f'system_directory = "{bios}"\nconfig_save_on_exit = "false"\n')
    return path


def launch_args(game, L, rom):
    w, h = screen_size()
    system = game.get("system")
    romdir = L.get("romdir") or os.path.dirname(rom)
    bios = os.path.join(romdir, "BIOS")
    values = {"{rom}": rom, "{screenw}": str(w), "{screenh}": str(h), "{bios}": bios, "{romdir}": romdir, "{romfolder}": os.path.dirname(rom),
              "{gamedir}": rom if os.path.isdir(rom) else os.path.dirname(rom), "{basename}": os.path.splitext(os.path.basename(rom))[0]}
    out = []
    for a in L["args"]:
        if a == "{auto}":
            out += AUTO_ARGS[system](rom, bios, bios_found(system, bios)) if system in AUTO_ARGS else []
            continue
        if a == "{gameid}":
            out.append(scummvm_id(rom))
            continue
        if "{bioscfg}" in a:
            a = a.replace("{bioscfg}", retroarch_cfg(system, bios))
        folders = "{romfolder}" in a
        for k, v in values.items():
            a = a.replace(k, v)
        if folders:  # a game at the top of its ROMs folder: that folder once
            a = ";".join(dict.fromkeys(a.split(";")))
        out.append(a)
    return out


# --- which systems are chosen
def sync_systems(counts):
    """Systems with games are added by themselves; the first time (an older setup), so is every one with an emulator."""
    cfg = config()
    have, removed = cfg.get("systems"), set(cfg.get("systemsRemoved") or [])
    chosen = list(have) if have is not None else [s for s in ROM_FOLDERS if cfg.get("emulators", {}).get(s, {}).get("path")]
    added = [s for s in ROM_FOLDERS if counts.get(f"ROMs/{s}") and s not in chosen and s not in removed]
    if have is not None and not added:
        return
    cfg["systems"] = [s for s in ROM_FOLDERS if s in chosen or s in added]
    store("config.json", cfg)
    for s in cfg["systems"] if have is None else added:
        ensure_folders(s, cfg)
    apply_soon()


def choose_systems(systems, install):
    cfg = config()
    old = set(cfg.get("systems") or [])
    picked = [s for s in ROM_FOLDERS if s in systems]
    with_games = {s for s in ROM_FOLDERS if STATE["counts"].get(f"ROMs/{s}")}
    cfg["systems"] = picked
    cfg["systemsRemoved"] = sorted(((set(cfg.get("systemsRemoved") or []) | (with_games | old)) - set(picked)) & set(ROM_FOLDERS))  # left unticked: not added back
    store("config.json", cfg)
    for s in picked:
        ensure_folders(s, cfg)
    unqueue(set(ROM_FOLDERS) - set(picked))
    if install:
        queue_install(picked)
    apply_soon()


def add_system(system):
    cfg = config()
    cfg["systems"] = [s for s in ROM_FOLDERS if s in (cfg.get("systems") or []) or s == system]
    cfg["systemsRemoved"] = [s for s in cfg.get("systemsRemoved") or [] if s != system]
    store("config.json", cfg)
    ensure_folders(system, cfg)
    queue_install([system])
    apply_soon()


def remove_system(system):
    """Only stops listing it: its games, BIOS files and emulator stay where they are."""
    cfg = config()
    cfg["systems"] = [s for s in cfg.get("systems") or [] if s != system]
    cfg["systemsRemoved"] = sorted(set(cfg.get("systemsRemoved") or []) | {system})
    store("config.json", cfg)
    unqueue({system})


def unqueue(systems):
    """Take these systems out of installs still waiting their turn; a job left with none is dropped."""
    with QUEUE_COND:
        for j in QUEUE["jobs"]:
            if j["state"] == "waiting" and not j.get("extra"):
                j["systems"] = [s for s in j["systems"] if s not in systems]
        QUEUE["jobs"] = [j for j in QUEUE["jobs"] if j["systems"] or j.get("extra") or j["state"] != "waiting"]


# --- installing emulators one at a time, in the background
QUEUE = {"jobs": [], "next": 0, "worker": None, "batch": 0}  # batch: the first job queued since it was last idle ("2 of 5")
QUEUE_COND = threading.Condition()


def new_batch():
    """(Under QUEUE_COND, before a job goes in.) Queued when nothing is waiting or installing: the count starts again from it."""
    if not any(j["state"] in ("waiting", "installing") for j in QUEUE["jobs"]):
        QUEUE["batch"] = QUEUE["next"] + 1


def queue_install(systems):
    emus = config().get("emulators", {})
    with QUEUE_COND:
        for s in systems:
            package = emu_table().get(s)
            if not (WIN or MAC) or not package or package[1] == "manual" or os.path.exists(emus.get(s, {}).get("path", "")):
                continue
            job = next((j for j in QUEUE["jobs"] if j["package"] == package and j["state"] in ("waiting", "installing")), None)
            if job:  # one emulator for several systems (ares, MAME...) installs once
                job["systems"] += [] if s in job["systems"] else [s]
                continue
            new_batch()
            QUEUE["next"] += 1
            QUEUE["jobs"].append({"id": QUEUE["next"], "emulator": package[0], "package": package, "systems": [s], "state": "waiting", "error": ""})
        if not QUEUE["worker"]:
            QUEUE["worker"] = threading.Thread(target=install_worker, daemon=True)
            QUEUE["worker"].start()
        QUEUE_COND.notify_all()


def install_worker():
    while True:
        with QUEUE_COND:
            QUEUE_COND.wait_for(lambda: any(j["state"] == "waiting" for j in QUEUE["jobs"]))
            job = next(j for j in QUEUE["jobs"] if j["state"] == "waiting")
            job["state"] = "installing"
        JOB_LOCAL.job = job  # the downloads and winget report their progress to it
        try:
            install_job(job)
        finally:
            JOB_LOCAL.job = None


def install_job(job):
    if job.get("update"):  # a newer version of an emulator that's already set up
        try:
            update_emulator(job["update"])
            job.update(state="ready", error="")
        except Exception as e:
            job.update(state="failed", error=(str(e) or type(e).__name__)[:200])
            if not isinstance(e, ValueError):
                log_error()
        return
    if job.get("launcher"):  # a game launcher (Steam, GOG Galaxy...): winget, then its games are looked for
        try:
            winget_install(job["package"][0], job["emulator"])
            job.update(state="ready" if launcher_installed(job["launcher"]) else "failed",
                       error="" if launcher_installed(job["launcher"]) else "Installed, but it wasn’t found where expected. Restart the frontend.")
        except Exception as e:
            job.update(state="failed", error=(str(e) or type(e).__name__)[:200])
            if not isinstance(e, ValueError):
                log_error()
        try:
            scan()
        except Exception:
            log_error()
        return
    if job.get("extra"):  # an extra (PresentMon): no systems to connect or rescan
        try:
            EXTRAS[job["extra"]][1]()
            job.update(state="ready", error="")
        except Exception as e:
            job.update(state="failed", error=(str(e) or type(e).__name__)[:200])
            if not isinstance(e, ValueError):
                log_error()
        return
    try:
        connect_emulator(job["package"])  # already on this PC: nothing to download
        if not all(os.path.exists(config().get("emulators", {}).get(s, {}).get("path", "")) for s in job["systems"]):  # (a Mac app is a folder)
            install_emulator(job["systems"][0])
        emus = config().get("emulators", {})
        missing = [s for s in job["systems"] if not os.path.exists(emus.get(s, {}).get("path", ""))]
        job.update(state="failed" if missing else "ready", error="Installed, but its program wasn’t found. Use Choose program." if missing else "")
    except Exception as e:
        job.update(state="failed", error=(str(e) or type(e).__name__)[:200])
        if not isinstance(e, ValueError):
            log_error()
    try:
        scan()
    except Exception:
        log_error()
    apply_soon()


# ---------------------------------------------------------------- emulators kept up to date
EMU_SETTINGS = (".yml", ".yaml", ".ini", ".cfg", ".json", ".toml", ".xml", ".conf", ".txt")
EMU_UPDATES = {"checked": 0.0, "github": {}, "winget": {}, "error": ""}  # what's newer: {name: {"system", "from", "to"}}
EMU_UPDATE_LOCK = threading.Lock()


def own_github_emus(cfg=None):
    """The downloaded emulators Ultra Front End installed and uses: {name: (folder, systems)}. Only its own folders in
    C:\\Ultra-Front-End\\Emulators or ~\\Emulators (never a build you put somewhere yourself)."""
    cfg = cfg or config()
    out = {}
    for name, (_, _, program) in GITHUB_EMUS.items():
        for home in (EMU_HOME, OLD_EMU_HOME):
            folder = os.path.join(home, name)
            systems = [s for s, e in (cfg.get("emulators") or {}).items() if under(e.get("path", ""), folder)]
            if systems and os.path.isfile(os.path.join(folder, program)):
                out[name] = (folder, systems)
                break
    return out


def winget_emus(cfg=None):
    """Emulators with an installer from winget that Ultra Front End can install: {package id: (name, systems)}."""
    cfg = cfg or config()
    out = {}
    for system, entry in EMU_INSTALL.items():
        if not entry:
            continue
        name, source = entry
        pkg = "Libretro.RetroArch" if source.startswith("retroarch:") else source
        if re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", pkg or "") and os.path.exists((cfg.get("emulators") or {}).get(system, {}).get("path", "")):
            n, systems = out.get(pkg, ("RetroArch" if pkg == "Libretro.RetroArch" else name, []))
            out[pkg] = (n, systems + [system])
    return out


def winget_upgrades(ids):
    """{package id: (installed version, newer version)} for those of ids that winget has an update for."""
    winget = shutil.which("winget")
    if not winget or not ids:
        return {}
    r = subprocess.run([winget, "upgrade", "--source", "winget", "--accept-source-agreements", "--disable-interactivity"],
                       capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    text = r.stdout.decode("utf-8", "replace")
    out = {}
    for line in text.splitlines():
        words = line.split()
        for i, w in enumerate(words):
            if w in ids and len(words) > i + 2 and re.match(r"^[<>]?[0-9v]", words[i + 1]):
                out[w] = (words[i + 1].lstrip("<>"), words[i + 2])
    return out


def check_emulator_updates():
    """Which of the app's own emulators have something newer (GitHub downloads by release date, installers by winget)."""
    refind_moved(list(config().get("emulators") or {}))  # any whose program has moved since (an update, or by hand)
    cfg, versions = config(), load("emu-versions.json", {})
    github = {}
    for name, (folder, systems) in own_github_emus(cfg).items():
        try:
            asset, published = github_latest(name)
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            continue
        if not asset:
            continue
        had = versions.get(name) or {}
        if had.get("keep"):  # a build picked by hand (emu-versions.json "keep": true) stays until it's set back
            continue
        if had.get("asset"):
            newer = asset["name"] != had["asset"] or published > (had.get("published") or "")
        else:  # installed before versions were kept: newer than the program on disk, by more than a day
            exe = os.path.join(folder, GITHUB_EMUS[name][2])
            newer = published > time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(exe) + 86400))
        if newer:
            github[name] = {"systems": systems, "to": asset["name"], "folder": folder}
    wing = winget_emus(cfg)
    try:
        ups = winget_upgrades(set(wing))
    except (OSError, subprocess.TimeoutExpired):
        ups = {}
    winget = {wing[p][0]: {"systems": wing[p][1], "package": p, "from": a, "to": b} for p, (a, b) in ups.items()}
    try:
        installed = winget_installed(set(wing))
    except (OSError, subprocess.TimeoutExpired):
        installed = EMU_UPDATES.get("installed") or {}
    EMU_UPDATES.update(checked=time.time(), github=github, winget=winget, installed=installed, error="")
    EMU_VERSIONS.clear()
    versions["_checked"] = time.time()
    store("emu-versions.json", versions)


def emulator_running(folder):
    """A program from this emulator's folder is running (an update would fail on its files, or pull them from under it)."""
    if not WIN:
        return False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-Process | Where-Object { $_.Path } | ForEach-Object { $_.Path }"],
                           capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return any(under(p.strip(), folder) for p in r.stdout.decode("utf-8", "replace").splitlines() if p.strip())
    except (OSError, subprocess.TimeoutExpired):
        return True  # can't tell: try another time


def refind_moved(systems):
    """Systems whose emulator program isn't where it was any more (an update moved it): found again and set, keeping
    their arguments. Returns the systems fixed."""
    cfg = config()
    emus = cfg.get("emulators") or {}
    gone = [s for s in systems if emus.get(s, {}).get("path") and not os.path.exists(emus[s]["path"])]
    if not gone:
        return []
    found = find_emulators()
    fixed = []
    for s in gone:
        if found.get(s):
            emus[s]["path"] = found[s]
            fixed.append(s)
    if fixed:
        store("config.json", cfg)
        EMU_VERSIONS.clear()
    return fixed


def update_emulator(name):
    """Bring one of the app's emulators up to date: a newer download unpacked over it, or its installer through winget."""
    info = EMU_UPDATES["github"].get(name)
    if info:
        if emulator_running(info["folder"]):
            raise ValueError(f"Close {name} first, then try again")
        install_from_github(name, info["folder"])
        EMU_UPDATES["github"].pop(name, None)
        return
    info = EMU_UPDATES["winget"].get(name)
    if info:
        winget_install(info["package"], name)  # installing a package that's there brings it up to date
        EMU_UPDATES["winget"].pop(name, None)
        refind_moved(info["systems"])  # an update can move it (into C:\\Ultra-Front-End\\Emulators): follow it there
        return
    raise ValueError(f"{name} is up to date")


def queue_emulator_updates(names):
    """Each into the install queue as an update job (progress in Settings › Systems)."""
    added = 0
    with QUEUE_COND:
        for name in names:
            info = EMU_UPDATES["github"].get(name) or EMU_UPDATES["winget"].get(name)
            if not info or any(j.get("update") == name and j["state"] in ("waiting", "installing") for j in QUEUE["jobs"]):
                continue
            new_batch()
            QUEUE["next"] += 1
            QUEUE["jobs"].append({"id": QUEUE["next"], "emulator": name, "update": name, "systems": list(info["systems"]),
                                  "package": (name, "update"), "state": "waiting", "error": ""})
            added += 1
        if added and not QUEUE["worker"]:
            QUEUE["worker"] = threading.Thread(target=install_worker, daemon=True)
            QUEUE["worker"].start()
        QUEUE_COND.notify_all()
    return added


# ---------- which version each emulator is ----------
EMU_VERSIONS = {}  # (program, modified) -> what to show


def exe_version(path):
    """The version written in a Windows program (its version resource), or ""."""
    if not WIN:
        return ""
    import ctypes
    import ctypes.wintypes as W
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(path, None)
    buf = ctypes.create_string_buffer(size) if size else None
    if not buf or not ver.GetFileVersionInfoW(path, 0, size, buf):
        return ""
    ptr, n = ctypes.c_void_p(), W.UINT()
    if ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) and n.value >= 4:
        lang, cp = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
        for key in ("ProductVersion", "FileVersion"):
            sptr, sn = ctypes.c_void_p(), W.UINT()
            if ver.VerQueryValueW(buf, f"\\StringFileInfo\\{lang:04x}{cp:04x}\\{key}", ctypes.byref(sptr), ctypes.byref(sn)) and sn.value:
                text = ctypes.wstring_at(sptr, sn.value).strip("\x00 ").strip()
                if text and text not in ("0.0.0.0", "1.0.0.0"):
                    return text
    if ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)) and n.value >= 52:
        f = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        nums = (f[4] >> 16, f[4] & 0xFFFF, f[5] >> 16, f[5] & 0xFFFF)
        if any(nums) and nums != (1, 0, 0, 0):
            return ".".join(map(str, nums))
    return ""


def tidy_version(v):
    """"2.1.1+137ae7ce3bf3..." -> "2.1.1+137ae7c"; ".0.1.5664-2df3434" -> "0.1.5664-2df3434"."""
    v = v.strip().lstrip(".")
    return re.sub(r"([+-])([0-9a-f]{7})[0-9a-f]{5,}$", r"\1\2", v)


def emulator_version(program, system=None):
    """What version an emulator is, from the best place there is: the release Ultra Front End installed, the version in
    the program, Windows' list of installed apps (winget, read with the daily update check), a build code in its folder's
    name, or when the program was built."""
    try:
        stamp = os.path.getmtime(program)
    except OSError:
        return ""
    key = (os.path.normcase(program), stamp)
    if key in EMU_VERSIONS:
        return EMU_VERSIONS[key]
    v = ""
    versions = load("emu-versions.json", {})
    for name in GITHUB_EMUS:
        rec = versions.get(name) or {}
        if rec.get("folder") and under(program, rec["folder"]):
            v = rec.get("tag") or (f"build of {rec['published'][:10]}" if rec.get("published") else "")
            break
    v = v or tidy_version(exe_version(program))
    if not v and system:
        package = (EMU_INSTALL.get(system) or (None, ""))[1]
        v = (EMU_UPDATES.get("installed") or {}).get(package, "")
    if not v:  # "eglantine-windows-x86_64-ec667e25f9ab...", "Dolphin-2609a" (its program is a folder further in): the build in the folder's name
        here = os.path.dirname(program)
        for folder in (os.path.basename(here), os.path.basename(os.path.dirname(here))):
            m = re.search(r"[-_ ]v?(\d+(?:\.\d+)+[\w.-]*|\d{3,6}[a-z]?|[0-9a-f]{7,40})$", folder, re.I)
            if m and not re.search(r"x86|x64|win(32|64)|_[0-9a-z]{13}$", m.group(0), re.I):  # (not "x86_64", nor a Windows package's publisher code)
                code = m.group(1)
                v = f"build {code[:7]}" if re.fullmatch(r"[0-9a-f]{7,40}", code, re.I) and re.search(r"[a-f]", code, re.I) and len(code) >= 7 and not re.fullmatch(r"\d{3,6}[a-z]?", code) else code
                break
    v = v or time.strftime("build of %d %b %Y", time.localtime(stamp))
    EMU_VERSIONS[key] = v
    return v


def winget_installed(ids):
    """{package id: installed version} from winget's list, for the emulators that don't say their version themselves."""
    winget = shutil.which("winget")
    if not winget or not ids:
        return {}
    r = subprocess.run([winget, "list", "--source", "winget", "--accept-source-agreements", "--disable-interactivity"],
                       capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = {}
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        words = line.split()
        for i, w in enumerate(words):
            if w in ids and len(words) > i + 1 and re.match(r"^[<>]?[0-9v]", words[i + 1]):
                out[w] = words[i + 1].lstrip("<>")
    return out


def watch_emulator_updates():
    """Once a day: look for newer emulators. Downloaded ones update by themselves while nothing is running; ones with an
    installer wait for a press in Settings › Systems (their installers may ask Windows for permission)."""
    time.sleep(300)  # after start-up, an update of the app itself, and the first scans
    while True:
        try:
            if time.time() - (load("emu-versions.json", {}).get("_checked") or 0) > 86400 or not EMU_UPDATES["checked"]:
                with EMU_UPDATE_LOCK:
                    check_emulator_updates()
            if EMU_UPDATES["github"] and not update_busy() and not any(j["state"] in ("waiting", "installing") for j in QUEUE["jobs"]):
                queue_emulator_updates([n for n, i in EMU_UPDATES["github"].items() if not emulator_running(i["folder"])])
        except Exception:
            log_error()
        time.sleep(1800)


def job_for(system):
    return next((j for j in reversed(QUEUE["jobs"]) if system in j["systems"]), None)


def job_info(job):
    """What the page shows of a job: its state, and while installing its stage and progress (None: not known)."""
    live = {k: job.get(k) for k in ("stage", "progress", "done", "total")} if job["state"] == "installing" else {}
    return {"id": job["id"], "state": job["state"], "error": job["error"], **live}


def queue_view():
    return {"jobs": [{"emulator": j["emulator"], "systems": j["systems"], **job_info(j)} for j in QUEUE["jobs"]],
            "busy": any(j["state"] in ("waiting", "installing") for j in QUEUE["jobs"]), "batch": QUEUE["batch"]}


# --- extras: optional tools, installed through the same queue (Settings › General and the setup guide)
PRESENTMON_REPO = "GameTechDev/PresentMon"
PERF_LOG_USERS = "S-1-5-32-559"  # Performance Log Users, by SID: its name depends on Windows' language
TOKEN_GROUPS = [None]  # this process's groups don't change until the user signs in again


def install_presentmon():
    """Intel's PresentMon console program (one exe) from its own GitHub releases into data/tools, for the performance overlay's FPS."""
    rel = http_json(f"https://api.github.com/repos/{PRESENTMON_REPO}/releases/latest", timeout=30)
    asset = next((a for a in rel.get("assets", []) if re.fullmatch(r"PresentMon-[0-9.]+-x64\.exe", a.get("name", ""))), None)
    if not asset:
        raise ValueError("PresentMon has no Windows download right now. Try again later.")
    url, digest = asset["browser_download_url"], str(asset.get("digest") or "").lower()
    if not url.startswith(f"https://github.com/{PRESENTMON_REPO}/releases/download/"):
        raise ValueError("PresentMon's download isn't on its own project")
    if not digest.startswith("sha256:"):  # a lone exe: never kept without GitHub's checksum
        raise ValueError("PresentMon's download has no checksum to check it against. Try again later.")
    folder = os.path.join(DATA, "tools")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, asset["name"])
    part = target + ".part"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as response, open(part, "wb") as output:
        copy_progress(response, output, asset.get("size") or 0)
    job_progress("Setting up")
    with open(part, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or file_sha256(part) != digest[7:] or (asset.get("size") and os.path.getsize(part) != asset["size"]):
        os.remove(part)
        raise ValueError("The PresentMon download was damaged. Try again.")
    os.replace(part, target)
    for old in glob.glob(os.path.join(folder, "PresentMon*.exe")):  # older versions: the overlay uses the newest anyway
        if os.path.normcase(old) != os.path.normcase(target):
            try:
                os.remove(old)
            except OSError:
                pass
    return target


def remove_presentmon():
    import hud
    hud.MODE[0] = "off"  # its row goes with it, so nothing could turn the overlay off again
    store("hud.json", {"mode": "off"})
    hud.stop()
    time.sleep(0.5)
    for exe in glob.glob(os.path.join(DATA, "tools", "PresentMon*.exe")):
        os.remove(exe)


def token_groups():
    """This process's group SIDs, from whoami (read only)."""
    if TOKEN_GROUPS[0] is None:
        try:
            out = subprocess.run(["whoami", "/groups", "/fo", "csv", "/nh"], capture_output=True, text=True, errors="replace", timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            TOKEN_GROUPS[0] = set(re.findall(r"S-1-[0-9-]+", out))
        except (OSError, subprocess.TimeoutExpired):
            return set()
    return TOKEN_GROUPS[0]


def perf_group_name():
    """Performance Log Users' name on this PC, looked up from its SID."""
    import ctypes
    import ctypes.wintypes as W
    adv, kernel = ctypes.WinDLL("advapi32"), ctypes.WinDLL("kernel32")
    adv.ConvertStringSidToSidW.argtypes = [W.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    adv.LookupAccountSidW.argtypes = [W.LPCWSTR, ctypes.c_void_p, W.LPWSTR, ctypes.POINTER(W.DWORD), W.LPWSTR, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD)]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    sid = ctypes.c_void_p()
    if not adv.ConvertStringSidToSidW(PERF_LOG_USERS, ctypes.byref(sid)):
        return "Performance Log Users"
    try:
        name, domain, n, d, use = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256), W.DWORD(256), W.DWORD(256), W.DWORD()
        ok = adv.LookupAccountSidW(None, sid, name, ctypes.byref(n), domain, ctypes.byref(d), ctypes.byref(use))
        return name.value if ok and name.value else "Performance Log Users"
    finally:
        kernel.LocalFree(sid)


def account_name():
    return f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")


def account_in_group(group):
    """Whether this account is in a local group now, signed in again or not (read only: NetUserGetLocalGroups)."""
    import ctypes
    import ctypes.wintypes as W
    net = ctypes.WinDLL("netapi32")
    net.NetUserGetLocalGroups.argtypes = [W.LPCWSTR, W.LPCWSTR, W.DWORD, W.DWORD, ctypes.POINTER(ctypes.c_void_p), W.DWORD, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD)]
    net.NetApiBufferFree.argtypes = [ctypes.c_void_p]
    buf, read, total = ctypes.c_void_p(), W.DWORD(), W.DWORD()
    if net.NetUserGetLocalGroups(None, account_name(), 0, 1, ctypes.byref(buf), 0xFFFFFFFF, ctypes.byref(read), ctypes.byref(total)):  # 1: LG_INCLUDE_INDIRECT
        return False
    try:
        names = ctypes.cast(buf, ctypes.POINTER(ctypes.c_wchar_p))
        return any((names[i] or "").lower() == group.lower() for i in range(read.value))
    finally:
        net.NetApiBufferFree(buf)


def presentmon_rights():
    """PresentMon reads frame data as an administrator or a member of Performance Log Users: 'ready', 'signout' (added, but
    this sign-in doesn't have it yet) or 'needed'."""
    groups = token_groups()
    if PERF_LOG_USERS in groups or "S-1-16-12288" in groups or "S-1-16-16384" in groups:  # in the group, or running elevated (high or system level)
        return "ready"
    try:
        return "signout" if account_in_group(perf_group_name()) else "needed"
    except (OSError, AttributeError):
        return "needed"


def run_elevated(program, params, wait=120000):
    """Run a program through Windows' administrator prompt (UAC), hidden, and wait for it: its exit code."""
    import ctypes
    import ctypes.wintypes as W

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("fMask", W.ULONG), ("hwnd", W.HWND), ("lpVerb", W.LPCWSTR), ("lpFile", W.LPCWSTR), ("lpParameters", W.LPCWSTR),
                    ("lpDirectory", W.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", W.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", W.LPCWSTR),
                    ("hkeyClass", W.HKEY), ("dwHotKey", W.DWORD), ("hIcon", W.HANDLE), ("hProcess", W.HANDLE)]
    shell, kernel = ctypes.WinDLL("shell32", use_last_error=True), ctypes.WinDLL("kernel32")
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(Info)]
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    info = Info(cbSize=ctypes.sizeof(Info), fMask=0x40 | 0x100, lpVerb="runas", lpFile=program, lpParameters=params, nShow=0)  # NOCLOSEPROCESS | NOASYNC, hidden
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        if ctypes.get_last_error() == 1223:
            raise ValueError("Windows' permission prompt was cancelled")
        raise ValueError("Windows' permission prompt couldn't open")
    code = W.DWORD(1)
    try:
        kernel.WaitForSingleObject(info.hProcess, wait)
        kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    finally:
        kernel.CloseHandle(info.hProcess)
    return code.value


# ---------- signing in to Windows automatically (an option: the setup guide's start-up step and Settings > General) ----------
# The app never sees a password. An account without one is set up here; for one with a password, Windows' own User
# Accounts window (netplwiz) asks for it and keeps it encrypted. Either way waking from sleep stops asking too.
WINLOGON = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"


def my_sign_in_names():
    """The names Windows may use for this account in its auto sign-in setting: the account name, its Microsoft account
    email (netplwiz writes that for a Microsoft account) and its work or school sign-in (UPN). Lower case."""
    import ctypes
    import winreg
    names = {os.environ.get("USERNAME", "").lower()}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\IdentityCRL\UserExtendedProperties") as k:
            i = 0
            while True:
                try:
                    names.add(winreg.EnumKey(k, i).lower())
                except OSError:
                    break
                i += 1
    except OSError:
        pass
    try:
        sec = ctypes.WinDLL("secur32")
        size = ctypes.c_ulong(512)
        buf = ctypes.create_unicode_buffer(512)
        if sec.GetUserNameExW(8, buf, ctypes.byref(size)):  # NameUserPrincipal
            names.add(buf.value.lower())
    except (OSError, AttributeError):
        pass
    names.discard("")
    return names


def autologon_view():
    """Read only: whether Windows signs this account in by itself, or another one."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINLOGON) as k:
            def get(name):
                try:
                    return str(winreg.QueryValueEx(k, name)[0])
                except OSError:
                    return ""
            on, user = get("AutoAdminLogon") == "1", get("DefaultUserName")
    except OSError:
        return {"available": False}
    mine = bool(user) and user.split("\\")[-1].lower() in my_sign_in_names()
    return {"available": True, "on": on and mine, "other": user if on and user and not mine else "", "user": os.environ.get("USERNAME", "")}


def blank_password():
    """Whether this account has no password: True, False, or None when it can't tell. Asked once, only when the option is
    turned on: Windows answers a blank-password sign-in with 'account restriction' (1327) or lets it in when there's none,
    and 'wrong password' (1326) when there is one."""
    import ctypes
    import ctypes.wintypes as W
    adv, k32 = ctypes.WinDLL("advapi32", use_last_error=True), ctypes.WinDLL("kernel32")
    adv.LogonUserW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.DWORD, W.DWORD, ctypes.POINTER(W.HANDLE)]
    k32.CloseHandle.argtypes = [W.HANDLE]
    token = W.HANDLE()
    if adv.LogonUserW(os.environ.get("USERNAME", ""), ".", "", 2, 0, ctypes.byref(token)):  # LOGON32_LOGON_INTERACTIVE
        k32.CloseHandle(token)
        return True
    err = ctypes.get_last_error()
    return True if err == 1327 else False if err == 1326 else None


def ps_text(text):
    """A string for the administrator script, passed as data (base64) so no name can break out of it."""
    return "([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + base64.b64encode(str(text).encode("utf-16-le")).decode() + "')))"


AUTOLOGON_HEAD = r"""$ErrorActionPreference = 'Stop'
trap { exit 1 }
$w = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$d = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device'
$keep = 'HKLM:\SOFTWARE\Ultra Front End'
function Get-Value($key, $name) { $v = Get-ItemProperty $key -Name $name -ErrorAction SilentlyContinue; if ($v) { $v.$name } }
function Set-Wake($lock) {  # asking for the sign-in on wake, in every power plan (a laptop's modes switch plans)
  $plans = (powercfg /list | Select-String '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}' -AllMatches).Matches.Value | Select-Object -Unique
  foreach ($g in $plans) { powercfg /setacvalueindex $g SUB_NONE CONSOLELOCK $lock; powercfg /setdcvalueindex $g SUB_NONE CONSOLELOCK $lock }
  powercfg /setactive SCHEME_CURRENT
}
function Hello-Off {  # 'only allow Windows Hello sign-in' hides netplwiz's tick box: noted first, so it can be put back
  if (-not (Test-Path $keep)) { New-Item $keep -Force | Out-Null }
  if ($null -eq (Get-Value $keep 'HelloBefore')) { Set-ItemProperty $keep HelloBefore ([string](Get-Value $d 'DevicePasswordLessBuildVersion')) -Type String }
  if (-not (Test-Path $d)) { New-Item $d -Force | Out-Null }
  Set-ItemProperty $d DevicePasswordLessBuildVersion 0 -Type DWord
}
function Hello-Back {
  $b = Get-Value $keep 'HelloBefore'
  if ($null -eq $b) { return }
  if ($b -eq '') { Remove-ItemProperty $d DevicePasswordLessBuildVersion -ErrorAction SilentlyContinue }
  else { Set-ItemProperty $d DevicePasswordLessBuildVersion ([int]$b) -Type DWord }
  Remove-ItemProperty $keep HelloBefore
}
"""
AUTOLOGON_FORGET = r"""
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class UfeLsa {
  [StructLayout(LayoutKind.Sequential)] struct U { public ushort Length; public ushort MaximumLength; public IntPtr Buffer; }
  [StructLayout(LayoutKind.Sequential)] struct A { public int Length; public IntPtr RootDirectory; public IntPtr ObjectName; public uint Attributes; public IntPtr SecurityDescriptor; public IntPtr SecurityQualityOfService; }
  [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr system, ref A attributes, uint access, out IntPtr policy);
  [DllImport("advapi32.dll")] static extern uint LsaStorePrivateData(IntPtr policy, ref U key, IntPtr data);
  [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr policy);
  public static uint Forget(string name) {
    A a = new A(); a.Length = Marshal.SizeOf(typeof(A)); IntPtr policy;
    uint r = LsaOpenPolicy(IntPtr.Zero, ref a, 0x00F0FFF, out policy);
    if (r != 0) return r;
    U key = new U(); key.Buffer = Marshal.StringToHGlobalUni(name); key.Length = (ushort)(name.Length * 2); key.MaximumLength = (ushort)(key.Length + 2);
    try { return LsaStorePrivateData(policy, ref key, IntPtr.Zero); } finally { Marshal.FreeHGlobal(key.Buffer); LsaClose(policy); }
  }
}
'@
[void][UfeLsa]::Forget('DefaultPassword')
"""
AUTOLOGON_CANCELLED = 3  # the User Accounts window was closed without turning it on: everything was put back


def autologon_script(on, blank):
    """The administrator script: no file on disk, so nothing can swap it before Windows' prompt. The account is named as
    data: the person approving Windows' prompt can be a different administrator, so the script can't ask who it runs as."""
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "") or os.environ.get("COMPUTERNAME", "")
    head = AUTOLOGON_HEAD + f"$u = {ps_text(user)}\n$dom = {ps_text(domain)}\n"
    if not on:  # off: the saved sign-in goes too, wherever Windows kept it, whoever it was for
        return head + ("Set-ItemProperty $w AutoAdminLogon '0'\n"
                       "foreach ($n in 'DefaultPassword', 'AutoLogonCount') { Remove-ItemProperty $w $n -ErrorAction SilentlyContinue }\n"
                       + AUTOLOGON_FORGET + "Set-Wake 1\nHello-Back\nexit 0\n")
    if blank:
        return head + (AUTOLOGON_FORGET  # a password Windows keeps from another account's auto sign-in would be tried first
                       + "Set-ItemProperty $w DefaultUserName $u\n"
                       "Set-ItemProperty $w DefaultDomainName $dom\n"
                       "Set-ItemProperty $w DefaultPassword ''\n"
                       "Remove-ItemProperty $w AutoLogonCount -ErrorAction SilentlyContinue\n"  # it would turn itself off after that many
                       "Set-ItemProperty $w AutoAdminLogon '1'\n"
                       "Set-Wake 0\nexit 0\n")
    # A password: Windows' User Accounts window asks for it. Waited for: done, the rest follows; closed, all is put back.
    return head + ("Hello-Off\n"
                   "$was = @{ on = (Get-Value $w 'AutoAdminLogon'); user = (Get-Value $w 'DefaultUserName'); dom = (Get-Value $w 'DefaultDomainName') }\n"
                   "if ($was.on -ne '1') { Set-ItemProperty $w DefaultUserName $u; Set-ItemProperty $w DefaultDomainName $dom }  # its name box starts on this account\n"
                   "$p = Start-Process \"$env:SystemRoot\\System32\\netplwiz.exe\" -PassThru\n"
                   "$p.WaitForExit()\n"
                   "$now = @{ on = (Get-Value $w 'AutoAdminLogon'); user = (Get-Value $w 'DefaultUserName') }\n"
                   "if ($now.on -eq '1' -and ($was.on -ne '1' -or $now.user -ne $was.user)) {\n"
                   "  Remove-ItemProperty $w AutoLogonCount -ErrorAction SilentlyContinue\n"
                   "  Set-Wake 0\n  exit 0\n}\n"
                   "if ($was.on -ne '1') {\n"
                   "  foreach ($n in 'user', 'dom') { $name = @{ user = 'DefaultUserName'; dom = 'DefaultDomainName' }[$n]\n"
                   "    if ($null -eq $was[$n]) { Remove-ItemProperty $w $name -ErrorAction SilentlyContinue } else { Set-ItemProperty $w $name $was[$n] } }\n"
                   "}\n"
                   f"Hello-Back\nexit {AUTOLOGON_CANCELLED}\n")


def set_autologon(on):
    """Turn signing in automatically on or off, after Windows' administrator prompt: 'on', 'off', or 'cancelled' when
    Windows' User Accounts window was closed without turning it on."""
    if not WIN:
        raise ValueError("Signing in automatically is a Windows setting")
    blank = blank_password() if on else None
    powershell = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    encoded = base64.b64encode(autologon_script(on, blank).encode("utf-16-le")).decode()
    window = on and not blank
    if window:  # Windows opens it behind the fullscreen frontend
        bring_forward("netplwiz.exe", "User Accounts", timeout=90)
    code = run_elevated(powershell, f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}", wait=900000 if window else 120000)
    if window and code == AUTOLOGON_CANCELLED:
        return "cancelled"
    if code:
        raise ValueError("Windows couldn't change the sign-in setting")
    return "on" if on else "off"


def bring_forward(exe, title="", timeout=10):
    """Bring a program's window in front of the fullscreen frontend once it shows (Windows opens it behind). By its .exe,
    or by its title when the program runs as another account (an administrator who approved the prompt) and can't be read."""
    import ctypes
    user32 = ctypes.WinDLL("user32")
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    FOCUS[0] += 1
    token = FOCUS[0]

    def run():
        deadline = time.time() + timeout
        while time.time() < deadline and FOCUS[0] == token:
            time.sleep(0.3)
            found = list(windows_of(exe)) or ([user32.FindWindowW("#32770", title)] if title else [])
            if found and found[0]:
                take_foreground(found[0])
                return
    threading.Thread(target=run, daemon=True).start()


def presentmon_permission():
    """Add this account to Performance Log Users: net localgroup, as administrator, after Windows' own prompt."""
    if presentmon_rights() != "needed":
        return
    net = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "net.exe")
    code = run_elevated(net, f'localgroup "{perf_group_name()}" "{account_name()}" /add')
    if code and presentmon_rights() == "needed":  # (2 is also 'already a member')
        raise ValueError(f"Windows couldn't add you to Performance Log Users (code {code})")


# ---------- recording: the app's own copy of FFmpeg, fetched into data/tools ----------
# FFmpeg's official Windows builds (BtbN/FFmpeg-Builds, linked from ffmpeg.org): the LGPL "shared" edition of the newest
# stable version, about 80 MB, checked against GitHub's checksum. Only ffmpeg.exe and its DLLs are kept.
RECORDER_REPO = "BtbN/FFmpeg-Builds"
RECORDER_DIR = os.path.join(DATA, "tools", "ffmpeg")


def own_ffmpeg():
    exe = os.path.join(RECORDER_DIR, "ffmpeg.exe")
    return exe if os.path.isfile(exe) else ""


def install_recorder():
    import zipfile
    rel = http_json(f"https://api.github.com/repos/{RECORDER_REPO}/releases/latest", timeout=30)
    pick = None
    for a in rel.get("assets", []):
        m = re.fullmatch(r"ffmpeg-n(\d+(?:\.\d+)*)-latest-win64-lgpl-shared-[\d.]+\.zip", a.get("name", ""))
        if m and (not pick or version_key(m.group(1)) > version_key(pick[0])):
            pick = (m.group(1), a)
    if not pick:
        raise ValueError("FFmpeg has no Windows download right now. Try again later.")
    asset = pick[1]
    url, digest = asset["browser_download_url"], str(asset.get("digest") or "").lower()
    if not url.startswith(f"https://github.com/{RECORDER_REPO}/releases/download/") or not digest.startswith("sha256:"):
        raise ValueError("FFmpeg's download couldn't be checked. Try again later.")
    os.makedirs(os.path.dirname(RECORDER_DIR), exist_ok=True)
    part = RECORDER_DIR + ".zip.part"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as response, open(part, "wb") as output:
        copy_progress(response, output, asset.get("size") or 0)
    job_progress("Setting up")
    try:
        if file_sha256(part) != digest[7:]:
            raise ValueError("The FFmpeg download was damaged. Try again.")
        fresh = RECORDER_DIR + ".new"
        shutil.rmtree(fresh, ignore_errors=True)
        os.makedirs(fresh)
        with zipfile.ZipFile(part) as z:
            for name in z.namelist():  # only the program and the libraries it needs, never paths from the archive
                base = name.rsplit("/", 1)[-1]
                if "/bin/" in name and re.fullmatch(r"ffmpeg\.exe|[\w.-]+\.dll", base, re.I):
                    with z.open(name) as src, open(os.path.join(fresh, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        exe = os.path.join(fresh, "ffmpeg.exe")
        if not os.path.isfile(exe) or subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, timeout=30).returncode:
            raise ValueError("FFmpeg didn't start. Try again.")
        shutil.rmtree(RECORDER_DIR, ignore_errors=True)
        os.replace(fresh, RECORDER_DIR)
        ENCODER[0] = None  # look for the best encoder again with this copy
    finally:
        try:
            os.remove(part)
        except OSError:
            pass
    return own_ffmpeg()


def remove_recorder():
    if RECORD["proc"]:
        raise ValueError("Stop the recording first")
    shutil.rmtree(RECORDER_DIR)
    ENCODER[0] = None


EXTRAS = {"presentmon": ("Performance overlay", install_presentmon, remove_presentmon),  # name: (what it's called, install, remove)
          "recorder": ("Video recording", install_recorder, remove_recorder)}


def queue_extra(name):
    with QUEUE_COND:
        if not any(j.get("extra") == name and j["state"] in ("waiting", "installing") for j in QUEUE["jobs"]):
            new_batch()
            QUEUE["next"] += 1
            QUEUE["jobs"].append({"id": QUEUE["next"], "emulator": EXTRAS[name][0], "package": (name, "extra"), "systems": [], "extra": name, "state": "waiting", "error": ""})
    queue_install([])  # starts the worker if need be and wakes it


def extras_view():
    import hud
    exe = hud.presentmon(DATA)
    job = next((j for j in reversed(QUEUE["jobs"]) if j.get("extra") == "presentmon"), None)
    pm = {"installed": bool(exe), "version": (re.findall(r"\d+(?:\.\d+)+", os.path.basename(exe)) or [""])[0] if exe else "",
          "job": job_info(job) if job else None, "available": WIN}
    if exe and WIN:
        pm["rights"] = presentmon_rights()
        pm["mode"] = hud_mode()  # Off, Compact or Full: chosen in Settings
    rjob = next((j for j in reversed(QUEUE["jobs"]) if j.get("extra") == "recorder"), None)
    rec = {"installed": bool(own_ffmpeg()), "elsewhere": bool(not own_ffmpeg() and ffmpeg_path()), "job": job_info(rjob) if rjob else None, "available": WIN}
    return {"presentmon": pm, "recorder": rec}


def system_view(system, cfg, chosen):
    emu = cfg.get("emulators", {}).get(system, {}).get("path", "")
    package, job = emu_table().get(system), job_for(system)
    view = {"name": system, "group": SYSTEM_GROUP.get(system, "Other"), "chosen": system in chosen, "count": STATE["counts"].get(f"ROMs/{system}", 0),
            "emulator": os.path.basename(emu), "emulatorDir": os.path.dirname(emu) if emu else "",
            "emulatorVersion": emulator_version(emu, system) if emu and WIN else "", "install": package[0] if (WIN or MAC) and package and package[1] != "manual" else None,
            "recommended": emulator_for(system), "site": system_site(system), "steps": BIOS_STEPS.get(system),
            "job": job_info(job) if job else None}
    if system in chosen:  # (only these are looked through: hashing every console's folder would slow Settings down)
        view["bios"] = {**bios_state(system, bios_dir(cfg, system)), "note": APPLIED.get(system)}
    return view


# ---------------------------------------------------------------- HTTP
LAST_PING = [time.time()]


def page_version():
    """Changes when a page file changes, so an open frontend can refresh itself."""
    try:
        return max(int(os.path.getmtime(os.path.join(APP, n))) for n in ("app.js", "styles.css", "index.html"))
    except OSError:
        return 0


def read_clipboard():
    """The clipboard's text, or "" when it holds none."""
    if not WIN:
        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
    import ctypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    for _ in range(10):  # another program may have it open for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise ValueError("The clipboard is busy. Try again.")
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)[:4000] if pointer else ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def log_error():
    """An unexpected error in a request, kept in data/errors.log (the exe has no console to print to): the newest 200 KB."""
    import traceback
    try:
        path = os.path.join(DATA, "errors.log")
        if os.path.exists(path) and os.path.getsize(path) > 200_000:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except OSError:
        pass


class Handler(SimpleHTTPRequestHandler):
    timeout = 30  # a client that stops mid-request gives its thread back (long polls wait in our code, not on the socket)

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=APP, **kw)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", getattr(self, "cache", "no-store"))
        super().end_headers()

    def revalidate(self, f):
        """Images and the app's own files can be kept by the page: it asks again each time, and an unchanged file
        costs a 304 instead of being read and sent again."""
        st = os.stat(f)
        self.cache, self.etag = "no-cache", f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        if self.etag not in self.headers.get("If-None-Match", ""):
            return False
        self.send_response(304)
        self.send_header("ETag", self.etag)
        self.end_headers()
        return True

    def local_host(self):
        # Blocks DNS-rebinding: only answer requests addressed to this machine.
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_path(self, f):
        """A file from disk, with byte ranges so recordings can be scrubbed."""
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
                 ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska"}.get(os.path.splitext(f)[1].lower(), "application/octet-stream")
        if ctype.startswith("image/") and self.revalidate(f):  # not videos: they're big, and seeking asks for ranges
            return
        size = os.path.getsize(f)
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        start, end = 0, size - 1
        if m and (m.group(1) or m.group(2)):
            start, end = (int(m.group(1)), min(int(m.group(2) or size - 1), size - 1)) if m.group(1) else (max(0, size - int(m.group(2))), size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                return self.end_headers()
        self.send_response(206 if m and (m.group(1) or m.group(2)) else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        if self.etag:
            self.send_header("ETag", self.etag)
        self.send_header("Content-Length", str(end - start + 1))
        if m and (m.group(1) or m.group(2)):
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionError, OSError):
                pass  # the player moved on (seeking closes the old request)

    def do_HEAD(self):
        if not self.local_host():
            return self.send_error(403)
        return super().do_HEAD()

    def do_GET(self):
        try:
            return self.handle_get()
        except (ConnectionError, TimeoutError):
            pass
        except Exception as e:  # a bug in one route: still an answer the page can show, not a dropped connection
            log_error()
            try:
                return self.reply({"error": f"Something went wrong ({type(e).__name__}: {e})"}, 500)
            except OSError:
                pass

    def handle_get(self):
        self.cache, self.etag = "no-store", None
        if "\x00" in urllib.parse.unquote(self.path):
            return self.send_error(404)
        if not self.local_host():
            return self.send_error(403)
        path = urllib.parse.urlparse(self.path).path
        LAST_PING[0] = time.time()
        if path == "/api/library":
            if not STATE["scanned"]:
                scan()
            return self.reply({"games": public_games(), "errors": STATE["errors"], "scanned": STATE["scanned"]})
        if path == "/api/settings":
            return self.reply(settings_view())
        if path == "/api/systems/queue":
            return self.reply(queue_view())
        if path == "/api/pad":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                after = int((q.get("after") or ["0"])[0])
            except ValueError:
                after = 0
            return self.reply(pad_wait(after, bool(q.get("overlay"))))
        if path == "/api/ping":
            return self.reply({"ok": True, "scanned": STATE["scanned"], "page": page_version(), "build": BUILD, "pid": os.getpid(), "root": ROOT,
                               "version": VERSION})
        if path == "/api/profile":
            return self.reply(profile())
        if path == "/api/avatar":
            pic = glob.glob(os.path.join(DATA, "avatar.*"))
            if not pic:
                return self.send_error(404)
            if self.revalidate(pic[0]):
                return
            with open(pic[0], "rb") as fh:
                data = fh.read()
            ext = os.path.splitext(pic[0])[1].lower().lstrip(".")
            self.send_response(200)
            self.send_header("Content-Type", {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, f"image/{ext}"))
            self.send_header("ETag", self.etag)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if path == "/api/overlay":  # ?tip: the menu page itself, which shows a game's once-only tip
            return self.reply(overlay_state(tip="tip" in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)))
        if path == "/api/overlay/wake":  # the overlay program, waiting to be shown or hidden
            want = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("want") or ["open"])[0]
            return self.reply(overlay_wake("hide" if want == "hide" else "open"))
        if path == "/api/nowplaying":
            return self.reply(now_playing())
        if path == "/api/nowplaying/art":
            if not NP_ART["data"] or not NP_ART["type"].startswith("image/"):
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", NP_ART["type"])
            self.send_header("Cache-Control", "max-age=86400")  # its address changes with the picture
            self.send_header("Content-Length", str(len(NP_ART["data"])))
            self.end_headers()
            return self.wfile.write(NP_ART["data"])
        if path == "/api/spawn/next":
            return self.reply(spawn_next())
        if path == "/api/qa":  # Quick Access: sound outputs, controllers, Wi-Fi, notifications, brightness
            return self.reply(qa_view())
        if path == "/api/padraw":
            return self.reply({"hex": PAD_RAW[0].hex(), "age": time.time() - PAD_RAW[1], "battery": PAD_BATTERY[0] if time.time() - PAD_RAW[1] < 60 else None})
        if path == "/api/xinput":  # the controller tester, when the browser can't see an Xbox pad (Steam Input can hide it)
            keys = ("buttons", "lt", "rt", "lx", "ly", "rx", "ry")
            return self.reply({"pads": [{"slot": i, **dict(zip(keys, v[1:]))} for i, v in sorted(XSTATE.items()) if time.time() - v[0] < 2]})
        if path == "/api/launching":
            gid_ = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0]
            exited = gid_ in EXITED_EARLY and gid_ not in LAUNCHING
            EXITED_EARLY.discard(gid_) if exited else None
            return self.reply({"waiting": gid_ in LAUNCHING, "exited": exited})
        if path == "/api/volume":
            try:
                return self.reply(audio_volume())
            except OSError:
                return self.reply({"volume": None, "muted": False})
        if path == "/api/game/players":
            g = STATE["byId"].get((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0]) or {}
            try:
                return self.reply({"players": steam_players(g["appid"]) if g.get("appid") else None})
            except (OSError, ValueError):
                return self.reply({"players": None})
        if path == "/api/hud":
            import hud
            return self.reply({"mode": hud_mode(), "fps": bool(hud.presentmon(DATA))})  # the overlay is an extra: shown once PresentMon is in data/tools
        if path == "/api/update":
            return self.reply(update_view())
        if path == "/api/running":
            return self.reply({"games": list(RUN_NOW), "folders": len(RUN_DIRS[1])})
        if path == "/api/downloads":
            return self.reply({"items": steam_downloads()})
        if path == "/api/friends":
            try:
                return self.reply({"items": steam_friends()})
            except ValueError as e:
                return self.reply({"items": [], "error": str(e)})
            except OSError:
                return self.reply({"items": [], "error": "Couldn't reach Steam. Check your connection."})
        if path == "/api/unpack":
            gid_ = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0]
            return self.reply({"unpacking": gid_ in UNPACKING, "error": UNPACK_ERRORS.get(gid_, "")})
        if path == "/api/hero":
            g = STATE["byId"].get((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0])
            if not g:
                return self.reply({"hero": ""})
            still, anim = animated_hero(g)
            return self.reply({"hero": still, "heroAnim": anim} if still else {"hero": hero_local(g, hero_for(g))})
        if path == "/api/heroimg":
            g = STATE["byId"].get((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0])
            f = g and os.path.join(HERO_IMG, safe_name(g["id"]) + ".jpg")
            return self.send_path(f) if f and os.path.isfile(f) else self.send_error(404)
        if path == "/api/news":
            return self.reply({"news": all_news()})
        if path == "/api/broker/next":  # the elevated install helper asking for work (it waits here up to 25 s)
            token = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("token") or [""])[0]
            if not BROKER["token"] or not secrets_equal(token, BROKER["token"]):
                return self.reply({"error": "Not the install helper"}, 403)
            with BROKER_COND:
                BROKER["seen"] = time.time()
                BROKER_COND.notify_all()
                BROKER_COND.wait_for(lambda: BROKER["jobs"], timeout=25)
                BROKER["seen"] = time.time()
                job = BROKER["jobs"].pop(0) if BROKER["jobs"] else {}
            return self.reply(job)
        if path == "/api/whatsnew":
            items, error = whats_new()
            return self.reply({"items": items, "error": error, "version": VERSION, "unseen": whats_new_unseen()})
        if path == "/api/whatsnew/unseen":  # for the News button's dot: no network
            return self.reply({"unseen": whats_new_unseen(), "version": VERSION})
        if path == "/api/game/achievements":
            g = STATE["byId"].get((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0])
            return self.reply({"achievements": quiet(POOL.submit(achievements, g), None) if g else None})
        if path == "/api/game/news":
            g = STATE["byId"].get((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0])
            return self.reply({"news": game_news(g) if g else []})
        if path == "/api/game":
            g = STATE["byId"].get((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0])
            if not g:
                return self.reply({"error": "Game not found"}, 404)
            return self.reply(game_details(g))
        if path == "/api/album":
            return self.reply({"captures": album(), "still": True})
        if path in ("/api/album/file", "/api/album/thumb"):
            cid = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id") or [""])[0]
            f = album_file(cid) if path.endswith("file") else album_thumb(cid)
            return self.send_path(f) if f else self.send_error(404)
        if path.startswith("/api/art/"):
            key = path.rsplit("/", 1)[-1]
            f = ART.get(key) or DETAIL_ART.get(key)
            if not f or not os.path.isfile(f):
                return self.send_error(404)
            if key.endswith("--anim"):
                f = light_anim(f)  # only ever the light copy (a cover is offered as animated once it exists)
                if not f:
                    return self.send_error(404)
            if self.revalidate(f):
                return
            with open(f, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", {"png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(f.rsplit(".", 1)[-1].lower(), "image/jpeg"))
            self.send_header("ETag", self.etag)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self.cache = "no-cache"  # the app's files: revalidated with Last-Modified, so an edit still shows on the next load
        return super().do_GET()

    def do_POST(self):
        self.cache = "no-store"
        # The custom header can't be sent cross-site without a CORS preflight, which we never approve.
        if not self.local_host() or self.headers.get("X-Frontend") != "1":
            return self.send_error(403)
        try:
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 <= size <= 1_000_000:
                self.close_connection = True  # the body isn't read, so this connection can't take another request
                raise ValueError("Bad Content-Length" if size < 0 else "That request is too big")
            try:
                body = json.loads(self.rfile.read(size) or b"{}")
            except RecursionError:
                raise ValueError("Send a JSON object")
            if not isinstance(body, dict):
                raise ValueError("Send a JSON object")
            TEXT_FIELDS = ("id", "system", "provider", "key", "user", "code", "query", "url", "kind", "name", "profile", "action", "timezone", "avatar")
            if urllib.parse.urlparse(self.path).path != "/api/spawn/done" and any(  # (the window's spawn jobs have numbered ids)
                    k in body and body[k] is not None and not isinstance(body[k], str) for k in TEXT_FIELDS) or ("pid" in body and not isinstance(body["pid"], int)):
                raise ValueError("A field has the wrong type")
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/spawn/done":
                spawn_done(body.get("id"), int(body.get("pid") or 0))
                return self.reply({"ok": True})
            if path in ("/api/broker/out", "/api/broker/done"):  # the elevated install helper's output and result
                if not BROKER["token"] or not secrets_equal(str(body.get("token") or ""), BROKER["token"]):
                    return self.reply({"error": "Not the install helper"}, 403)
                with BROKER_COND:
                    BROKER["seen"] = time.time()
                    job = body.get("job")  # (numbers: the request check wants "id" and "code" to be text)
                    if path.endswith("out") and job in BROKER["out"]:
                        BROKER["out"][job].append(str(body.get("text") or ""))
                    elif path.endswith("done") and isinstance(job, int):
                        BROKER["done"][job] = int(body.get("exit") or 0)
                    BROKER_COND.notify_all()
                return self.reply({"ok": True})
            if path == "/api/whatsnew":  # this version's notes were read: the News button's dot goes
                store("whatsnew.json", {**load("whatsnew.json", {}), "seen": VERSION})
                return self.reply({"unseen": False})
            if path == "/api/update":  # Settings > About: check now, install now, or the page has shown "Updated"
                if body.get("action") == "seen":
                    store("update.json", {**load("update.json", {}), "updated": None})
                elif body.get("action") == "channel":  # Settings › About: main releases or nightly builds, then a check on that channel
                    cfg = config()
                    cfg["updateChannel"] = "nightly" if body.get("channel") == "nightly" else "main"
                    store("config.json", cfg)
                    UPDATE.update(latest=None, state="", error="", retry=0.0)
                    if not updates_off():
                        threading.Thread(target=update_step, args=["check"], daemon=True).start()
                        time.sleep(0.3)
                elif body.get("action") in ("check", "install"):
                    threading.Thread(target=update_step, args=[body["action"]], daemon=True).start()
                    time.sleep(0.3)
                return self.reply(update_view())
            if path == "/api/mac/controller-settings" and MAC:  # Settings > Controllers: the home button's setting is Apple's
                subprocess.Popen(["open", "x-apple.systempreferences:com.apple.Game-Controller-Settings.extension"])
                return self.reply({"ok": True})
            if path == "/api/uninstall" and MAC:  # Settings > About > Uninstall: to the Trash, then the app quits
                failed, data = uninstall_mac(bool(body.get("wipe")))
                if not failed:
                    threading.Timer(2.5, lambda: (data(), os._exit(0))).start()  # long enough for the page to say so
                return self.reply({"ok": not failed, "failed": failed})
            if path == "/api/quit":  # a newer build is taking over
                threading.Timer(0.2, QUIT[0]).start()
                return self.reply({"ok": True})
            if path == "/api/overlay":
                if body.get("action") == "toggle":  # for testing without a controller
                    toggle_overlay()
                else:
                    threading.Thread(target=overlay_action, args=[body.get("action")], daemon=True).start()
                return self.reply({"ok": True})
            if path == "/api/launch":
                g = STATE["byId"].get(body.get("id"))
                if not g:
                    raise ValueError("Game not found")
                result = launch(g)
                return self.reply({"ok": True, "installing": not g["installed"], "unpacking": result == "unpacking"})
            if path == "/api/game/app-location":
                return self.reply(change_app_location(body.get("id"), bool(body.get("reset"))))
            if path == "/api/game/hide":
                g = STATE["byId"].get(body.get("id"))
                if not g:
                    raise ValueError("Game not found")
                overrides = load("overrides.json", {})
                o = overrides.setdefault(g["id"], {})
                if body.get("hidden"):
                    o["hidden"] = True
                else:
                    o.pop("hidden", None)
                    if not o:
                        overrides.pop(g["id"])
                store("overrides.json", overrides)
                g["hidden"] = bool(body.get("hidden"))
                return self.reply({"ok": True})
            if path == "/api/game/rename":  # a name of the user's own; an empty one goes back to the game's own name
                g = STATE["byId"].get(body.get("id"))
                if not g:
                    raise ValueError("Game not found")
                title = " ".join(str(body.get("title") or "").split())[:120]
                overrides = load("overrides.json", {})
                o = overrides.setdefault(g["id"], {})
                if title:
                    o["title"] = title
                else:
                    o.pop("title", None)
                    if not o:
                        overrides.pop(g["id"])
                store("overrides.json", overrides)
                scan()
                return self.reply({"ok": True, "title": title})
            if path == "/api/game/favorite":
                g = STATE["byId"].get(body.get("id"))
                if not g:
                    raise ValueError("Game not found")
                overrides = load("overrides.json", {})
                o = overrides.setdefault(g["id"], {})
                if body.get("favorite"):
                    o["favorite"] = g["favorite"] = True
                else:
                    o.pop("favorite", None)
                    g.pop("favorite", None)
                    if not o:
                        overrides.pop(g["id"])
                store("overrides.json", overrides)
                return self.reply({"ok": True})
            if path == "/api/game/collection":
                g, name = STATE["byId"].get(body.get("id")), str(body.get("name") or "").strip()[:40]
                if not g:
                    raise ValueError("Game not found")
                if not name:
                    raise ValueError("Type a name for the collection")
                overrides = load("overrides.json", {})
                o = overrides.setdefault(g["id"], {})
                names = [n for n in o.get("collections", []) if n != name] + ([name] if body.get("member") else [])
                if names:
                    o["collections"] = g["collections"] = names
                else:
                    o.pop("collections", None)
                    g.pop("collections", None)
                    if not o:
                        overrides.pop(g["id"])
                store("overrides.json", overrides)
                return self.reply({"ok": True})
            if path == "/api/friends/message":  # Steam's own chat window: its Web API can't send messages
                sid = str(body.get("id") or "")
                if not re.fullmatch(r"7656[0-9]{13}", sid):
                    raise ValueError("That friend couldn't be found")
                open_in_steam("steam://friends/message/" + sid, str(body.get("name") or "")[:100] or "Steam")
                return self.reply({"ok": True})
            if path == "/api/introsound" and MAC:
                name = "outro.wav" if body.get("outro") else "intro.wav"  # the closing sound, or the opening one
                own = os.path.join(DATA, name)
                plat_mac.play_sound(own if os.path.isfile(own) else os.path.join(APP, "assets", name)) if body.get("play") else plat_mac.stop_sound()
                return self.reply({"ok": True})
            if path == "/api/introsound":  # played here because a page can't start sound by itself
                import winsound
                if body.get("play"):
                    name = "outro.wav" if body.get("outro") else "intro.wav"  # the closing sound, or the opening one
                    own = os.path.join(DATA, name)  # put your own sound there to replace the one that ships
                    winsound.PlaySound(own if os.path.isfile(own) else os.path.join(APP, "assets", name), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                else:
                    winsound.PlaySound(None, 0)
                return self.reply({"ok": True})
            if path == "/api/hud":
                import hud
                if not hud.presentmon(DATA):
                    raise ValueError("Install the performance overlay in Settings › General first")
                return self.reply({"mode": hud_mode(cycle=True)})
            if path == "/api/launchers/install":  # a missing game launcher, through the install queue
                queue_launcher(body.get("id") or "")
                return self.reply(settings_view())
            if path == "/api/autologon":  # after Windows' administrator prompt
                state = set_autologon(bool(body.get("on")))
                return self.reply({**settings_view(), "autologonState": state})
            if path in ("/api/extras/install", "/api/extras/remove", "/api/extras/permission"):
                if body.get("name") not in EXTRAS or not WIN:
                    raise ValueError("No such extra")
                if path.endswith("install"):
                    queue_extra(body["name"])
                elif path.endswith("remove"):
                    EXTRAS[body["name"]][2]()
                else:  # waits for Windows' prompt to be answered
                    presentmon_permission()
                return self.reply(settings_view())
            if path == "/api/album/delete":
                delete_capture(body.get("id"))
                return self.reply({"ok": True})
            if path in ("/api/running/resume", "/api/running/close"):
                if body.get("id") not in STATE["byId"]:
                    raise ValueError("Game not found")
                (running_resume if path.endswith("resume") else running_close)(body["id"])
                return self.reply({"ok": True})
            if path == "/api/system":
                system_power(body.get("action"))
                return self.reply({"ok": True})
            if path == "/api/volume":
                return self.reply(audio_volume(delta=body.get("delta"), mute=body.get("mute")))
            if path == "/api/qa":
                act = body.get("action")
                if act == "output":
                    set_sound_output(str(body.get("id") or ""))
                elif act == "padoff":
                    xinput_off(int(body.get("slot", -1)))
                elif act == "dnd":
                    do_not_disturb(bool(body.get("on")))
                elif act == "brightness":
                    screen_brightness(max(5, min(100, int(body.get("level", 50)))))
                elif act == "wifijoin":
                    return self.reply({**qa_view(), "joined": wifi_connect(str(body.get("ssid") or ""))})
                elif act == "wifiscan":
                    return self.reply({**qa_view(), "networks": wifi_networks()})
                elif act == "wifiradio":
                    radios("WiFi", bool(body.get("on")))
                    time.sleep(3)  # it takes a moment to find networks after switching on
                    return self.reply({**qa_view(), "networks": wifi_networks() if body.get("on") else []})
                elif act == "wifinew":
                    return self.reply({**qa_view(), "joined": wifi_join_new(str(body.get("ssid") or ""), str(body.get("password") or ""))})
                elif act == "btscan":
                    return self.reply({**qa_view(), "found": bt_scan()})
                elif act == "mix":
                    return self.reply({"mixer": mixer_set(str(body.get("group")), int(body.get("delta", 0)))})  # quick: only the mixer
                elif act == "btforget":
                    bt_forget(str(body.get("addr") or ""))
                elif act == "btpair":
                    bt_pair(str(body.get("addr") or ""))
                    time.sleep(3)  # its sound output takes a moment to appear
                elif act == "bt":
                    bt_audio_connect(str(body.get("addr") or ""), bool(body.get("connect", True)))
                elif act in ("wifi", "nightlight", "bluetooth"):
                    open_target({"wifi": "ms-availablenetworks:", "nightlight": "ms-settings:nightlight", "bluetooth": "ms-settings:bluetooth"}[act])
                else:
                    raise ValueError("Unknown action")
                return self.reply(qa_view())
            if path == "/api/rescan":
                scan()
                return self.reply({"ok": True})
            if path == "/api/options":
                cfg = config()
                for k in OPTION_KEYS:
                    if k in body:
                        cfg[k] = bool(body[k])
                if body.get("startup") in STARTUP_MODES:
                    cfg["startup"] = body["startup"]
                store("config.json", cfg)
                if "startup" in body:
                    set_autostart(cfg["startup"])
                if "keepOnScreen" in body:
                    keep_on_screen(cfg["keepOnScreen"])
                scan()
                return self.reply(settings_view())
            if path == "/api/profile":
                cfg = config()
                p = cfg.setdefault("profile", {})
                if isinstance(body.get("name"), str):
                    p["name"] = body["name"].strip()[:32]
                if "avatar" in body:
                    p["avatar"] = re.sub(r"[^a-z0-9-]", "", str(body["avatar"]))[:24]
                if "timezone" in body:
                    zone = str(body["timezone"])
                    p["timezone"] = zone if re.fullmatch(r"[A-Za-z]+(/[A-Za-z0-9_+-]+){1,2}", zone) else "auto"
                if "setupDone" in body:
                    p["setupDone"] = bool(body["setupDone"])
                store("config.json", cfg)
                note_data_folder(DATA)  # a finished setup is the one a new copy should find
                return self.reply(profile())
            if path == "/api/profile/picture":
                src = pick("file", "Choose a profile picture", [("Images", "*.png *.jpg *.jpeg *.webp *.gif")])
                if not src:
                    return self.reply({"cancelled": True})
                ext = os.path.splitext(src)[1].lower()
                if ext not in IMG_EXT + (".gif",) or os.path.getsize(src) > 15 * 1024 * 1024:
                    raise ValueError("Choose a PNG, JPG, WEBP or GIF under 15 MB")
                try:
                    from PIL import Image
                    with Image.open(src) as im:
                        im.verify()
                except Exception:
                    raise ValueError("That file isn't a picture that can be opened")
                for old in glob.glob(os.path.join(DATA, "avatar.*")):
                    os.remove(old)
                with open(src, "rb") as fi, open(os.path.join(DATA, "avatar" + ext), "wb") as fo:
                    fo.write(fi.read())
                cfg = config()
                cfg.setdefault("profile", {})["avatar"] = "picture"
                store("config.json", cfg)
                return self.reply(profile())
            if path in ("/api/romroot/choose", "/api/romroot/default"):
                folder = default_rom_root() if path.endswith("default") else pick("dir", "Choose or create your ROMs folder (a subfolder for each console goes inside)")
                if not folder:
                    return self.reply({"cancelled": True})
                made, found = set_rom_root(folder)
                scan()
                return self.reply({**settings_view(), "made": made, "found": found})
            if path == "/api/home/move":  # Settings › Libraries: ROMs and downloaded emulators into C:\Ultra-Front-End
                r = move_to_home()
                return self.reply({**settings_view(), **r})
            if path == "/api/romroot/open":
                root = config().get("romRoot")
                if not root or not os.path.isdir(root):
                    raise ValueError("Set up your ROMs folder first")
                open_target(root)
                return self.reply({"ok": True})
            if path == "/api/emulators/update":  # Settings › Systems: one emulator ("name"), or every one with an update
                if body.get("check"):
                    with EMU_UPDATE_LOCK:
                        check_emulator_updates()
                else:
                    names = [body["name"]] if isinstance(body.get("name"), str) else [*EMU_UPDATES["github"], *EMU_UPDATES["winget"]]
                    queue_emulator_updates(names)
                return self.reply(settings_view())
            if path == "/api/emulators/install":  # waits its turn in the install queue (/api/systems/queue)
                if body.get("system") not in EMU_INSTALL:
                    raise ValueError("No such console")
                queue_install([body["system"]])
                return self.reply(settings_view())
            if path == "/api/systems/choose":  # the setup guide's list: these systems and no others, installing their emulators if asked
                picked = body.get("systems")
                if not isinstance(picked, list) or not all(isinstance(x, str) for x in picked):
                    raise ValueError("Send a list of systems")
                choose_systems(picked, bool(body.get("install")))
                return self.reply(settings_view())
            if path in ("/api/systems/add", "/api/systems/remove", "/api/systems/bios", "/api/systems/emulator-folder"):
                system = body.get("system") or ""
                if system not in SYSTEM_GROUP:
                    raise ValueError("No such system")
                if path.endswith("emulator-folder"):  # where its emulator is: the folder of the program in its settings, never a path from the page
                    emu = config().get("emulators", {}).get(system, {}).get("path", "")
                    folder = emu if os.path.isdir(emu) else os.path.dirname(emu)
                    if not emu or not os.path.isdir(folder):
                        raise ValueError(f"{system} has no emulator on this PC yet")
                    open_target(folder)
                    return self.reply({"ok": True})
                if path.endswith("bios"):  # its BIOS folder, made if missing: a path built here, never one from the page
                    if system not in BIOS_NEEDS:
                        raise ValueError(f"{system} needs no BIOS files")
                    cfg = config()
                    if not cfg.get("romRoot") or not os.path.isdir(cfg["romRoot"]):
                        raise ValueError("Set up your ROMs folder first")
                    ensure_folders(system, cfg)
                    folder = bios_dir(cfg, system, create=True)
                    os.makedirs(folder, exist_ok=True)
                    open_target(folder)
                    return self.reply({"ok": True})
                (add_system if path.endswith("add") else remove_system)(system)
                return self.reply(settings_view())
            if path == "/api/emulators/set":
                system = body.get("system") or ""
                if system not in {s[1] for s in SYSTEMS}:
                    raise ValueError("No such console")
                exe = pick("file", f"Choose the emulator for {system}")
                if not exe:
                    return self.reply({"cancelled": True})
                cfg = config()
                cfg.setdefault("emulators", {})[system] = {"path": exe, "args": emulator_args(exe, (system_info(system) or {"cores": []})["cores"], system)}
                store("config.json", cfg)
                scan()
                apply_soon()
                return self.reply(settings_view())
            if path == "/api/launching/cancel":  # B on the launch screen
                LAUNCH_CANCEL.add(body.get("id"))
                LAUNCHING.discard(body.get("id"))
                return self.reply({"ok": True})
            if path == "/api/clipboard":  # the on-screen keyboard's Paste (POST: a web page elsewhere can't ask for it)
                return self.reply({"text": read_clipboard()})
            if path == "/api/emulators/site":  # only the project pages listed above, never an address from the page
                site = system_site(body.get("system") or "")
                if not site:
                    raise ValueError("No project page for this console")
                open_target(site)
                return self.reply({"ok": True})
            if path == "/api/emulators/clear":
                cfg = config()
                cfg.get("emulators", {}).pop(body.get("system") or "", None)
                store("config.json", cfg)
                scan()
                return self.reply(settings_view())
            if path == "/api/emulators/find":
                cfg = config()
                found = auto_emulators(cfg)
                store("config.json", cfg)
                scan()
                return self.reply({**settings_view(), "found": found})
            if path == "/api/libraries/add":
                lib = add_library(body.get("kind"), body.get("provider"))
                if lib:
                    scan()
                return self.reply({"added": lib["name"] if lib else None, "count": STATE["counts"].get("lib:" + lib["id"], 0) if lib else 0})
            if path == "/api/libraries/remove":
                cfg = config()
                cfg["libraries"] = [l for l in cfg["libraries"] if l["id"] != body.get("id")]
                store("config.json", cfg)
                scan()
                return self.reply(settings_view())
            if path == "/api/accounts/steam":
                key = (body.get("key") or "").strip()
                if not re.fullmatch(r"[0-9A-Fa-f]{32}", key):
                    raise ValueError("A Steam Web API key is 32 letters and numbers")
                try:
                    sid = resolve_steam_id(body.get("profile") or "", key)
                    scan_steam_account({"steamid": sid, "key": key})  # fails here if the key or profile is wrong/private
                except urllib.error.HTTPError as e:
                    raise ValueError("Steam didn't accept that API key" if e.code in (401, 403) else "Steam couldn't be reached. Try again.") from e
                accounts = load("accounts.json", {})
                accounts["steam"] = {"steamid": sid, "key": key}
                store("accounts.json", accounts)
                scan()
                return self.reply(settings_view())
            if path == "/api/accounts/epic/open":
                open_target(EPIC_LOGIN_URL)
                return self.reply({"ok": True})
            if path == "/api/steam/downloads":  # pause, resume and reorder happen there
                open_in_steam("steam://open/downloads")
                return self.reply({"ok": True})
            if path == "/api/accounts/steam/open":
                open_target("https://steamcommunity.com/dev/apikey")
                return self.reply({"ok": True})
            if path == "/api/accounts/epic":
                accounts = load("accounts.json", {})
                try:
                    accounts["epic"] = epic_login(body.get("code") or "")
                except urllib.error.HTTPError as e:
                    raise ValueError("That Epic code is wrong or has expired. Sign in again and copy a new one.") from e
                store("accounts.json", accounts)
                scan()
                return self.reply(settings_view())
            if path == "/api/accounts/sgdb":
                key = (body.get("key") or "").strip()
                if not re.fullmatch(r"[0-9A-Za-z]{20,64}", key):
                    raise ValueError("Paste the API key from SteamGridDB's preferences page")
                try:
                    sgdb_search(key, "portal")
                except urllib.error.HTTPError as e:
                    raise ValueError("SteamGridDB didn't accept that key") from e
                accounts = load("accounts.json", {})
                accounts["sgdb"] = {"key": key}
                store("accounts.json", accounts)
                scan()
                return self.reply(settings_view())
            if path == "/api/accounts/sgdb/open":
                open_target(SGDB_KEY_PAGE)
                return self.reply({"ok": True})
            if path == "/api/accounts/ra/open":
                open_target(RA_KEY_PAGE)
                return self.reply({"ok": True})
            if path == "/api/accounts/ra":
                user, key = (body.get("user") or "").strip(), (body.get("key") or "").strip()
                if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", user):
                    raise ValueError("Type your RetroAchievements username")
                if not re.fullmatch(r"[0-9A-Za-z]{20,64}", key):
                    raise ValueError("Paste the Web API key from RetroAchievements' settings page")
                try:
                    found = ra("API_GetUserProfile.php", {"user": user, "key": key}, u=user)  # not "profile": that would hide profile() from all of do_POST
                except urllib.error.HTTPError as e:
                    raise ValueError("RetroAchievements didn't accept that username and key") from e
                if not isinstance(found, dict) or not found.get("User"):
                    raise ValueError("RetroAchievements didn't find that user")
                accounts = load("accounts.json", {})
                accounts["ra"] = {"user": found["User"], "key": key, "ulid": found.get("ULID", ""), "points": found.get("TotalPoints", 0),
                                  "pic": RA_MEDIA + found["UserPic"] if str(found.get("UserPic", "")).startswith("/") else ""}
                store("accounts.json", accounts)
                ACH.clear()
                return self.reply(settings_view())
            if path == "/api/art/options":
                key = (load("accounts.json", {}).get("sgdb") or {}).get("key")
                g = STATE["byId"].get(body.get("id"))
                if not g:
                    raise ValueError("Game not found")
                query = (body.get("query") or "").strip()
                kind = body.get("kind") if body.get("kind") in ("hero", "logo") else "cover"
                extra = [] if kind == "logo" else libretro_art(g, kind, query)  # emulated games: libretro's box art and screens too
                if not key:
                    if g.get("source") != "Emulators":
                        raise ValueError("Connect SteamGridDB first")
                    return self.reply({"current": None, "games": [], "grids": extra})
                found = sgdb_search(key, query or g["title"])
                current = next((f for f in found if f["id"] == body.get("sgdbId")), None)
                if not current and not query:
                    current = sgdb_game_for(key, g)
                current = current or (found[0] if found and query else None)  # not this game's: let the list below choose
                results = ([current] if current else []) + [f for f in found if not current or f["id"] != current["id"]]
                return self.reply({"current": current, "games": results[:6], "grids": (sgdb_grids(key, current["id"], kind) if current else []) + extra})
            if path == "/api/art/set":
                if body.get("id") not in STATE["byId"]:
                    raise ValueError("Game not found")
                set_art(body["id"], body.get("url") or "", body.get("kind") if body.get("kind") in ("hero", "logo") else "cover")
                scan()
                return self.reply({"ok": True})
            if path == "/api/art/reset":
                reset_art(body.get("id") or "", body.get("kind") if body.get("kind") in ("hero", "logo") else "cover")
                scan()
                return self.reply({"ok": True})
            if path == "/api/accounts/remove":
                accounts = load("accounts.json", {})
                accounts.pop(body.get("name"), None)
                store("accounts.json", accounts)
                scan()
                return self.reply(settings_view())
            return self.send_error(404)
        except urllib.error.HTTPError as e:
            return self.reply({"error": f"The service said no ({e.code}). Check the details and try again."}, 400)
        except (urllib.error.URLError, TimeoutError):
            return self.reply({"error": "Couldn't reach the internet service"}, 400)
        except (ValueError, KeyError, OSError) as e:
            return self.reply({"error": str(e)}, 400)
        except Exception as e:  # a bug rather than bad input
            log_error()
            return self.reply({"error": f"Something went wrong ({type(e).__name__}: {e})"}, 500)


# ---------------------------------------------------------------- updates from the GitHub project
# A copy of the exe (not the project folder, not one run from source) keeps itself current from the project's GitHub releases:
# the newest release's exe is downloaded beside this one and checked against GitHub's SHA-256, then swapped in once nothing is
# open or running. The new copy takes over from this one (frontend.py replace_old_helper); if it never starts, the old exe goes
# back and that version waits a day.
UPDATE = {"state": "", "latest": None, "error": "", "checked": 0.0, "retry": 0.0, "done": None, "quick": 0.0}
QUICK_EVERY = 60  # how often github.com is asked which release is the latest: a tiny request, not the API (no hourly limit)


def latest_tag():
    """The newest release's version, from github.com's own "latest release" redirect, or "" if it can't tell. Asked every
    minute, so an update starts downloading within a minute of being published; the API is asked only when this changes."""
    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None  # read where it points instead of going there
    req = urllib.request.Request(f"https://github.com/{UPDATE_REPO}/releases/latest", method="HEAD", headers={"User-Agent": UA})
    try:
        urllib.request.build_opener(Stay).open(req, timeout=10)
    except urllib.error.HTTPError as e:
        where = e.headers.get("Location", "") if e.code in (301, 302, 303, 307, 308) else ""
        m = re.search(r"/releases/tag/v?([0-9][\w.-]*)$", where)
        return m.group(1) if m else ""
    except (OSError, ValueError):
        return ""
    return ""
UPDATE_LOCK = threading.Lock()
UPDATE_EVERY = 3600  # GitHub is asked this often (fixes reach everyone within the hour); an unchanged answer (ETag) doesn't count against its hourly limit
UPDATE_ASSET = "UltraFrontEnd-mac.zip" if MAC else "UltraFrontEnd.exe"  # the release file tools/release.py uploads (the Mac app zipped)


NIGHTLY_TAG = "nightly"  # the pre-release the nightly build job (.github/workflows/nightly.yml) replaces each night


def version_key(v):
    """Comparable versions: 1.2.7-nightly.202611080300 comes after 1.2.6 and before 1.2.7 (the release it leads up to)."""
    v = v or ""
    m = re.search(r"-nightly\.(\d+)", v)
    nums = tuple(int(x) for x in re.findall(r"\d+", v[:m.start()] if m else v)[:3]) or (0,)
    return nums + (0,) * (3 - len(nums)) + ((0, int(m.group(1))) if m else (1, 0))


def is_nightly(v):
    return "-nightly." in (v or "")


def update_channel():
    """Settings › About: "main" (the releases) or "nightly" (a build of the newest code every night, and the releases too)."""
    return "nightly" if config().get("updateChannel") == "nightly" else "main"


def wanted_release(rel):
    """Whether this copy should move to that release: a newer one, or the main release when someone on a nightly build
    has gone back to the main channel (that one is older, by number)."""
    if not rel or not rel.get("version") or rel["version"] == VERSION:
        return False
    if version_key(rel["version"]) > version_key(VERSION):
        return True
    return update_channel() == "main" and is_nightly(VERSION) and not is_nightly(rel["version"])


def exe_build(path):
    """The build stamp (as BUILD) of the exe at a path, or "" if there's none."""
    try:
        return "%d-%d" % (int(os.path.getmtime(path)), os.path.getsize(path))
    except OSError:
        return ""


def file_sha256(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def updates_off():
    """Why this copy doesn't update itself, or "" when it does."""
    if MAC:
        bundle = mac_bundle() if getattr(sys, "frozen", False) else ""
        if not bundle:
            return "Only the downloaded app updates itself"
        if "/AppTranslocation/" in bundle or bundle.startswith("/Volumes/"):
            return "Move Ultra Front End into your Applications folder to get updates"
        return "" if os.access(os.path.dirname(bundle), os.W_OK) else "macOS won't let it change the folder it's in. Move it to Applications to get updates"
    if not (WIN and getattr(sys, "frozen", False)):
        return "Only the downloaded exe updates itself"
    if os.path.isdir(os.path.join(ROOT, ".git")):
        return "This copy runs from the project folder: build it again to update"
    import tempfile
    try:  # os.access can't tell on Windows, so try it
        tempfile.TemporaryFile(dir=ROOT).close()
    except OSError:
        return "Windows won't let it change the folder it's in. Move it to a folder of your own to get updates"
    return ""


def latest_release():
    """The release this copy's channel offers (version, notes, and its exe with GitHub's SHA-256), or None while there's
    none: the newest main release, or on the nightly channel whichever is newer of that and the latest nightly build."""
    main = fetch_release(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest", "release")
    if update_channel() != "nightly":
        return main
    try:
        night = fetch_release(f"https://api.github.com/repos/{UPDATE_REPO}/releases/tags/{NIGHTLY_TAG}", "nightlyRelease")
    except (urllib.error.URLError, OSError, ValueError):
        night = None  # no nightly build yet, or GitHub didn't answer: the main release still counts
    found = [r for r in (main, night) if r and r.get("version")]
    return max(found, key=lambda r: version_key(r["version"])) if found else None


def fetch_release(api_url, key):
    """One release from GitHub's API, remembered in update.json under key (with its ETag, so an unchanged answer is free)."""
    saved = load("update.json", {})
    etag_key = "etag" if key == "release" else key + "Etag"
    # a stand-in for GitHub's answer on this PC, to try an update end to end without publishing one (main channel only)
    test = os.environ.get("UFE_UPDATE_API", "") if key == "release" else ""
    test = test if test.startswith(("http://127.0.0.1:", "http://localhost:")) else ""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if saved.get(etag_key) and saved.get(key) and not test:
        headers["If-None-Match"] = saved[etag_key]
    try:
        with urllib.request.urlopen(urllib.request.Request(test or api_url, headers=headers), timeout=15) as r:
            rel, etag = json.loads(r.read().decode("utf-8")), r.headers.get("ETag", "")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return saved[key]
        if e.code == 404:  # nothing published yet
            return None
        raise
    asset = next((a for a in rel.get("assets") or [] if a.get("name") == UPDATE_ASSET), None) or {}
    url, digest = asset.get("browser_download_url", ""), str(asset.get("digest") or "").lower()
    # only this project's own download, and only with a SHA-256 to check it against
    ok = digest.startswith("sha256:") and asset.get("size") and (test or url.startswith(f"https://github.com/{UPDATE_REPO}/releases/download/"))
    # a nightly build's version is its release title (its tag, "nightly", stays the same every night)
    version = str(rel.get("name") if key != "release" else rel.get("tag_name") or "").strip().lstrip("vV")
    if key != "release":  # a readable title ("Ultra Front End 1.2.7 Nightly, 6 November 2026"): the exact version is in its notes
        m = re.search(r"\d+\.\d+\.\d+-nightly\.\d+", f'{rel.get("name") or ""} {rel.get("body") or ""}')
        version = m.group(0) if m else version
    release = {"version": version, "notes": str(rel.get("body") or ""), "page": str(rel.get("html_url") or ""),
               "exe": {"url": url, "size": asset["size"], "sha256": digest[7:]} if ok else None}
    if key != "release" and not is_nightly(version):
        release["exe"] = None  # not a nightly build's title: never installed from here
    if not test:
        store("update.json", {**load("update.json", {}), etag_key: etag, key: release})
    return release


def download_update(release):
    """The release's exe, saved beside this one as <exe>.new once its size and SHA-256 match what GitHub lists."""
    exe, asset = frontend_exe(), release["exe"]
    part, ready = update_paths()
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(urllib.request.Request(asset["url"], headers={"User-Agent": UA}), timeout=60) as r, open(part, "wb") as f:
            while chunk := r.read(1 << 20):
                digest.update(chunk)
                f.write(chunk)
        with open(part, "rb") as f:
            head = f.read(2)
        if head != (b"PK" if MAC else b"MZ") or os.path.getsize(part) != asset["size"] or digest.hexdigest() != asset["sha256"]:
            raise ValueError("the download didn't match the release, so it wasn't used")
        os.replace(part, ready)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return ready


def update_busy():
    """A game, its in-game menu or a recording is going: an update would cut into it."""
    return bool(RUN_NOW or RUNNING or LAUNCHING or overlay_open() or RECORD["proc"])


def note_start():
    """The copy that is (or is about to be) the helper says so, so an update can tell its new copy ran. Also written when that
    copy leaves an older helper running because a game had started: it works, it just waits."""
    if getattr(sys, "frozen", False):
        try:
            store("started.json", {"version": VERSION, "build": BUILD, "at": time.time()})
        except OSError:
            pass


def started_since(version, since):
    s = load("started.json", {})
    return s.get("version") == version and s.get("at", 0) >= since


def fail_version(version, days=1):
    """Leave a version alone for a while: it didn't start, or it isn't what its release says it is."""
    saved = load("update.json", {})
    failed = saved.get("failed") if isinstance(saved.get("failed"), dict) else {}
    store("update.json", {**saved, "failed": {**failed, version: time.time() + days * 86400}, "installing": None})


def follow_rename(path):
    """PyInstaller reads this copy's not-yet-used modules from its own exe, by name: after renaming the exe, read them from
    the new name, or the first screenshot or folder picker after an update would fail."""
    pyz = getattr(sys.modules.get("pyimod02_importers"), "pyz_archive", None)
    if pyz is not None and hasattr(pyz, "_filename"):
        pyz._filename = path


def close_window(hwnd, seconds=10):
    import ctypes
    ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)  # WM_CLOSE, as the tray's Exit does
    deadline = time.time() + seconds
    while frontend_window() and time.time() < deadline:
        time.sleep(0.2)
    return not frontend_window()


def install_update(ready, version, reopen=False):
    """Swap the new exe in (the running one is renamed, which Windows allows) and start it; it asks this copy to quit once it
    has taken over. If it never gets that far, the old exe goes back."""
    if MAC:
        return install_update_mac(ready, version)
    exe = frontend_exe()
    base = exe[:-4] if exe.lower().endswith(".exe") else exe
    old = base + ".old.exe"
    try:
        os.remove(old)
    except FileNotFoundError:
        pass
    except OSError:  # still running: a window from before an earlier update. Set this one aside under its own name
        old = f"{base}.old-{int(time.time())}.exe"
    os.replace(exe, old)
    follow_rename(old)
    try:
        os.replace(ready, exe)
    except OSError:
        os.replace(old, exe)
        follow_rename(exe)
        raise
    store("update.json", {**load("update.json", {}), "installing": version, "from": VERSION, "reopen": reopen})
    since = time.time()
    if start_alone(["--background"] + (["--port", str(PORT)] if PORT != 8137 else [])):
        for _ in range(180):  # counted, not timed: a PC that sleeps meanwhile doesn't make the new copy look dead
            time.sleep(1)
            if started_since(version, since):
                UPDATE["done"], UPDATE["state"] = version, "installed"  # it's taking over now, or will once the game ends
                return
    fail_version(version)  # first, so it isn't tried again straight away whatever happens below
    try:
        os.replace(exe, f"{base}.bad-{int(time.time())}.exe")
    except OSError:
        pass  # gone (antivirus took it) or still held: putting the old one back below still works
    os.replace(old, exe)
    follow_rename(exe)
    UPDATE["state"], UPDATE["error"] = "", f"Version {version} didn't start, so this one was kept"


def update_step(action=None):
    """Ask GitHub if it's time, fetch a newer release, and install it if nothing is in the way. action comes from Settings:
    "check" asks GitHub now and gives a version that failed another go; "install" also goes ahead while the frontend is
    open (it closes, and the new copy opens it again)."""
    if updates_off() or UPDATE["done"] or not UPDATE_LOCK.acquire(blocking=False):
        return
    try:
        now = time.time()
        if not action and now < UPDATE["retry"]:
            return
        newer = False
        if not action and now - UPDATE["quick"] >= QUICK_EVERY - 1:  # each minute: has a newer release appeared?
            UPDATE["quick"] = now
            tag = latest_tag()
            known = (UPDATE["latest"] or {}).get("version") or VERSION
            newer = bool(tag) and version_key(tag) > version_key(known)
        if action or newer or now - UPDATE["checked"] > UPDATE_EVERY:
            UPDATE["checked"], UPDATE["state"] = now, "checking"
            UPDATE["latest"] = latest_release()
        rel, saved = UPDATE["latest"], load("update.json", {})
        failed = saved.get("failed") if isinstance(saved.get("failed"), dict) else {}
        if rel and action and rel["version"] in failed:
            failed.pop(rel["version"])
            store("update.json", {**saved, "failed": failed})
        if not rel or not rel.get("exe") or not wanted_release(rel) or failed.get(rel["version"], 0) > now:
            UPDATE["state"], UPDATE["error"] = "current", ""
            return
        exe, digest = frontend_exe(), rel["exe"]["sha256"]
        if exe_build(exe) != BUILD:  # the exe on disk isn't this copy any more: an update is in place, waiting to take over
            UPDATE["done"], UPDATE["state"] = rel["version"], "installed"
            return
        ready = update_paths()[1]
        if saved.get("ready") != digest or not os.path.isfile(ready):
            UPDATE["state"] = "downloading"
            download_update(rel)
            store("update.json", {**load("update.json", {}), "ready": digest})
        UPDATE["state"], UPDATE["error"] = "ready", ""
        if update_busy():
            if action == "install":
                UPDATE["error"] = "It installs once the game, in-game menu or recording has finished"
            return
        window = True if MAC else frontend_window()  # (on a Mac the helper lives in the window: an update goes in when asked, or when idle)
        if window and action != "install":
            return  # it goes in once the frontend is closed
        if file_sha256(ready) != digest:  # changed since it was downloaded
            os.remove(ready)
            raise ValueError("the downloaded update changed on disk, so it will be fetched again")
        if window and not MAC and not close_window(window):
            raise ValueError("the frontend didn't close")
        UPDATE["state"] = "installing"
        install_update(ready, rel["version"], reopen=bool(window))
    except Exception as e:
        UPDATE["state"], UPDATE["error"] = "", f"Couldn't update: {e}"
        UPDATE["retry"] = time.time() + 3600  # a failed download or install waits an hour (Settings can try sooner)
    finally:
        UPDATE_LOCK.release()


def clean_after_update():
    """The exes an update leaves beside this one (the previous version, a bad one, a broken download), once they're not in use."""
    if MAC:
        bundle = mac_bundle()
        for f in ([bundle[:-4] + ".old.app", bundle[:-4] + ".new.app"] if bundle else []) + list(update_paths()[:1]):
            (shutil.rmtree if os.path.isdir(f) else os.remove)(f) if os.path.exists(f) else None
        return
    exe = frontend_exe()
    base = exe[:-4] if exe.lower().endswith(".exe") else exe
    for f in glob.glob(glob.escape(base) + ".old*.exe") + glob.glob(glob.escape(base) + ".bad-*.exe") + [exe + ".download"]:
        try:
            os.remove(f)
        except OSError:
            pass  # still running (a window from before the update) or already gone


USAGE_URL = f"https://github.com/{UPDATE_REPO}/releases/download/usage/checkin.txt"


def watch_usage():
    """Once a day, while the helper runs, this copy downloads a tiny file from the project's GitHub page, so GitHub's
    download count shows how many copies are in use (a daily job writes the totals to stats/usage.csv). Nothing about
    the person or their games is sent. Off in Settings › About; never from a test copy on another port or a source run."""
    if PORT != 8137 or not getattr(sys, "frozen", False) or updates_off():
        return
    while True:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if config().get("usageCheckin", True) and load("usage.json", {}).get("day") != today:
            try:
                req = urllib.request.Request(USAGE_URL, headers={"User-Agent": "UltraFrontEnd"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    r.read(64)
                store("usage.json", {"day": today})
            except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                pass  # offline: tried again within the hour
        time.sleep(3600)


def watch_updates():
    """In the helper, once it has the port: finish an update that just went in, then look for the next one now and then."""
    if updates_off():
        return
    saved = load("update.json", {})
    if saved.get("installing") == VERSION:  # this copy is the update: the page says so once, and reopens if it was open
        store("update.json", {**saved, "installing": None, "reopen": False,
                              "updated": {"version": VERSION, "from": saved.get("from"),
                                          "notes": (saved.get("nightlyRelease" if is_nightly(VERSION) else "release") or {}).get("notes", "")}})
        if saved.get("reopen"):
            threading.Thread(target=open_frontend, daemon=True).start()
    elif saved.get("installing"):  # the release said one version but its exe is another: don't install it over and over
        fail_version(saved["installing"], days=3650)
    clean_after_update()
    if PORT != 8137:
        return  # a test copy updates only when asked (Settings, or POST /api/update)
    time.sleep(90)  # after the first scan, and after a takeover has settled
    while True:
        update_step()
        time.sleep(QUICK_EVERY)  # new releases are noticed, and a waiting update goes in, within a minute


def update_view():
    saved = load("update.json", {})
    rel = UPDATE["latest"] or (saved.get("release") if update_channel() == "main" else None) or {}
    newer = wanted_release(rel)
    return {"version": VERSION, "channel": update_channel(), "off": updates_off(), "state": UPDATE["state"], "error": UPDATE["error"],
            "latest": rel.get("version") if newer else None, "notes": rel.get("notes", "") if newer else "", "updated": saved.get("updated")}


# ---------- the Mac versions that need this module's state (the rest are in plat_mac) ----------
def watch_running_mac():
    """Which games have a window open, as watch_running does on Windows: by install folder, plus anything started from here.
    The 'window' kept for each game is its pid, which running_resume brings to the front."""
    me = os.getpid()
    while True:
        time.sleep(3)
        try:
            wins = plat_mac.windows()
            folders, now = game_folders(), {}
            paths = {pid: plat_mac.process_image(pid) for pid in {w[1] for w in wins} if pid != me}
            for pid, path in paths.items():
                hit = max((d for d in folders if path.startswith(d)), key=len, default=None)
                if hit:
                    now.setdefault(folders[hit], (pid, pid))
            for game, proc in list(RUNNING.items()):
                tree = game_tree(proc.pid)
                if tree and game not in now:
                    pid = next((w[1] for w in wins if w[1] in tree), proc.pid)
                    now[game] = (pid, pid)
            RUN_NOW.clear()
            RUN_NOW.update(now)
        except Exception:
            pass


def focus_process_mac(pid, timeout=120):
    """Bring a launched game to the front once it has a window (a launcher hands over to the game itself)."""
    FOCUS[0] += 1
    token = FOCUS[0]

    def run():
        deadline = time.time() + timeout
        while time.time() < deadline and FOCUS[0] == token:
            tree = game_tree(pid) or plat_mac.process_tree(pid)
            hit = next((w[1] for w in plat_mac.windows() if w[1] in tree), None)
            if hit:
                plat_mac.activate(hit)
                return
            time.sleep(0.5)
    threading.Thread(target=run, daemon=True).start()


def trash_mac(path):
    """To the Trash, so anything deleted from the album can be brought back (no Finder permission needed)."""
    trash = os.path.expanduser("~/.Trash")
    name, ext = os.path.splitext(os.path.basename(path))
    dest, n = os.path.join(trash, name + ext), 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(trash, f"{name} {n}{ext}")
    try:
        shutil.move(path, dest)
        return True
    except OSError:
        return False


# ---------- Mac: the app bundle, updating it, opening at login, the controller, emulators from their own projects ----------
def mac_bundle():
    """The .app this program runs from (…/Ultra Front End.app), or "" when it isn't in one (a source run)."""
    d = sys.executable
    while d and os.path.dirname(d) != d:
        if d.endswith(".app"):
            return d
        d = os.path.dirname(d)
    return ""


def update_paths():
    """Where an update is downloaded (part) and kept once checked (ready): beside the exe on Windows, beside the .app on a Mac."""
    if MAC:
        bundle = mac_bundle() or frontend_exe()
        return bundle + ".download", bundle + ".new.zip"
    exe = frontend_exe()
    return exe + ".download", exe + ".new"


def install_update_mac(ready, version):
    """Unpack the new .app beside this one, check it, swap the two, open the new one and leave. The old one stays beside it
    as "Ultra Front End.old.app" until the new one has run (clean_after_update), so it can be put back by hand if need be."""
    import plistlib
    import tempfile
    bundle = mac_bundle()
    if not bundle:
        raise ValueError("this copy doesn't run from an app bundle")
    parent, name = os.path.dirname(bundle), os.path.basename(bundle)
    new, old = os.path.join(parent, name[:-4] + ".new.app"), os.path.join(parent, name[:-4] + ".old.app")
    with tempfile.TemporaryDirectory(prefix="ufe-update-", dir=parent) as staging:
        if subprocess.run(["/usr/bin/ditto", "-x", "-k", ready, staging], capture_output=True, timeout=300).returncode:
            raise ValueError("the update couldn't be unpacked")
        apps = [os.path.join(staging, f) for f in os.listdir(staging) if f.endswith(".app")]
        if len(apps) != 1:
            raise ValueError("the update isn't one app")
        with open(os.path.join(apps[0], "Contents", "Info.plist"), "rb") as f:
            got = str(plistlib.load(f).get("CFBundleShortVersionString") or "")
        if got != version or not os.access(os.path.join(apps[0], "Contents", "MacOS", "Ultra Front End"), os.X_OK):
            raise ValueError(f"the update says it's version {got or '?'}, not {version}")
        shutil.rmtree(new, ignore_errors=True)
        os.rename(apps[0], new)
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", new], capture_output=True)
    shutil.rmtree(old, ignore_errors=True)
    os.rename(bundle, old)
    try:
        os.rename(new, bundle)
    except OSError:
        os.rename(old, bundle)
        raise
    store("update.json", {**load("update.json", {}), "installing": version, "from": VERSION, "reopen": True})
    try:
        os.remove(ready)
    except OSError:
        pass
    UPDATE["done"], UPDATE["state"] = version, "installed"
    subprocess.Popen(["/bin/sh", "-c", 'sleep 1.5; open -n "$0"', bundle], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Timer(0.3, lambda: os._exit(0)).start()  # the window lives in this process: it goes, and the new copy opens


LAUNCH_AGENT = os.path.expanduser("~/Library/LaunchAgents/com.imsammyttv.ultrafrontend.plist")


def set_autostart_mac(mode):
    """Open at login: a LaunchAgent that opens the app (there's no background helper or tray on a Mac)."""
    import plistlib
    if mode == "open" and mac_bundle():
        os.makedirs(os.path.dirname(LAUNCH_AGENT), exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as f:
            plistlib.dump({"Label": "com.imsammyttv.ultrafrontend", "ProgramArguments": ["/usr/bin/open", "-a", mac_bundle()],
                           "RunAtLoad": True, "ProcessType": "Interactive"}, f)
    else:
        try:
            os.remove(LAUNCH_AGENT)
        except OSError:
            pass


def uninstall_mac(wipe):
    """Settings > About > Uninstall on a Mac: the app, its leftover update copies and its open-at-login entry go to the
    Trash (so they can be put back), and with wipe its settings, artwork, captures and WebKit data too. Emulators it
    installed are apps of their own and stay. Returns what couldn't be moved and a function that trashes the data: the
    caller runs it as the app quits, so nothing writes a new data folder after it's gone."""
    from Foundation import NSFileManager, NSURL
    bundle = mac_bundle()
    if not bundle or "/AppTranslocation/" in bundle or bundle.startswith("/Volumes/"):
        return ["Ultra Front End is running from the disk image, not Applications. Quit it and drag it from Applications to the Trash"], None
    ident = "com.imsammyttv.ultrafrontend"
    lib = os.path.expanduser("~/Library")
    paths = [LAUNCH_AGENT, bundle, *update_paths(), bundle[:-4] + ".old.app"]
    data = []
    if wipe:
        data = [DATA, os.path.join(lib, "WebKit", ident), os.path.join(lib, "Caches", ident), os.path.join(lib, "HTTPStorages", ident),
                  os.path.join(lib, "Saved Application State", ident + ".savedState"), os.path.join(lib, "Preferences", ident + ".plist")]
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{ident}"], capture_output=True)  # loaded at sign-in; harmless if not
    fm = NSFileManager.defaultManager()

    def trash(items):
        failed = []
        for p in items:
            if os.path.lexists(p):
                ok, _, _ = fm.trashItemAtURL_resultingItemURL_error_(NSURL.fileURLWithPath_(p), None, None)
                if not ok:
                    failed.append(os.path.basename(p))
        return failed
    return trash(paths), lambda: trash(data)


def mac_home_opens_us():
    """Does the controller's Xbox / home button open this app? (System Settings > Game Controllers > Press Home Button to Open)"""
    try:
        r = subprocess.run(["defaults", "read", "com.apple.GameController", "homeButtonLongPressAction"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() == "com.imsammyttv.ultrafrontend"
    except (OSError, subprocess.SubprocessError):
        return False


# The controller, read through macOS' GameController framework (any pad the Mac knows: Xbox, PlayStation, Switch Pro, MFi).
# Like the XInput reader on Windows: the frontend's menus while it's in front, the home button to bring it forward.
MAC_BUTTONS = {"a": "ok", "b": "back", "y": "options", "menu": "options", "l1": "prevTab", "r1": "nextTab"}


def watch_controller_mac():
    try:
        from GameController import GCController
    except Exception:
        return
    try:  # presses reach this app from behind other apps too, so the Xbox button can bring the frontend forward
        GCController.setShouldMonitorBackgroundEvents_(True)
    except Exception:
        pass
    held, repeat, combo, last_open, claimed = {}, {}, {}, 0.0, set()
    while True:
        front = frontend_in_front()
        time.sleep(0.016 if front else 0.05)
        now = time.time()
        pads, dirs = 0, set()
        try:
            pads_now = list(GCController.controllers())
        except Exception:
            pads_now = []
        for i, c in enumerate(pads_now):
            g = c.extendedGamepad()
            if g is None:
                continue
            pads += 1
            if id(c) not in claimed:  # while the frontend is in front, the Xbox button is ours, not macOS' Games app (2 = disabled)
                claimed.add(id(c))
                try:
                    g.buttonHome().setPreferredSystemGestureState_(2)
                except Exception:
                    pass
            try:
                b = {"a": g.buttonA(), "b": g.buttonB(), "x": g.buttonX(), "y": g.buttonY(), "menu": g.buttonMenu(), "view": g.buttonOptions(),
                     "home": g.buttonHome(), "l1": g.leftShoulder(), "r1": g.rightShoulder()}
                b = {k: bool(v is not None and v.isPressed()) for k, v in b.items()}
                dp, lx, ly = g.dpad(), g.leftThumbstick().xAxis().value(), g.leftThumbstick().yAxis().value()
                d = {"up": dp.up().isPressed() or ly > .55, "down": dp.down().isPressed() or ly < -.55,
                     "left": dp.left().isPressed() or lx < -.55, "right": dp.right().isPressed() or lx > .55}
            except Exception:
                continue
            was = held.get(i, {})
            held[i] = b
            pressed = {k for k, v in b.items() if v and not was.get(k)}
            if not front and config().get("guideOpens") and ("home" in pressed or (b["view"] and b["menu"])) and now - last_open > 2:
                last_open = now
                open_frontend()
            if b["view"] and pressed - {"view"}:
                combo[i] = True
            if was.get("view") and not b["view"] and not combo.pop(i, False) and front:
                pad_emit("system", "mac")  # View on its own: Quick Access
            if not front or b["view"]:
                continue
            for k, action in MAC_BUTTONS.items():
                if k in pressed:
                    pad_emit(action, "mac")
            dirs |= {k for k, v in d.items() if v}
        PAD["pads"] = pads
        for d in ("up", "down", "left", "right"):  # held directions repeat like a key: once, then steadily after a pause
            if d not in dirs:
                repeat.pop(d, None)
            elif d not in repeat:
                repeat[d] = now + 0.38
                pad_emit(d, "mac")
            elif now >= repeat[d]:
                repeat[d] = now + 0.09
                pad_emit(d, "mac")


# Emulators on a Mac: each from its own project's downloads (GitHub releases, or Dolphin's own site), into ~/Applications.
# (emulator, "mac") installs from MAC_DOWNLOADS; "manual" only shows the project page (Homebrew or the site has it).
_MAC_MANUAL = lambda name: (name, "manual")
EMU_INSTALL_MAC = {
    "PS1": ("DuckStation", "mac"), "PS2": ("PCSX2", "mac"), "PS3": ("RPCS3", "mac"), "PS4": ("shadPS4", "mac"), "PS5": ("KytyPS5", "mac"),
    "PSP": ("PPSSPP", "mac"), "PS Vita": ("Vita3K", "mac"), "Switch 2": ("Eglantine", "mac"), "Switch": _MAC_MANUAL("Eden"),
    "Wii U": ("Cemu", "mac"), "Wii": ("Dolphin", "mac"), "GameCube": ("Dolphin", "mac"), "N64": ("ares", "mac"), "SNES": ("Mesen", "mac"),
    "3DS": ("Azahar", "mac"), "DS": ("melonDS", "mac"), "GBA": ("mGBA", "mac"), "GBC": ("mGBA", "mac"), "Game Boy": ("mGBA", "mac"),
    "Xbox 360": _MAC_MANUAL("Xenia Canary"), "Xbox": ("xemu", "mac"),
    **{s: ("Mesen", "mac") for s in ("NES", "FDS", "PC Engine", "PC Engine CD", "WonderSwan", "SG-1000")},
    **{s: _MAC_MANUAL("Mednafen") for s in ("Virtual Boy", "Neo Geo Pocket", "Atari Lynx", "PC-FX")},
    **{s: ("ares", "mac") for s in ("Genesis", "Sega CD", "32X", "Master System", "Game Gear", "64DD")},
    **{s: ("Flycast", "mac") for s in ("Dreamcast", "NAOMI", "NAOMI 2", "Atomiswave")},
    **{s: _MAC_MANUAL("MAME") for s in ("Atari 7800", "Arcade", "Neo Geo", "Neo Geo CD", "CD-i", "Intellivision", "Vectrex", "Odyssey 2", "Game & Watch")},
    **{s: ("openMSX", "mac") for s in ("ColecoVision", "MSX")},
    **{s: _MAC_MANUAL("Atari800") for s in ("Atari 5200", "Atari 8-bit")},
    **{s: _MAC_MANUAL("VICE") for s in ("C64", "VIC-20")},
    "Saturn": ("Ymir", "mac"), "Model 3": ("Supermodel", "mac"), "Atari 2600": ("Stella", "mac"), "Atari Jaguar": _MAC_MANUAL("BigPEmu"),
    "Atari ST": _MAC_MANUAL("Hatari"), "3DO": ("RetroArch", "retroarch:opera"), "Pokemon Mini": ("RetroArch", "retroarch:pokemini"),
    "Amstrad CPC": ("RetroArch", "retroarch:cap32"), "N-Gage": ("EKA2L1", "mac"), "Amiga": ("Amiberry", "mac"), "ZX Spectrum": ("ZEsarUX", "mac"),
    "DOS": ("DOSBox Staging", "mac"), "ScummVM": _MAC_MANUAL("ScummVM"), "Apple II": _MAC_MANUAL("AppleWin"), "Flash": ("Ruffle", "mac"),
}
# name: (GitHub repo, pattern for an Apple Silicon or universal download, pattern for an Intel one (Rosetta), the app's name)
# A download with no checksum on GitHub is only taken from the project's own address.
MAC_DOWNLOADS = {
    "DuckStation": ("stenzek/duckstation", r"^duckstation-mac-release\.zip$", None, "DuckStation.app"),
    "PCSX2": ("PCSX2/pcsx2", r"^pcsx2-v[\d.]+-macos-Qt\.tar\.xz$", None, "PCSX2*.app"),
    "RPCS3": ("RPCS3/rpcs3-binaries-mac-arm64", r"_macos_arm64\.7z$", ("RPCS3/rpcs3-binaries-mac", r"_macos\.7z$"), "RPCS3.app"),
    "shadPS4": ("shadps4-emu/shadPS4", r"^shadps4-macos-sdl-[\d.]+\.zip$", None, "shadps4*"),
    "KytyPS5": ("KytyPS5/KytyPS5", None, r"-macOS-x86_64\.zip$", "Kyty*"),
    "PPSSPP": ("hrydgard/ppsspp", r"^PPSSPPSDL-macOS-v[\d.]+\.zip$", None, "PPSSPP*.app"),
    "Vita3K": ("Vita3K/Vita3K", r"^macos-arm64-latest\.dmg$", r"^macos-latest\.dmg$", "Vita3K.app"),
    "Eglantine": ("Djihads80/Eglantine", r"^eglantine-macos-arm64\.zip$", None, "Eglantine*.app"),
    "Cemu": ("cemu-project/Cemu", None, r"^cemu-[\d.]+-macos-\d+-x64\.dmg$", "Cemu.app"),
    "Dolphin": ("https://dl.dolphin-emu.org/releases/2609a/dolphin-2609a-universal.dmg", None, None, "Dolphin.app"),  # its own site, as on Windows
    "ares": ("ares-emulator/ares", r"^ares-macos-universal\.zip$", None, "ares.app"),
    "Mesen": ("nesdev-org/MesenCE", r"^Mesen_[\d.]+_macOS_ARM64_AppleSilicon\.zip$", r"^Mesen_[\d.]+_macOS_x64_Intel\.zip$", "Mesen.app"),
    "Azahar": ("azahar-emu/azahar", r"^azahar-macos-universal-[\d.]+\.zip$", None, "Azahar*.app"),
    "melonDS": ("melonDS-emu/melonDS", r"^melonDS-[\d.]+-macOS-universal\.zip$", None, "melonDS.app"),
    "mGBA": ("mgba-emu/mgba", r"^mGBA-[\d.]+-macos\.dmg$", None, "mGBA.app"),
    "xemu": ("xemu-project/xemu", r"^xemu-[\d.]+-macos-universal\.zip$", None, "xemu.app"),
    "Flycast": ("flyinghead/flycast", r"^flycast-macOS-[\d.]+\.zip$", None, "Flycast.app"),
    "Supermodel": ("trzy/Supermodel", r"-macos\.tar\.gz$", None, "supermodel*"),
    "Stella": ("stella-emu/stella", r"^Stella-[\d.]+[a-z]?-macos\.dmg$", None, "Stella.app"),
    "Ymir": ("StrikerX3/Ymir", r"^ymir-macos-arm64-v[\d.]+\.zip$", r"^ymir-macos-x64-v[\d.]+\.zip$", "Ymir*.app"),
    "openMSX": ("openMSX/openMSX", r"^openmsx-[\d.]+-mac-aarch64-bin\.dmg$", r"^openmsx-[\d.]+-mac-x86_64-bin\.dmg$", "openMSX.app"),
    "EKA2L1": ("EKA2L1/EKA2L1", r"^EKA2L1-MacOS-arm64\.dmg$", None, "EKA2L1.app"),
    "Amiberry": ("BlitterStudio/amiberry", r"^Amiberry-[\d.]+-macOS-universal\.dmg$", None, "Amiberry.app"),
    "ZEsarUX": ("chernandezba/zesarux", r"^ZEsarUX_macos-silicon-[\d.]+\.dmg$", r"^ZEsarUX_macos-intel-[\d.]+\.dmg$", "ZEsarUX.app"),
    "DOSBox Staging": ("dosbox-staging/dosbox-staging", r"^dosbox-staging-macOS-v[\d.]+\.dmg$", None, "DOSBox Staging.app"),
    "Ruffle": ("ruffle-rs/ruffle", r"-macos-universal\.tar\.gz$", None, "Ruffle.app"),
}


def emu_table():
    return EMU_INSTALL_MAC if MAC else EMU_INSTALL


def mac_asset(name):
    """The download for this Mac: (url, file name, GitHub's checksum or "", size)."""
    import platform
    repo, arm, intel, _ = MAC_DOWNLOADS[name]
    if repo.startswith("https://"):
        return repo, repo.rsplit("/", 1)[1], "", 0
    choices = []
    if platform.machine() == "arm64" and arm:
        choices.append((repo, arm))
    if intel:
        choices.append(intel if isinstance(intel, tuple) else (repo, intel))
    elif arm and platform.machine() != "arm64":
        choices.append((repo, arm))  # universal builds run on both
    for r, pattern in choices:
        try:
            releases = http_json(f"https://api.github.com/repos/{r}/releases?per_page=20", timeout=30)
        except (urllib.error.URLError, ValueError):
            continue
        found = sorted(((rel.get("published_at") or "", a) for rel in releases if not rel.get("draft")
                        for a in rel.get("assets", []) if re.search(pattern, a["name"])), key=lambda x: x[0], reverse=True)
        if found:
            a = found[0][1]
            url = a["browser_download_url"]
            if not url.startswith(f"https://github.com/{r}/releases/download/"):
                raise ValueError(f"{name}'s download isn't on its own project")
            return url, a["name"], str(a.get("digest") or ""), a.get("size") or 0
    raise ValueError(f"{name} has no Mac download right now. Its project page may have one.")


def install_mac_app(name):
    """Download the emulator and put its app in ~/Applications (a program with no app bundle goes in ~/Applications/<name>)."""
    import tempfile
    url, filename, digest, size = mac_asset(name)
    app_pattern = MAC_DOWNLOADS[name][3]
    apps_dir = os.path.expanduser("~/Applications")
    os.makedirs(apps_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ufe-emu-") as staging:
        archive = os.path.join(staging, filename)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as response, open(archive, "wb") as output:
            copy_progress(response, output, size)
        if digest.startswith("sha256:") and file_sha256(archive) != digest[7:].lower():
            raise ValueError(f"The {name} download was damaged. Try again.")
        job_progress("Unpacking")
        unpacked = os.path.join(staging, "unpacked")
        os.makedirs(unpacked)
        low = filename.lower()
        if low.endswith(".dmg"):
            mount = os.path.join(staging, "mount")
            os.makedirs(mount)
            r = subprocess.run(["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mount, archive],
                               input=b"yes\n", capture_output=True, timeout=300)  # "yes": a licence some images show first
            if r.returncode:
                raise ValueError(f"The {name} download couldn't be opened")
            try:
                found = find_mac_program(mount, app_pattern)
                if not found:
                    raise ValueError(f"The {name} download has no app in it")
                target = os.path.join(apps_dir, os.path.basename(found))
                job_progress("Setting up")
                copy_mac_program(found, target)
            finally:
                subprocess.run(["/usr/bin/hdiutil", "detach", mount, "-force"], capture_output=True, timeout=120)
        else:
            cmd = ["/usr/bin/ditto", "-x", "-k", archive, unpacked] if low.endswith(".zip") else ["/usr/bin/tar", "-xf", archive, "-C", unpacked]
            if subprocess.run(cmd, capture_output=True, timeout=600).returncode:
                raise ValueError(f"The {name} download couldn't be unpacked")
            found = find_mac_program(unpacked, app_pattern)
            if not found:
                raise ValueError(f"The {name} download has no app in it")
            target = os.path.join(apps_dir, os.path.basename(found)) if found.endswith(".app") else os.path.join(apps_dir, name, os.path.basename(found))
            job_progress("Setting up")
            copy_mac_program(found, target)
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", target], capture_output=True)
    return target


def find_mac_program(folder, pattern):
    """The .app (or program file) matching the pattern, nearest the top."""
    import fnmatch
    hits = []
    for root, dirs, files in os.walk(folder):
        depth = root[len(folder):].count(os.sep)
        for d in list(dirs):
            if d.endswith(".app"):
                if fnmatch.fnmatch(d.lower(), pattern.lower()):
                    hits.append((depth, os.path.join(root, d)))
                dirs.remove(d)  # never inside an app
        if not pattern.endswith(".app"):
            for f in files:
                p = os.path.join(root, f)
                if fnmatch.fnmatch(f.lower(), pattern.lower()) and os.access(p, os.X_OK) and not f.endswith((".dylib", ".txt", ".md")):
                    hits.append((depth + 1, p))
        if depth >= 3:
            dirs[:] = []
    return min(hits)[1] if hits else None


def copy_mac_program(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if subprocess.run(["/usr/bin/ditto", src, dst], capture_output=True, timeout=600).returncode:  # keeps a bundle whole (signatures, links)
        raise ValueError("The emulator couldn't be copied into Applications")


def main():
    def start():
        scan()
        threading.Thread(target=watch_folders, daemon=True).start()
        if PORT == 8137 and MAC:
            threading.Thread(target=watch_running_mac, daemon=True).start()
            threading.Thread(target=watch_controller_mac, daemon=True).start()
            sync_autostart()
        if PORT == 8137 and WIN:  # only the real helper (a test copy would fire every shortcut twice); XInput is Windows-only
            threading.Thread(target=watch_controller, daemon=True).start()
            threading.Thread(target=watch_steam_button, daemon=True).start()
            threading.Thread(target=watch_running, daemon=True).start()
            threading.Thread(target=watch_emulator_updates, daemon=True).start()  # the app's own emulators, kept up to date
            threading.Thread(target=watch_key_guard, daemon=True).start()  # Steam's desktop keys kept out of games it didn't start
            threading.Thread(target=sync_keep_on_screen, daemon=True).start()  # Settings › General › Keep games on screen
            import hud
            hud.start(DATA, hud_visible, load("hud.json", {}).get("mode") if hud.presentmon(DATA) else "off")  # an extra: off until installed
            sync_autostart()
            note_installed_version()
        warm_details()
    threading.Thread(target=start, daemon=True).start()
    if "--auto-exit" in sys.argv:
        # Started by the launcher: quit once the UI has been closed for two minutes.
        def watchdog():
            while time.time() - LAST_PING[0] < 120:
                time.sleep(10)
            os._exit(0)
        threading.Thread(target=watchdog, daemon=True).start()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Port {PORT} is busy; the frontend helper is probably already running.")
        return
    print(f"Game frontend on http://127.0.0.1:{PORT}")
    threading.Thread(target=watch_updates, daemon=True).start()  # once this copy really has the port
    threading.Thread(target=watch_usage, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
