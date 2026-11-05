"""Setup and Uninstall, in a window of Ultra Front End's own (app/setup.html).

UltraFrontEnd-Setup.exe is the app itself under another name: started under that name (or with --setup) it installs a
copy of itself into %LOCALAPPDATA%\\Programs\\Ultra Front End for this Windows account (so Windows never asks for
administrator permission and the copy keeps updating itself), adds Start menu and desktop shortcuts and an entry in
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
TARGET = os.environ.get("UFE_SETUP_TARGET") or os.path.join(LOCAL, "Programs", NAME)  # (a test can install elsewhere)
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
        return v if os.path.isfile(os.path.join(TARGET, "UltraFrontEnd.exe")) else ""
    except OSError:
        return ""


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
        self._say("Done", 1.0)

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
                              "ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }"))
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
    import webview
    api = Api(mode)
    with open(os.path.join(APP, "setup.html"), encoding="utf-8") as f:
        page = f.read().replace('src="icon.png"', 'src="data:image/png;base64,'
                                + base64.b64encode(open(os.path.join(APP, "icon.png"), "rb").read()).decode() + '"')
    title = f"{NAME} {'Uninstall' if mode == 'uninstall' else 'Setup'}"
    api.window = webview.create_window(title, html=page, js_api=api, width=820, height=540, resizable=False, frameless=True,
                                       easy_drag=False, background_color="#070c1a")
    api.window.events.shown += lambda: round_corners(api.window)
    webview.start(private_mode=True)
