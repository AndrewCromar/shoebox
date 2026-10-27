#!/bin/sh
# Install Shoebox on Linux (for you only, no sudo):
#   curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh
# Update: run the same command again. Uninstall:
#   curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh -s -- --uninstall
#
# Puts the app in ~/.local/share/shoebox, a "shoebox" command in ~/.local/bin, and Shoebox in your app menu.
# Needs mpv (for videos) and ffmpeg (for video thumbnails) from your package manager; it tells you if they're missing.
set -eu

REPO="AndrewCromar/shoebox"
APP="${XDG_DATA_HOME:-$HOME/.local/share}/shoebox"
BIN="$HOME/.local/bin"
MENU="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

say() { printf '%s\n' "$*"; }

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$APP" "$BIN/shoebox" "$MENU/shoebox.desktop" "$ICONS/shoebox.svg"
    say "Shoebox is uninstalled. Your photos weren't touched."
    say "Its settings and thumbnails are still in ~/.config/shoebox and ~/.cache/shoebox (delete them if you like)."
    exit 0
fi

say "Downloading Shoebox…"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/$REPO/releases/latest/download/Shoebox-Linux.tar.gz"
if [ -n "${SHOEBOX_TARBALL:-}" ]; then cp "$SHOEBOX_TARBALL" "$TMP/shoebox.tar.gz"  # testing a local build
elif command -v curl >/dev/null 2>&1; then curl -fL --progress-bar "$URL" -o "$TMP/shoebox.tar.gz"
else wget -q --show-progress "$URL" -O "$TMP/shoebox.tar.gz"; fi

rm -rf "$APP"
mkdir -p "$APP" "$BIN" "$MENU" "$ICONS"
tar -xzf "$TMP/shoebox.tar.gz" -C "$APP" --strip-components=1
ln -sf "$APP/Shoebox" "$BIN/shoebox"
rm -f "$ICONS/shoebox.svg" "$MENU/shoebox.desktop"  # an older install may have left links here
cp "$APP/_internal/assets/shoebox.svg" "$ICONS/shoebox.svg"
cat > "$MENU/shoebox.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Shoebox
GenericName=Photo and video viewer
Comment=Browse photos, videos and audio by year, month and trip
Exec=$APP/Shoebox
Icon=shoebox
Terminal=false
Categories=Graphics;Viewer;
Keywords=photos;videos;pictures;gallery;picasa;media;shoebox;
StartupWMClass=shoebox
DESKTOP
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$MENU" 2>/dev/null || true

say "Shoebox is installed: find it in your app menu, or run: shoebox"
missing=""
command -v ffmpeg >/dev/null 2>&1 || missing="$missing ffmpeg"
ldconfig -p 2>/dev/null | grep -q libmpv || missing="$missing mpv"
if [ -n "$missing" ]; then
    say ""
    say "For videos, also install:$missing"
    if command -v apt >/dev/null 2>&1; then say "   sudo apt install$missing" | sed 's/ mpv/ libmpv2/'
    elif command -v pacman >/dev/null 2>&1; then say "   sudo pacman -S$missing"
    elif command -v dnf >/dev/null 2>&1; then say "   sudo dnf install$missing" | sed 's/ mpv/ mpv-libs/'
    fi
fi
case ":$PATH:" in *":$BIN:"*) ;; *) say "(To use the shoebox command, add $BIN to your PATH.)";; esac
