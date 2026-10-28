**Shoebox** is a simple photo, video and audio viewer: your folders by year, month and trip on the left,
thumbnails on the right, full size with Enter. It only looks; it never changes your photos unless you ask.

### What's new in 1.4.1
- **Linux:** fixes a crash after scrolling for a while. The installer now uses Python 3.12 or newer and rebuilds
  an older setup when you update (u).

### What's new in 1.4
- **Zoom:** full size, Ctrl + / Ctrl − (or = and _), Ctrl 0 fits; Ctrl arrows or drag to move around.
- **Info (i):** a side panel with the file's details and what the camera wrote (camera, lens, exposure, GPS…).
- **Slideshow (p):** full screen, photos fade into each other, videos play muted (v for sound).
- **Organize:** n makes a new event, F2 renames one, m moves photos to another event (shift/ctrl pick several),
  z undoes. Nothing is deleted.
- **t** turns every selected photo.
- **Open with:** Shoebox can open a photo, video or song from your file manager, even outside your media folder
  (it just looks). You can pick it as your default viewer.

### What's new in 1.3
- **Turn (t):** a quarter turn clockwise, on a thumbnail or full size; press again for more. Saved in the file:
  JPEGs keep every pixel (only the orientation tag changes, like a phone does).

### What's new in 1.2
- **Duplicates (Shift+D):** find the same picture more than once in an event, a month or a year, even renamed,
  resized or re-saved. Each set is shown side by side with the best copy marked KEEP; Enter sends the rest to the
  system trash (Recycle Bin), so they can be restored, and z puts the last set back.

### What's new in 1.1.1
- **Linux:** videos play again. Linux now installs from the source with its own Python environment and uses
  your system's mpv and ffmpeg (the old bundle clashed with newer system libraries), and **u** updates it.

### What's new in 1.1
- **Ingest (i):** bring a folder (a friend's upload, a phone dump) into an event without doubles. Each photo is
  marked NEW, HAVE or MAYBE by comparing the pictures themselves, so renamed, resized, re-saved or re-dated copies
  are still caught. Tick what you want, Enter moves it in, z undoes it. Nothing is deleted.
- **r** reloads the folders.

### Download
- **Windows:** `Shoebox-Setup.exe` (double-click; if Windows says it protected your PC: *More info* → *Run anyway*)
- **Mac:** `Shoebox-macOS.dmg` (drag Shoebox into Applications; the first time, right-click it → *Open*)
- **Linux:** `curl -fsSL https://raw.githubusercontent.com/AndrewCromar/shoebox/main/install.sh | sh`

Step-by-step help is in the [README](https://github.com/AndrewCromar/shoebox#install).
Already have Shoebox? It shows a green bar when there's a new version: press **u**.
