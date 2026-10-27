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
2. **Ingest** (Andrew, 2026-10-27): bring photos from outside (friends' uploads, a phone dump) into an event.
   A window: pick the folder and the event to merge into (e.g. `media/2026/06/Grand Teton National Park`).
   Shoebox shows what's new and hides or flags what you already have (via the matcher below); you accept photos
   in (moved into the event) or skip them. Every move goes in a log file (not shown in the app) so it can be
   undone, or Claude can fix things from it. Nothing is deleted.
3. **Duplicates** (separate feature, same matcher): clean up the library itself. Scan an event, a year, or
   everything; show each set of matches side by side (same photo resized, re-saved, renamed, or a burst of
   near-identical shots); keep one, send the rest to the trash (logged, undoable).
   **The matcher** both use: an image fingerprint (perceptual hash) plus the date taken; for videos a few frames
   and the length. Fingerprints are cached like thumbnails. Build it once, ingest first (the thing he needs now).

4. **Installer, updater, uninstaller** (Andrew, 2026-10-27), so friends don't deal with zips.
   - Windows: a real installer (Inno Setup, built by the GitHub workflow): Start menu + desktop shortcut, shows in
     *Add or remove programs* with an uninstaller. Mac: a .dmg to drag into Applications.
   - Updater: on start, Shoebox checks the latest GitHub release; if newer, a small "Update available" note
     with a button that downloads and runs the new installer. Needs the repo (or at least its releases) public.
   - Uninstall keeps the photos (Shoebox never stores them); optionally removes its settings and thumbnails.

## Done
- Year > month > event tree, misc and other groups below the years, search, settings (media folder, no default),
  reopens where you left off.
- Thumbnails (photos, HEIC, videos, audio) cached in `~/.cache/shoebox`; viewer for photos, videos and audio.
- Fast flipping and scrolling (dev, 2026-10-27): skip pictures you've passed, on-screen thumbnails first.
