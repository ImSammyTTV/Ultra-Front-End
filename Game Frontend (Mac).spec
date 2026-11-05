# PyInstaller build for Game Frontend.app (run build-mac.sh on a Mac; it also makes the .dmg)
a = Analysis(
    ["frontend.py"],
    datas=[("app", "app"), ("metadata", "metadata")],
    hiddenimports=["server"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Game Frontend", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Game Frontend")
app = BUNDLE(
    coll,
    name="Game Frontend.app",
    icon="app/icon-mac.png",
    bundle_identifier="com.imsammyttv.gamefrontend",
    info_plist={
        "CFBundleDisplayName": "Game Frontend",
        "CFBundleShortVersionString": "1.0",
        "LSApplicationCategoryType": "public.app-category.games",
        "NSHighResolutionCapable": True,
    },
)
