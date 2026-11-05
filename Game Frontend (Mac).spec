# PyInstaller build for Ultra Front End.app (run build-mac.sh on a Mac; it also makes the .dmg and the update zip)
import re

VERSION = re.search(r'^VERSION = "([^"]+)"', open("server.py", encoding="utf-8").read(), re.M).group(1)

a = Analysis(
    ["frontend.py"],
    datas=[("app", "app"), ("metadata", "metadata"), ("THIRD_PARTY_NOTICES.md", "."), ("licenses", "licenses")],
    hiddenimports=["server", "plat_mac", "psutil", "AppKit", "Quartz", "GameController", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageGrab"],
    excludes=["numpy", "yaml", "cryptography", "bcrypt", "jinja2", "markupsafe", "mako", "pygments", "chardet", "defusedxml", "olefile",
              "setuptools", "pkg_resources", "_distutils_hack", "importlib_resources"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Ultra Front End", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Ultra Front End")
app = BUNDLE(
    coll,
    name="Ultra Front End.app",
    icon="app/icon-mac.png",
    bundle_identifier="com.imsammyttv.ultrafrontend",
    info_plist={
        "CFBundleDisplayName": "Ultra Front End",
        "CFBundleName": "Ultra Front End",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSApplicationCategoryType": "public.app-category.games",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        # asked only when the feature is first used
        "NSAppleEventsUsageDescription": "Ultra Front End uses this to change the volume and to restart or shut down the Mac from the controller.",
    },
)
