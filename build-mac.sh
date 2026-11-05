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
"${INSTALL[@]}" --upgrade pywebview pyinstaller pillow psutil pyobjc-framework-Quartz pyobjc-framework-Cocoa pyobjc-framework-GameController
python -m PyInstaller --noconfirm --log-level WARN "Game Frontend (Mac).spec"

# unsigned: ad-hoc signed so Apple Silicon will run it (people allow it once in System Settings > Privacy & Security)
codesign --force --deep --sign - "dist/Ultra Front End.app"

rm -rf dist/dmg dist/UltraFrontEnd.dmg dist/UltraFrontEnd-mac.zip
mkdir -p dist/dmg
cp -R "dist/Ultra Front End.app" dist/dmg/
ln -s /Applications dist/dmg/Applications
hdiutil create -quiet -volname "Ultra Front End" -srcfolder dist/dmg -ov -format UDZO dist/UltraFrontEnd.dmg
rm -rf dist/dmg
(cd dist && ditto -c -k --keepParent "Ultra Front End.app" UltraFrontEnd-mac.zip)
echo "Built: $(pwd)/dist/UltraFrontEnd.dmg and dist/UltraFrontEnd-mac.zip"
