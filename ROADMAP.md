# Shoebox roadmap

Branches: `main` is the last version Andrew said works; new work goes on `dev` and is merged into main when he says.

## Next
1. **Works on Windows and Mac** (Andrew, 2026-10-27; his dad may use it). Qt already runs everywhere. To change:
   - `d` (show in file manager): Explorer `/select,` on Windows, `open -R` on Mac (today it's a Linux D-Bus call).
   - `malloc_trim` / `MALLOC_ARENA_MAX`: Linux only; skip elsewhere.
   - The ♪ tile font comes from `fc-match`; bundle a font or use Qt to draw it.
   - Bundle libmpv and ffmpeg/ffprobe, and package one app per system (PyInstaller: a Windows .exe, a Mac .app).
   - Andrew can't test those systems here; his dad is the Windows tester.

## Later
2. **Ingest window + duplicates** (Andrew, 2026-10-27). Not a special folder: a window. Say friends upload
   their Teton photos to a Dropbox folder; in Shoebox he opens Ingest, picks that folder and the event to merge
   into (e.g. `media/2026/06/Grand Teton National Park`), and Shoebox does its best: it matches what's already
   there (same photo at another size, re-encoded, renamed; for videos a few frames and the length) and shows the
   new ones, and the likely duplicates side by side. He accepts photos in (they're moved into the event) or
   skips them. Every move goes in a log file (not shown in the app) so it can be undone, or Claude can fix
   things from it. Nothing is deleted; anything thrown away goes to the trash.
   Matching: an image fingerprint (perceptual hash) plus the date taken.

## Done
- Year > month > event tree, misc and other groups below the years, search, settings (media folder, no default),
  reopens where you left off.
- Thumbnails (photos, HEIC, videos, audio) cached in `~/.cache/shoebox`; viewer for photos, videos and audio.
- Fast flipping and scrolling (dev, 2026-10-27): skip pictures you've passed, on-screen thumbnails first.
