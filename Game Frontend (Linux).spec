# PyInstaller build for Linux (run build-linux.sh: it also wraps the result into UltraFrontEnd-linux-<arch>.AppImage).
# The window is pywebview on Qt's web engine (PySide6, LGPL), carried inside: SteamOS has no WebKitGTK to rely on.
a = Analysis(
    ["frontend.py"],
    datas=[("app", "app"), ("metadata", "metadata"), ("THIRD_PARTY_NOTICES.md", "."), ("licenses", "licenses")],
    hiddenimports=["server", "plat_linux", "webview.platforms.qt", "qtpy", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
                   "PySide6.QtWebChannel", "PySide6.QtNetwork", "PySide6.QtPrintSupport", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"],
    excludes=["numpy", "yaml", "cryptography", "bcrypt", "jinja2", "markupsafe", "mako", "pygments", "chardet", "defusedxml", "olefile",
              "setuptools", "pkg_resources", "_distutils_hack", "importlib_resources", "tkinter", "gi", "PyQt5", "PyQt6", "PySide2",
              "webview.platforms.gtk", "webview.platforms.cef", "plat_mac"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ultra-front-end", console=False, strip=True)
coll = COLLECT(exe, a.binaries, a.datas, name="Ultra Front End", strip=True)
