# The Mac installer window (UltraFrontEnd.dmg), for dmgbuild. build-mac.sh runs:
#   dmgbuild -s dmg-settings.py -D app="dist/Ultra Front End.app" -D bg=<folder with background.png> "Ultra Front End" dist/UltraFrontEnd.dmg
# Icon places match tools/make_dmg_background.py (the arrow and the name strips are drawn there).
import os
import plistlib

app = defines["app"]  # noqa: F821 (dmgbuild provides defines)
name = os.path.basename(app)

format = "UDZO"
filesystem = "HFS+"
files = [app]
symlinks = {"Applications": "/Applications"}
with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
    _icon = plistlib.load(f).get("CFBundleIconFile", "")
icon = os.path.join(app, "Contents", "Resources", _icon if _icon.endswith(".icns") else _icon + ".icns")  # the disk's own icon

background = os.path.join(defines["bg"], "background.png")  # noqa: F821 (background@2x.png beside it for Retina)
window_rect = ((200, 160), (640, 420))
default_view = "icon-view"
show_status_bar = show_tab_view = show_toolbar = show_pathbar = show_sidebar = False
show_icon_preview = False
icon_size = 128
text_size = 13
arrange_by = None
icon_locations = {name: (170, 190), "Applications": (470, 190)}
