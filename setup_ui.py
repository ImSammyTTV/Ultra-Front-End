"""Setup and Uninstall, in a window of Ultra Front End's own (app/setup.html).

UltraFrontEnd-Setup.exe is the app itself under another name: started under that name (or with --setup) it installs a
copy of itself into C:\\Ultra-Front-End\\App, beside the ROMs and Emulators folders (a folder users may make without an
administrator prompt, so the copy keeps updating itself; %LOCALAPPDATA%\\Programs\\Ultra Front End on a PC that won't allow
it, which is also where Setup installed before 1.2.5: an install there is moved over, settings and all), adds Start menu and desktop shortcuts and an entry in
Settings > Apps, then offers to open it. That entry runs the installed copy with --uninstall, which shows the same window.

Runs before the helper (server.py) is imported, so Setup never makes a data folder beside the download. Settings aren't
copied: the installed app finds the ones the copy used before where they are (server.data_folder).
"""
import base64
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import winreg

NAME = "Ultra Front End"
KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UltraFrontEnd"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LOCAL = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
OLD_TARGET = os.path.join(LOCAL, "Programs", NAME)  # where Setup installed before 1.2.5
HOME = os.path.join((os.environ.get("SystemDrive") or "C:") + os.sep, "Ultra-Front-End")  # App, ROMs and Emulators, side by side


def target():
    """C:\\Ultra-Front-End\\App, beside the ROMs and Emulators folders. A PC that doesn't let its users make folders on C:
    (some school or work PCs) gets the old place in the user's own app data instead. A test can install elsewhere."""
    if os.environ.get("UFE_SETUP_TARGET"):
        return os.environ["UFE_SETUP_TARGET"]
    app = os.path.join(HOME, "App")
    try:
        os.makedirs(app, exist_ok=True)
        probe = os.path.join(app, f".setup-{os.getpid()}")
        open(probe, "w").close()
        os.remove(probe)
        return app
    except OSError:
        return OLD_TARGET


TARGET = OLD_TARGET  # set by main(): worked out only when Setup runs (this module is loaded at every start, to check for that)
NOTE = os.path.join(LOCAL, NAME, "settings-folder.txt")  # where the last copy's settings live (server.note_data_folder)
BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BUNDLE, "app")
PROGRAMS = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
NO_WINDOW = 0x08000000


def is_setup():
    """Started as the installer: named UltraFrontEnd-Setup*.exe (a browser may add " (1)"), or with --setup."""
    name = os.path.basename(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).lower()
    return "--setup" in sys.argv or name.startswith("ultrafrontend-setup")


def version():
    """VERSION from server.py, read from its code without running it (running it would set up a data folder)."""
    import dis
    import importlib.util
    try:
        code = importlib.util.find_spec("server").loader.get_code("server")
        last = None
        for ins in dis.get_instructions(code):
            if ins.opname == "LOAD_CONST":
                last = ins.argval
            elif ins.opname == "STORE_NAME" and ins.argval == "VERSION" and isinstance(last, str):
                return last
    except Exception:
        pass
    return ""


def installed_version():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            v = str(winreg.QueryValueEx(k, "DisplayVersion")[0])
        return v if any(os.path.isfile(os.path.join(t, "UltraFrontEnd.exe")) for t in (TARGET, OLD_TARGET)) else ""
    except OSError:
        return ""


def old_install():
    """An install in the old place (AppData\\Local\\Programs), when Setup now installs somewhere else: moved over, settings and all."""
    same = os.path.normcase(os.path.abspath(OLD_TARGET)) == os.path.normcase(os.path.abspath(TARGET))
    return "" if same or not os.path.isfile(os.path.join(OLD_TARGET, "UltraFrontEnd.exe")) else OLD_TARGET


def stop_copies(folder):
    """Ends Ultra Front End running from this folder (the window and the helper in the tray), and no other copy."""
    enc = base64.b64encode(folder.rstrip("\\").encode("utf-16-le")).decode()
    script = (f"$d = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{enc}')) + '\\'; "
              f"Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -ne {os.getpid()} -and $_.Path -and "
              f"$_.Path.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) }} | Stop-Process -Force")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode()],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW)


