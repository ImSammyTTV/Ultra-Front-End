# PyInstaller build for Game Frontend.exe:  python -m PyInstaller "Game Frontend.spec"
import importlib.util
import os

# Windows Graphics Capture for the in-game menu's live backdrop (frontend.py wgc_module): the windows-capture project's
# native module on its own, so its Python wrapper's OpenCV and numpy stay out of the exe.
_wgc = importlib.util.find_spec("windows_capture")
WGC = [(os.path.join(list(_wgc.submodule_search_locations)[0], "windows_capture.pyd"), ".")] if _wgc else []

a = Analysis(
    ["frontend.py"],
    binaries=WGC,
    datas=[("app", "app"), ("metadata", "metadata"), ("THIRD_PARTY_NOTICES.md", "."), ("licenses", "licenses")],
    hiddenimports=["server", "hud", "pystray._win32", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageGrab"],
    # Optional imports the app never uses: PIL -> numpy/defusedxml/olefile, bottle -> jinja2/mako, pywebview's ssl mode ->
    # cryptography, cffi's compiler -> setuptools. Without these the exe holds only what THIRD_PARTY_NOTICES.md lists.
    excludes=[
        "numpy", "cv2", "windows_capture", "threadpoolctl", "psutil", "yaml", "charset_normalizer",
        "cryptography", "bcrypt",
        "jinja2", "markupsafe", "mako", "pygments", "chardet",
        "defusedxml", "olefile",
        "pywintypes", "pythoncom", "win32api", "win32con", "win32pdh", "win32com",
        "setuptools", "pkg_resources", "_distutils_hack", "importlib_resources",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Game Frontend",
    icon="app/icon.ico",
    console=False,
    upx=False,
)
