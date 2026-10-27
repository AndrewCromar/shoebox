# Shoebox

<img src="assets/shoebox.svg" width="96" alt="Shoebox icon">

A Picasa-style photo, video and audio viewer. Point it at the folder with your photos and videos (it asks on the
first start; change it any time in Settings). It only looks: it never moves, renames or changes your photos.

## Install

Downloads are on the [latest release](https://github.com/AndrewCromar/shoebox/releases/latest), under **Assets**.

### Windows
1. Download **Shoebox-Setup.exe** and double-click it.
2. Windows may say *"Windows protected your PC"* (it says that for apps that aren't from a big company).
   Click **More info**, then **Run anyway**.
3. Click **Next** a few times, then **Install**. No admin password needed. Tick *desktop shortcut* if you want one.
4. Open **Shoebox** from the Start menu. It asks for your photos folder: click **Choose a folder…** and pick it.

**Updating:** when there's a new version, Shoebox shows a green bar at the top. Press **u** and it updates itself
and opens again. **Uninstalling:** Start → Settings → Apps → **Shoebox** → Uninstall (your photos are never touched).

### Mac
1. Download **Shoebox-macOS.dmg** and double-click it.
2. Drag **Shoebox** onto the **Applications** folder in that window.
3. The first time, open your Applications folder, **right-click** Shoebox → **Open** → **Open**. (A plain
   double-click says it *"can't be opened"*, because it isn't from the App Store.) If it still won't open:
   **System Settings** → **Privacy & Security** → scroll down → **Open Anyway**.
4. It asks for your photos folder: click **Choose a folder…** and pick it.

**Updating:** the green bar's **u** opens the download page; drag the new one into Applications again.
**Uninstalling:** drag Shoebox from Applications to the Trash.

### Linux
Paste this into a terminal (no sudo; it goes in your home folder and your app menu):
```
curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh
```
Run the same line again to update. To uninstall:
```
curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh -s -- --uninstall
```
For videos it needs **mpv** and **ffmpeg** from your package manager; the installer tells you the command if
they're missing.

### From the source (any system)
```
git clone https://github.com/AndrewCromar/shoebox && cd shoebox
python3 -m venv .venv && .venv/bin/pip install PySide6 pillow pillow-heif python-mpv
./shoebox-app
```

## Using it

- **Left:** the library's own layout: `2026/06/Grand Teton National Park/` shows as 2026 > 06 June > the event
  (newest first; events in a month by when their photos were taken). Other top folders (`misc/`, `drew.in.nature/`)
  are groups below the years, misc first. Subfolders sit under their event. Older `2026-06-05 Title` folders work
  too. Picking a year or month shows everything in it. Kdenlive `proxy/` folders are skipped.
- **Right:** thumbnails. Videos show ▶ and their length.
- **Enter / double-click:** full size. ←→ next/previous; videos play inside the window (space pauses, shift ←→ jumps
  5 s, `,` `.` 1 s). Shows when it was taken (EXIF or the video's creation time).
- **Keys** (the bar at the bottom changes with where you are: folders, photos or viewing): ↑↓ folders, → or Enter to the
  thumbnails, Esc back (Esc in the folders quits, so Esc Esc Esc gets you all the way out). `+` `−` or Ctrl+wheel change the thumbnail size.
  `o` opens the file in its usual app, `d` shows it in the file manager (Dolphin, Explorer, Finder), `f` full screen, F5 reloads,
  `q` quits, `/` or Ctrl+F searches the folder names (Enter keeps the filter, Esc clears it). The outline on a thumbnail only shows while you're in the photos.

**Settings (s):** pick the media folder (there's no default: the first start asks; remembered in `~/.config/shoebox/settings.json`) or
clear the thumbnails. It also remembers the last folder you looked at and opens there.

Read-only: it never moves, renames or edits anything in the library. Thumbnails are cached in your user cache folder
(`~/.cache/shoebox`, `%LOCALAPPDATA%\Shoebox`, `~/Library/Caches/Shoebox`; Settings can clear them). HEIC photos work through pillow-heif.

| file | what |
|---|---|
| `shoebox/library.py` | scans the folders, dates from names |
| `shoebox/thumbs.py` | thumbnail cache, background workers (Pillow, ffmpeg) |
| `shoebox/app.py` | the window: folder tree, grid, viewer (mpv) |


Linux menu entry (KDE menu, KRunner):
```
cp assets/shoebox.desktop ~/.local/share/applications/
ln -s "$PWD/assets/shoebox.svg" ~/.local/share/icons/hicolor/scalable/apps/shoebox.svg
```

## Building the Windows and Mac apps

GitHub builds them (`.github/workflows/build.yml`) on every push to `main` or `dev`, runs the app's
self-test on each (`Shoebox --selftest report.txt`: thumbnails, video player, window), and keeps the zips under the
run's **Artifacts**. On Windows it also tests the installer: install, run the installed app's self-test,
uninstall, check nothing's left. Linux tests `install.sh` the same way. Pushing a tag that matches the version in
`shoebox/__init__.py` (e.g. `v1.0.0`) makes a release with all the downloads, which is what the Install links
above (and the in-app updater) use. Locally: `python packaging/build.py` (see the file for the tools it bundles).
