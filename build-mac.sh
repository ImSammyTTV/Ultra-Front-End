#!/bin/zsh
# Builds "Game Frontend.app" and "Game Frontend.dmg" in dist/. Run on a Mac:  ./build-mac.sh
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-$(command -v /opt/homebrew/bin/python3 || command -v python3)}
[ -d .venv-mac ] || "$PY" -m venv .venv-mac
. .venv-mac/bin/activate
pip install -q --upgrade pywebview pyinstaller pillow
python -m PyInstaller --noconfirm --log-level WARN "Game Frontend (Mac).spec"

# disk image: the app plus an Applications shortcut to drag it onto
rm -rf dist/dmg "dist/Game Frontend.dmg"
mkdir -p dist/dmg
cp -R "dist/Game Frontend.app" dist/dmg/
ln -s /Applications dist/dmg/Applications
hdiutil create -quiet -volname "Game Frontend" -srcfolder dist/dmg -ov -format UDZO "dist/Game Frontend.dmg"
rm -rf dist/dmg
echo "Built: $(pwd)/dist/Game Frontend.dmg"
