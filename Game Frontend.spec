# PyInstaller build for Game Frontend.exe:  python -m PyInstaller "Game Frontend.spec"
a = Analysis(
    ["frontend.py"],
    datas=[("app", "app"), ("metadata", "metadata"), ("THIRD_PARTY_NOTICES.md", "."), ("licenses", "licenses")],
    hiddenimports=["server", "hud", "pystray._win32", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageGrab"],
    # Optional imports the app never uses: PIL -> numpy/defusedxml/olefile, bottle -> jinja2/mako, pywebview's ssl mode ->
    # cryptography, cffi's compiler -> setuptools. Without these the exe holds only what THIRD_PARTY_NOTICES.md lists.
    excludes=[
        "numpy", "threadpoolctl", "psutil", "yaml", "charset_normalizer",
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
