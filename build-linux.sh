#!/bin/sh
# Builds dist/UltraFrontEnd-linux-<arch>.AppImage (first install and updates: the same file) from this folder.
# Run on Linux:  ./build-linux.sh   (python3 with venv; a Steam Deck build needs an x86-64 machine, a Pi makes an aarch64 one)
# Needs, from the distribution: python3-venv, and the libraries Qt's web engine uses (libnss3, libxkbcommon-x11-0,
# libxcb-cursor0 and friends: Debian/Ubuntu's names), which go into the AppImage with it.
set -e
cd "$(dirname "$0")"
ARCH=$(uname -m)
if [ ! -d .venv-linux ]; then python3 -m venv .venv-linux; fi
. .venv-linux/bin/activate
pip install -q --upgrade pip
pip install -q --upgrade pywebview qtpy PySide6-Essentials PySide6-Addons pyinstaller pillow
python -m PyInstaller --noconfirm --log-level WARN "Game Frontend (Linux).spec"

# Libraries the build needs but this machine lacks never go into the AppImage, and the window then fails on every
# machine without them: stop here and name them (Qt's ARM web engine wants libevent, libminizip, libtiff5 and libwebp6)
MISSING=$(cd "dist/Ultra Front End/_internal" && find . -name "*.so*" -exec sh -c 'LD_LIBRARY_PATH=.:$LD_LIBRARY_PATH ldd "$1" 2>/dev/null' _ {} \; | awk '/not found/ {print $1}' | sort -u | xargs)
if [ -n "$MISSING" ]; then
  echo "Missing system libraries (install them, then build again): $MISSING" >&2
  exit 1
fi

# The AppImage: the PyInstaller folder, a desktop entry and icon, and AppRun to start it
APPDIR=dist/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr"
cp -a "dist/Ultra Front End" "$APPDIR/usr/lib"
cp app/icon.png "$APPDIR/ultra-front-end.png"
cat > "$APPDIR/ultra-front-end.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Ultra Front End
Comment=A controller-first game launcher
Exec=ultra-front-end
Icon=ultra-front-end
Categories=Game;
Terminal=false
EOF
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/ultra-front-end" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# appimagetool (the AppImage project's own), fetched once into .cache/
TOOL=".cache/appimagetool-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
  mkdir -p .cache
  curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
  chmod +x "$TOOL"
fi
OUT="dist/UltraFrontEnd-linux-$ARCH.AppImage"
rm -f "$OUT"
ARCH=$ARCH "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT"
rm -rf "$APPDIR"
echo "Built: $(pwd)/$OUT"
