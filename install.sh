#!/bin/sh
# Install Shoebox on Linux (for you only, no sudo):
#   curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh
# Update: run the same command again (Shoebox's own "u" does that for you). Uninstall:
#   curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh -s -- --uninstall
#
# Linux gets the source of the latest release plus its own Python environment, and uses your system's mpv and
# ffmpeg (a prebuilt bundle clashes with newer system libraries). Everything goes in ~/.local/share/shoebox,
# a "shoebox" command in ~/.local/bin, and Shoebox in your app menu.
# Needs: python3 (3.10 or newer, with venv), and for videos mpv + ffmpeg. It tells you what's missing.
set -eu

REPO="AndrewCromar/shoebox"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/shoebox"
BIN="$HOME/.local/bin"
MENU="$DATA/applications"
ICONS="$DATA/icons/hicolor/scalable/apps"

say() { printf '%s\n' "$*"; }
fetch() {  # url file
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"; else wget -q "$1" -O "$2"; fi
}
hint() {  # what to install, per package manager
    if command -v apt >/dev/null 2>&1; then say "   sudo apt install$1"
    elif command -v pacman >/dev/null 2>&1; then say "   sudo pacman -S$2"
    elif command -v dnf >/dev/null 2>&1; then say "   sudo dnf install$3"
    fi
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$APP" "$BIN/shoebox" "$MENU/shoebox.desktop" "$ICONS/shoebox.svg"
    say "Shoebox is uninstalled. Your photos weren't touched."
    say "Its settings and thumbnails are still in ~/.config/shoebox and ~/.cache/shoebox (delete them if you like)."
    exit 0
fi

PY=""
# 3.12+: on older Pythons PySide6 6.12 slowly drains None's refcount while painting and crashes
for p in python3 python3.14 python3.13 python3.12; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
        PY="$p"; break
    fi
done
if [ -z "$PY" ]; then
    say "Shoebox needs Python 3.12 or newer with venv. Install it, then run this again:"
    hint " python3 python3-venv" " python" " python3"
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [ -n "${SHOEBOX_SOURCE:-}" ]; then  # testing: a local source tarball
    cp "$SHOEBOX_SOURCE" "$TMP/src.tar.gz"; TAG="(local)"
else
    fetch "https://api.github.com/repos/$REPO/releases/latest" "$TMP/latest.json"
    TAG="$(sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' "$TMP/latest.json" | head -1)"
    [ -n "$TAG" ] || { say "Couldn't find the latest Shoebox release (offline?)."; exit 1; }
    say "Downloading Shoebox $TAG…"
    fetch "https://github.com/$REPO/archive/refs/tags/$TAG.tar.gz" "$TMP/src.tar.gz"
fi

mkdir -p "$APP" "$BIN" "$MENU" "$ICONS"
rm -rf "$APP/src.new" && mkdir "$APP/src.new"
tar -xzf "$TMP/src.tar.gz" -C "$APP/src.new" --strip-components=1
rm -rf "$APP/src" && mv "$APP/src.new" "$APP/src"
rm -rf "$APP/_internal" "$APP/Shoebox"  # an older install was a prebuilt bundle; not needed any more

if [ -x "$APP/venv/bin/python" ] && ! "$APP/venv/bin/python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    rm -rf "$APP/venv"  # made with an older Python; rebuild it
fi
if [ ! -x "$APP/venv/bin/python" ]; then
    say "Setting up Python packages (the first time takes a minute)…"
    "$PY" -m venv "$APP/venv"
fi
"$APP/venv/bin/python" -m pip install -q --disable-pip-version-check --upgrade PySide6 pillow pillow-heif python-mpv

cat > "$APP/shoebox" <<LAUNCH
#!/bin/sh
# Start Shoebox (installed by install.sh). MALLOC_ARENA_MAX: memory from big photos goes back to the system.
PYTHONPATH="$APP/src" MALLOC_ARENA_MAX=2 exec "$APP/venv/bin/python" -m shoebox "\$@"
LAUNCH
chmod +x "$APP/shoebox"
ln -sf "$APP/shoebox" "$BIN/shoebox"
rm -f "$ICONS/shoebox.svg" "$MENU/shoebox.desktop"  # an older install may have left links here
cp "$APP/src/assets/shoebox.svg" "$ICONS/shoebox.svg"
cat > "$MENU/shoebox.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Shoebox
GenericName=Photo and video viewer
Comment=Browse photos, videos and audio by year, month and trip
Exec=$APP/shoebox %f
MimeType=image/jpeg;image/png;image/heic;image/heif;image/webp;image/gif;image/bmp;image/tiff;video/mp4;video/quicktime;video/x-matroska;video/webm;video/x-msvideo;video/3gpp;video/mp2t;audio/mpeg;audio/mp4;audio/x-m4a;audio/x-wav;audio/flac;audio/ogg;audio/opus;audio/aac;audio/x-aiff;
Icon=shoebox
Terminal=false
Categories=Graphics;Viewer;
Keywords=photos;videos;pictures;gallery;picasa;media;shoebox;
StartupWMClass=shoebox
DESKTOP
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$MENU" 2>/dev/null || true

say "Shoebox $TAG is installed: find it in your app menu, or run: shoebox"
apt_="" ; pac="" ; dnf=""
if ! command -v ffmpeg >/dev/null 2>&1; then apt_="$apt_ ffmpeg"; pac="$pac ffmpeg"; dnf="$dnf ffmpeg"; fi
if ! "$APP/venv/bin/python" -c 'import mpv' >/dev/null 2>&1; then
    apt_="$apt_ libmpv2"; pac="$pac mpv"; dnf="$dnf mpv-libs"
fi
if [ -n "$apt_" ]; then
    say ""
    say "For videos, also install:"
    hint "$apt_" "$pac" "$dnf"
fi
case ":$PATH:" in *":$BIN:"*) ;; *) say "(To use the shoebox command, add $BIN to your PATH.)";; esac
