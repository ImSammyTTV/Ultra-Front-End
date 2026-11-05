#!/bin/zsh
# Builds "Ultra Front End.app", "UltraFrontEnd.dmg" (first install) and "UltraFrontEnd-mac.zip" (updates) in dist/.
# Run on a Mac:  ./build-mac.sh   (uses uv's Python 3.12 if uv is installed, otherwise python3)
set -e
cd "$(dirname "$0")"
UV="$HOME/.local/bin/uv"
if [ ! -d .venv-mac ]; then
  if [ -x "$UV" ]; then "$UV" venv --python 3.12 .venv-mac; else python3 -m venv .venv-mac; fi
fi
. .venv-mac/bin/activate
if [ -x "$UV" ]; then INSTALL=("$UV" pip install -q); else INSTALL=(pip install -q); fi
"${INSTALL[@]}" --upgrade pywebview pyinstaller pillow psutil pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-GameController dmgbuild
python -m PyInstaller --noconfirm --log-level WARN "Game Frontend (Mac).spec"

# unsigned: ad-hoc signed so Apple Silicon will run it (people allow it once in System Settings > Privacy & Security)
codesign --force --deep --sign - "dist/Ultra Front End.app"

rm -rf dist/dmg-bg dist/UltraFrontEnd.dmg dist/UltraFrontEnd-mac.zip
# the install window: background with an arrow to Applications, icons placed on it (dmg-settings.py)
python tools/make_dmg_background.py dist/dmg-bg
dmgbuild -s dmg-settings.py -D app="dist/Ultra Front End.app" -D bg=dist/dmg-bg "Ultra Front End" dist/UltraFrontEnd.dmg
rm -rf dist/dmg-bg
(cd dist && ditto -c -k --keepParent "Ultra Front End.app" UltraFrontEnd-mac.zip)
echo "Built: $(pwd)/dist/UltraFrontEnd.dmg and dist/UltraFrontEnd-mac.zip"
