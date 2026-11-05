# PyInstaller build for UltraFrontEnd-Setup.exe (tools/release.py builds it around dist/release/UltraFrontEnd.exe).
# The app, the version it is and the notices travel inside; nothing else from Python's library is needed.
import os

RELEASE = os.path.join("dist", "release")
a = Analysis(
    ["installer.py"],
    datas=[(os.path.join(RELEASE, "UltraFrontEnd.exe"), "."), (os.path.join(RELEASE, "version.txt"), "."), ("THIRD_PARTY_NOTICES.md", ".")],
    excludes=["tkinter", "pywebview", "webview", "PIL", "numpy"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="UltraFrontEnd-Setup", icon="app/icon.ico", console=False, upx=False)
