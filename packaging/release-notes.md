**Shoebox** is a simple photo, video and audio viewer: your folders by year, month and trip on the left,
thumbnails on the right, full size with Enter. It only looks; it never changes your photos.

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
