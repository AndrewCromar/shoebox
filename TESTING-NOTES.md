# Andrew's test notes (2026-10-27, Windows laptop)

Problems he noticed. Fixed on `platforms` (2026-10-27), waiting for his retest.

1. **Show in files (d) on Windows opened Documents** instead of the photo's folder.
   Likely cause: Python quotes the whole `/select,C:\...\photo.jpg` argument when the path has spaces, and
   Explorer doesn't understand the quotes there, so it falls back to Documents. Fix: build the command line
   ourselves: `explorer /select,"C:\...\photo.jpg"`. **Fixed** (can't test on Linux: retest on Windows).
2. **The folder pane width isn't remembered.** Dragging the divider works, but the next start is back to the
   default. **Fixed**: the width is saved in settings.json when you drag it (tested).
3. **Always start maximized** (instead of a 1600x980 window). **Fixed.**
4. **d in the thumbnails didn't highlight the photo on Windows** (it did from the viewer). **Fixed**: d now
   follows the side you were last on (folders or photos), not which widget has keyboard focus at that moment.
5. **Multiple photos could be selected with the mouse** (Ctrl/Shift-click) with no use for it. **Fixed**: one at a time.

Works on Windows (confirmed by Andrew, 2026-10-27):
- The installer (Shoebox-Setup.exe) and the app it installs.
- Open in its app (o).
- d from the viewer highlights the photo in Explorer (after fix 1).
