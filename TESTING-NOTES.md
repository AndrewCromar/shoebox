# Andrew's test notes (2026-10-27, Windows laptop)

Problems he noticed. Fixed on `platforms` (2026-10-27), waiting for his retest.

1. **Show in files (d) on Windows opened Documents** instead of the photo's folder.
   Likely cause: Python quotes the whole `/select,C:\...\photo.jpg` argument when the path has spaces, and
   Explorer doesn't understand the quotes there, so it falls back to Documents. Fix: build the command line
   ourselves: `explorer /select,"C:\...\photo.jpg"`. **Fixed** (can't test on Linux: retest on Windows).
2. **The folder pane width isn't remembered.** Dragging the divider works, but the next start is back to the
   default. **Fixed**: the width is saved in settings.json when you drag it (tested).
3. **Always start maximized** (instead of a 1600x980 window). **Fixed.**

Works on Windows:
- Open in its app (o).
