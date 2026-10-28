# Shoebox roadmap

Branches: `main` is the last version Andrew said works; new work goes on `dev` and is merged into main when he says.

## Next
1. Andrew tests Ingest (v1.1) and Duplicates (v1.2). A friend tests the Mac version.

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

4. ~~**Installer, updater, uninstaller**~~ done in v1.0.0 (Andrew, 2026-10-27), so friends don't deal with zips.
   - Windows: a real installer (Inno Setup, built by the GitHub workflow): Start menu + desktop shortcut, shows in
     *Add or remove programs* with an uninstaller. Mac: a .dmg to drag into Applications.
   - Updater: on start, Shoebox checks the latest GitHub release; if newer, a small "Update available" note
     with a button that downloads and runs the new installer. Needs the repo (or at least its releases) public.
   - Uninstall keeps the photos (Shoebox never stores them); optionally removes its settings and thumbnails.

## Done
- **Turn (t)** (dev, 2026-10-27): a quarter turn clockwise, saved; JPEGs lossless (EXIF orientation).
- **Duplicates** (v1.2, 2026-10-27): Shift+D; sets side by side, keep the best, rest to the trash, z undoes.
- **v1.1.0**: Ingest, r reloads; the picture decides, not names or metadata.
- **Ingest** + the matcher (dev, 2026-10-27): i opens it; NEW / HAVE / MAYBE, tick, move in, logged, z undoes.
- **v1.0.0** (2026-10-27): Windows installer, Mac .dmg, Linux install command, in-app updates. Tested on
  Andrew's Windows laptop and in CI on all three systems.
- Year > month > event tree, misc and other groups below the years, search, settings (media folder, no default),
  reopens where you left off.
- Thumbnails (photos, HEIC, videos, audio) cached in `~/.cache/shoebox`; viewer for photos, videos and audio.
- Fast flipping and scrolling (dev, 2026-10-27): skip pictures you've passed, on-screen thumbnails first.
