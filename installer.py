"""UltraFrontEnd-Setup.exe: installs Ultra Front End for this Windows account.

It goes in %LOCALAPPDATA%\\Programs\\Ultra Front End (the user's own folder, as Discord, Spotify and VS Code install), so
Windows never asks for administrator permission and the app keeps updating itself silently. Adds Start menu and desktop
shortcuts and an entry in Settings > Apps (its uninstall runs the app with --uninstall), offers to bring the settings of
a copy used before, then opens the app. Built by tools/release.py around the release's UltraFrontEnd.exe.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg

NAME = "Ultra Front End"
TEST = bool(os.environ.get("UFE_SETUP_TEST"))  # automated test: every question answered yes, its own Apps entry, the app not opened
KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UltraFrontEnd" + ("-SetupTest" if TEST else "")
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
TARGET = os.path.join(LOCAL, "Programs", NAME)
EXE = os.path.join(TARGET, "UltraFrontEnd.exe")
NOTE = os.path.join(LOCAL, NAME, "settings-folder.txt")  # where the last copy's settings live (server.note_data_folder)
OK_CANCEL, YES_NO, INFO, QUESTION, WARN, IDOK, IDYES = 0x1, 0x4, 0x40, 0x20, 0x30, 1, 6


def ask(text, flags):
    if TEST:
        print("ASK:", text.replace("\n", " ")[:160])
        return IDYES if flags & YES_NO else IDOK
    return ctypes.windll.user32.MessageBoxW(None, text, f"{NAME} Setup", flags | 0x10000 | 0x40000)  # foreground, topmost


def bundled_version():
    try:
        with open(os.path.join(HERE, "version.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def installed_version():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            return str(winreg.QueryValueEx(k, "DisplayVersion")[0]) if os.path.isfile(EXE) else ""
    except OSError:
        return ""


def set_up_in(folder):
    import json
    try:
        with open(os.path.join(folder, "config.json"), encoding="utf-8") as f:
            return bool((json.load(f).get("profile") or {}).get("setupDone"))
    except (OSError, ValueError, AttributeError):
        return False


def shortcut(path, target):
    """A .lnk through Windows' own shortcut object (paths passed as data, base64, so no name can break the script)."""
    import base64
    enc = lambda s: base64.b64encode(s.encode("utf-16-le")).decode()
    dec = lambda s: f"([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{enc(s)}')))"
    script = (f"$l = (New-Object -ComObject WScript.Shell).CreateShortcut({dec(path)}); $l.TargetPath = {dec(target)}; "
              f"$l.WorkingDirectory = {dec(os.path.dirname(target))}; $l.IconLocation = {dec(target + ',0')}; "
              f"$l.Description = {dec(NAME)}; $l.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode()],
                   capture_output=True, timeout=60, creationflags=0x08000000)


def folder_size_kb(folder):
    total = 0
    for root, _, files in os.walk(folder):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total // 1024


def main():
    new, old = bundled_version(), installed_version()
    if old:
        text = (f"{NAME} {old} is installed. Install {new} over it?\n\nYour settings, games and captures stay as they are."
                if old != new else f"{NAME} {new} is already installed. Install it again?\n\nYour settings, games and captures stay as they are.")
    else:
        text = (f"Install {NAME} {new} for {os.environ.get('USERNAME') or 'you'}?\n\nIt goes in your own user folder, so Windows won't ask for "
                f"administrator permission, and it keeps itself up to date. You'll find it in the Start menu and on the desktop.")
    if ask(text, OK_CANCEL | QUESTION) != IDOK:
        return

    os.makedirs(TARGET, exist_ok=True)
    if os.path.isfile(EXE):  # a copy that's running can be renamed, not overwritten: the app removes the old one later
        try:
            os.replace(EXE, os.path.join(TARGET, f"UltraFrontEnd.old-{int(time.time())}.exe"))
        except OSError:
            ask(f"{NAME} couldn't be replaced. Close it (including from the tray), then run Setup again.", WARN)
            return
    shutil.copyfile(os.path.join(HERE, "UltraFrontEnd.exe"), EXE)
    for extra in ("THIRD_PARTY_NOTICES.md",):
        if os.path.isfile(os.path.join(HERE, extra)):
            shutil.copyfile(os.path.join(HERE, extra), os.path.join(TARGET, extra))

    # Settings from a copy used before (a downloaded exe somewhere): copied in, the other copy keeps its own
    data = os.path.join(TARGET, "data")
    try:
        with open(NOTE, encoding="utf-8") as f:
            before = f.read().strip()
    except OSError:
        before = ""
    if (before and not set_up_in(data) and set_up_in(before)
            and os.path.normcase(os.path.abspath(before)) != os.path.normcase(os.path.abspath(data))):
        if ask(f"Bring over the settings from the copy you used before?\n\n{before}\n\nYour games, accounts, artwork, play history "
               "and captures come with them. That copy keeps its own.", YES_NO | QUESTION) == IDYES:
            shutil.copytree(before, data, dirs_exist_ok=True, ignore=shutil.ignore_patterns("webview", "*.part", "*.log"))

    # Start menu, desktop, and Settings > Apps
    programs = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    for place in (programs, desktop):
        if os.path.isdir(place):
            shortcut(os.path.join(place, f"{NAME}.lnk"), EXE)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        for name, value in (("DisplayName", NAME), ("DisplayVersion", new), ("Publisher", "ImSammyTTV"), ("DisplayIcon", f"{EXE},0"),
                            ("InstallLocation", TARGET), ("UninstallString", f'"{EXE}" --uninstall'),
                            ("URLInfoAbout", "https://github.com/ImSammyTTV/Ultra-Front-End")):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", folder_size_kb(TARGET))):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)

    if TEST:
        return print("INSTALLED", EXE)
    subprocess.Popen([EXE], cwd=TARGET, creationflags=0x00000008 | 0x00000200, close_fds=True)  # detached: Setup can leave


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never a Python error box: say what went wrong in words
        ask(f"Setup couldn't finish: {e}", WARN)
