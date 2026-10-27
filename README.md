# Shoebox

<img src="assets/shoebox.svg" width="96" alt="Shoebox icon">

A Picasa-style photo, video and audio viewer for `~/storage/Dropbox/Kids/Andrew/media/`.

```
./shoebox-app                # or "Shoebox" in the KDE menu / KRunner
./shoebox-app /some/folder   # another library
```

- **Left:** the library's own layout: `2026/06/Grand Teton National Park/` shows as 2026 > 06 June > the event
  (newest first; events in a month by when their photos were taken). Other top folders (`misc/`, `drew.in.nature/`)
  are groups below the years, misc first. Subfolders sit under their event. Older `2026-06-05 Title` folders work
  too. Picking a year or month shows everything in it. Kdenlive `proxy/` folders are skipped.
- **Right:** thumbnails. Videos show ▶ and their length.
- **Enter / double-click:** full size. ←→ next/previous; videos play inside the window (space pauses, shift ←→ jumps
  5 s, `,` `.` 1 s). Shows when it was taken (EXIF or the video's creation time).
- **Keys** (the bar at the bottom changes with where you are: folders, photos or viewing): ↑↓ folders, → or Enter to the
  thumbnails, Esc back. `+` `−` or Ctrl+wheel change the thumbnail size.
  `o` opens the file in its usual app, `d` shows it in the file manager (Dolphin), `f` full screen, F5 reloads,
  `q` quits, `/` or Ctrl+F searches the folder names (Enter keeps the filter, Esc clears it). The outline on a thumbnail only shows while you're in the photos.

**Settings (s):** pick the media folder (if it moves; remembered in `~/.config/shoebox/settings.json`) or
clear the thumbnails.

Read-only: it never moves, renames or edits anything in the library. Thumbnails are cached in `~/.cache/shoebox`
(delete it any time). HEIC photos work through pillow-heif.

| file | what |
|---|---|
| `shoebox/library.py` | scans the folders, dates from names |
| `shoebox/thumbs.py` | thumbnail cache, background workers (Pillow, ffmpeg) |
| `shoebox/app.py` | the window: folder tree, grid, viewer (mpv) |

Setup: `python3 -m venv .venv && .venv/bin/pip install PySide6 pillow pillow-heif python-mpv` (needs mpv and ffmpeg).

Install the menu entry (KDE menu, KRunner):
```
cp assets/shoebox.desktop ~/.local/share/applications/
ln -s "$PWD/assets/shoebox.svg" ~/.local/share/icons/hicolor/scalable/apps/shoebox.svg
```