def shortcut(path, target):
    """A .lnk through Windows' own shortcut object (paths passed as data, base64, so no name can break the script)."""
    enc = lambda s: base64.b64encode(s.encode("utf-16-le")).decode()
    dec = lambda s: f"([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{enc(s)}')))"
    script = (f"$l = (New-Object -ComObject WScript.Shell).CreateShortcut({dec(path)}); $l.TargetPath = {dec(target)}; "
              f"$l.WorkingDirectory = {dec(os.path.dirname(target))}; $l.IconLocation = {dec(target + ',0')}; "
              f"$l.Description = {dec(NAME)}; $l.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode()],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW)
    if not os.path.isfile(path):
        raise OSError(f"Windows didn't make the shortcut {path}")


def desktop():
    """The desktop folder, wherever it is (OneDrive can move it)."""
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


class Work:
    """What the page shows while Setup or Uninstall runs."""
    def __init__(self):
        self.progress, self.step, self.error, self.done, self.kept = 0.0, "", "", False, True


class Api:
    def __init__(self, mode):
        self.mode, self.work, self.window = mode, Work(), None

    def info(self):
        here = os.path.dirname(sys.executable) if self.mode == "uninstall" and getattr(sys, "frozen", False) else TARGET
        return {"mode": self.mode, "version": version(), "installed": installed_version(), "target": here,
                "user": os.environ.get("USERNAME") or "you"}

    def state(self):
        w = self.work
        return {"progress": w.progress, "step": w.step, "error": w.error, "done": w.done, "kept": w.kept}

    def install(self, want_desktop):
        self.work = Work()
        threading.Thread(target=self._run, args=[self._install, bool(want_desktop)], daemon=True).start()

    def uninstall(self, wipe):
        self.work = Work()
        threading.Thread(target=self._run, args=[self._uninstall, bool(wipe)], daemon=True).start()

    def _run(self, job, arg):
        try:
            job(arg)
            self.work.progress, self.work.done = 1.0, True
        except Exception as e:  # said in words on the page, with Try again
            self.work.error = f"That didn't work: {e}"

    def _say(self, step, progress):
        self.work.step, self.work.progress = step, progress

    def _install(self, want_desktop):
        exe = os.path.join(TARGET, "UltraFrontEnd.exe")
        self._say("Closing Ultra Front End if it's open…", 0.04)
        stop_copies(TARGET)
        os.makedirs(TARGET, exist_ok=True)
        old = old_install()
        if old:  # installed in the old place before: its settings come too, and the old copy goes
            self._say("Moving your settings to the new folder…", 0.06)
            stop_copies(old)
            self._move_settings(os.path.join(old, "data"), os.path.join(TARGET, "data"))
        if os.path.isfile(exe):  # a copy that's still closing can be renamed, not overwritten: the app removes the old one later
            try:
                os.remove(exe)
            except OSError:
                os.replace(exe, os.path.join(TARGET, f"UltraFrontEnd.old-{int(time.time())}.exe"))
        source = sys.executable if getattr(sys, "frozen", False) else None
        if not source:
            raise OSError("Setup only installs from the built UltraFrontEnd-Setup.exe")
        total, done = os.path.getsize(source), 0
        with open(source, "rb") as src, open(exe + ".part", "wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
                done += len(chunk)
                self._say("Copying the app…", 0.08 + 0.62 * done / total)
        os.replace(exe + ".part", exe)
        notices = os.path.join(BUNDLE, "THIRD_PARTY_NOTICES.md")
        if os.path.isfile(notices):
            shutil.copyfile(notices, os.path.join(TARGET, "THIRD_PARTY_NOTICES.md"))
        self._say("Adding it to the Start menu…", 0.74)
        os.makedirs(PROGRAMS, exist_ok=True)
        shortcut(os.path.join(PROGRAMS, f"{NAME}.lnk"), exe)
        place = os.path.join(desktop(), f"{NAME}.lnk")
        if want_desktop:
            self._say("Putting a shortcut on the desktop…", 0.84)
            shortcut(place, exe)
        elif os.path.isfile(place):
            os.remove(place)
        self._say("Adding it to Settings › Apps…", 0.94)
        size = sum(os.path.getsize(os.path.join(TARGET, f)) for f in os.listdir(TARGET) if os.path.isfile(os.path.join(TARGET, f))) // 1024
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            for name, value in (("DisplayName", NAME), ("DisplayVersion", version()), ("Publisher", "ImSammyTTV"),
                                ("DisplayIcon", f"{exe},0"), ("InstallLocation", TARGET), ("UninstallString", f'"{exe}" --uninstall'),
                                ("QuietUninstallString", f'"{exe}" --uninstall'), ("URLInfoAbout", "https://github.com/ImSammyTTV/Ultra-Front-End")):
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
            for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size)):
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
        if old:
            self._say("Removing the old copy…", 0.97)
            shutil.rmtree(old, ignore_errors=True)  # its settings are in the new folder now
        self._say("Done", 1.0)

    def _move_settings(self, src, dst):
        """The old install's data folder into the new one: a rename on the same drive. One that's already set up there is
        kept, and the note of where the settings are points at the new place."""
        def set_up(folder):
            try:
                import json
                with open(os.path.join(folder, "config.json"), encoding="utf-8") as f:
                    return bool((json.load(f).get("profile") or {}).get("setupDone"))
            except (OSError, ValueError, AttributeError):
                return False
        if not os.path.isdir(src) or set_up(dst):
            return
        if os.path.isdir(dst):  # an empty start made there earlier: set aside, not deleted
            os.replace(dst, f"{dst}.before-{int(time.time())}")
        shutil.move(src, dst)
        try:
            with open(NOTE, encoding="utf-8") as f:
                noted = f.read().strip()
        except OSError:
            noted = ""
        if not noted or os.path.normcase(os.path.abspath(noted)) == os.path.normcase(os.path.abspath(src)):
            os.makedirs(os.path.dirname(NOTE), exist_ok=True)
            with open(NOTE, "w", encoding="utf-8") as f:
                f.write(dst)

    def _uninstall(self, wipe):
        folder = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else TARGET
        self._say("Closing Ultra Front End…", 0.15)
        stop_copies(folder)
        self._say("Removing shortcuts…", 0.4)
        for lnk in (os.path.join(PROGRAMS, f"{NAME}.lnk"), os.path.join(desktop(), f"{NAME}.lnk")):
            try:
                os.remove(lnk)
            except OSError:
                pass
        self._say("Removing it from Settings › Apps…", 0.6)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                for name in (NAME, "Game Frontend"):
                    try:
                        winreg.DeleteValue(k, name)
                    except OSError:
                        pass
        except OSError:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
        except OSError:
            pass
        if wipe:
            self._say("Deleting your settings…", 0.75)
            try:
                with open(NOTE, encoding="utf-8") as f:
                    if os.path.normcase(os.path.abspath(f.read().strip())) == os.path.normcase(os.path.abspath(os.path.join(folder, "data"))):
                        os.remove(NOTE)
            except OSError:
                pass
        self.work.kept = not wipe
        self.removal = (folder, wipe)  # the folder itself goes once this program has left (a running exe can't be deleted)
        self._say("Done", 1.0)

    def open_app(self):
        exe = os.path.join(TARGET, "UltraFrontEnd.exe")
        subprocess.Popen([exe], cwd=TARGET, creationflags=0x00000008 | 0x00000200, close_fds=True)  # detached
        self.close()

    def close(self):
        removal = getattr(self, "removal", None)
        if removal:
            folder, wipe = removal
            enc = lambda text: base64.b64encode(text.encode("utf-16-le")).decode()
            script = (f"Start-Sleep -Seconds 2; $f = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{enc(folder)}')); "
                      + ("Remove-Item -LiteralPath $f -Recurse -Force -ErrorAction SilentlyContinue" if wipe
                         else "Get-ChildItem -LiteralPath $f | Where-Object { $_.Name -ne 'data' } | "
                              "ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }")
                      # C:\Ultra-Front-End itself goes only if nothing is left in it (ROMs and emulators stay where they are)
                      + "; $p = Split-Path -LiteralPath $f; if ((Split-Path -Leaf $p) -eq 'Ultra-Front-End' -and "
                        "-not (Get-ChildItem -LiteralPath $p -Force -ErrorAction SilentlyContinue)) { Remove-Item -LiteralPath $p -ErrorAction SilentlyContinue }")
            subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc(script)],
                             creationflags=0x00000200 | NO_WINDOW, close_fds=True)
        if self.window:
            self.window.destroy()


def round_corners(window):
    """Windows 11's rounded corners and shadow on the borderless window."""
    try:
        hwnd = window.native.Handle.ToInt32()
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


def main(mode="install"):
    global TARGET
    import webview
    if mode == "install":
        TARGET = target()
    elif getattr(sys, "frozen", False):
        TARGET = os.path.dirname(sys.executable)  # Uninstall removes the copy it was started from
    api = Api(mode)
    with open(os.path.join(APP, "setup.html"), encoding="utf-8") as f:
        page = f.read().replace('src="icon.png"', 'src="data:image/png;base64,'
                                + base64.b64encode(open(os.path.join(APP, "icon.png"), "rb").read()).decode() + '"')
    title = f"{NAME} {'Uninstall' if mode == 'uninstall' else 'Setup'}"
    api.window = webview.create_window(title, html=page, js_api=api, width=820, height=540, resizable=False, frameless=True,
                                       easy_drag=False, background_color="#070c1a")
    api.window.events.shown += lambda: round_corners(api.window)
    webview.start(private_mode=True)
