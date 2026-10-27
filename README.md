# gallery

A Picasa-style photo, video and audio viewer for `~/storage/Dropbox/Kids/Andrew/media/_photos and videos/`.

```
./gallery-app                # or "Gallery" in the KDE menu
./gallery-app /some/folder   # another library
```

- **Left:** folders by year, then month (from names like `2026-06-05 Teton National Park`). Subfolders ("nick phone")
  sit under their folder, and folders without a date ("2007-2023") are at the bottom. Picking a year or month shows
  everything in it. Kdenlive `proxy/` folders are skipped.
- **Right:** thumbnails. Videos show ▶ and their length.
- **Enter / double-click:** full size. ←→ next/previous; videos play inside the window (space pauses, shift ←→ jumps
  5 s, `,` `.` 1 s). Shows when it was taken (EXIF or the video's creation time).
- **Keys** (the bar at the bottom changes with where you are: folders, photos or viewing): ↑↓ folders, → or Enter to the
  thumbnails, Esc back. `+` `−` or Ctrl+wheel change the thumbnail size.
  `o` opens the file in its usual app, `d` shows it in the file manager (Dolphin), `f` full screen, F5 reloads,
  `q` quits. The outline on a thumbnail only shows while you're in the photos.

Read-only: it never moves, renames or edits anything in the library. Thumbnails are cached in `~/.cache/gallery`
(delete it any time). HEIC photos work through pillow-heif.

| file | what |
|---|---|
| `gallery/library.py` | scans the folders, dates from names |
| `gallery/thumbs.py` | thumbnail cache, background workers (Pillow, ffmpeg) |
| `gallery/app.py` | the window: folder tree, grid, viewer (mpv) |

Setup: `python3 -m venv .venv && .venv/bin/pip install PySide6 pillow pillow-heif python-mpv` (needs mpv and ffmpeg).
