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
2. **Duplicates and an ingest folder** (Andrew, 2026-10-27). Friends' photos of a trip go in `media/ingest/` with the
   same layout (`ingest/2026/06/Grand Teton National Park/`). Shoebox shows them together with the real event, and a
   duplicates window scans and shows matches side by side (same photo at another size, re-encoded, or renamed)
   with **keep one** / **merge in** / **discard**. The point: see quickly what he doesn't have yet, without going
   through everything his friends shot. Nothing is moved or deleted without asking (to the trash, never a hard delete).
   Matching: an image fingerprint (perceptual hash) plus the date taken; for videos, a few frames and the length.

## Done
- Year > month > event tree, misc and other groups below the years, search, settings (media folder, no default),
  reopens where you left off.
- Thumbnails (photos, HEIC, videos, audio) cached in `~/.cache/shoebox`; viewer for photos, videos and audio.
- Fast flipping and scrolling (dev, 2026-10-27): skip pictures you've passed, on-screen thumbnails first.
