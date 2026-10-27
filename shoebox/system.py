"""Everything that differs between Linux, Windows and macOS, in one place.

- where settings and thumbnails live
- finding ffmpeg/ffprobe and libmpv (bundled next to the app, or installed)
- running a tool without a console window popping up (Windows)
- opening a file in its app, and showing it in the file manager
"""
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
FROZEN = getattr(sys, "frozen", False)  # a packaged app (PyInstaller)
# where a packaged app keeps its bundled tools (ffmpeg, ffprobe, libmpv)
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def config_dir() -> Path:
    if WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Shoebox"
    if MAC:
        return Path.home() / "Library" / "Application Support" / "Shoebox"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "shoebox"


def cache_dir() -> Path:
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Shoebox" / "cache"
    if MAC:
        return Path.home() / "Library" / "Caches" / "Shoebox"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "shoebox"


def tool(name: str) -> str | None:
    """ffmpeg / ffprobe: the bundled copy first, then the one installed on the system."""
    exe = name + (".exe" if WINDOWS else "")
    for d in (BUNDLE / "bin", BUNDLE):
        if (d / exe).exists():
            return str(d / exe)
    return shutil.which(name)


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """A command-line tool, quietly: low priority where that's possible, no console window on Windows."""
    if WINDOWS:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    elif shutil.which("nice"):
        cmd = ["nice", *cmd]
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, **kw)


def prepare_mpv():
    """Let python-mpv find libmpv: a bundled copy goes on the search path before `import mpv`."""
    for d in (BUNDLE / "bin", BUNDLE):
        if WINDOWS and (d / "libmpv-2.dll").exists():
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(d))
        if MAC and any(d.glob("libmpv*.dylib")):
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = str(d) + os.pathsep + os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")


def _detached(cmd: list):
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if WINDOWS:
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen([str(c) for c in cmd], **kw)


def open_path(p: Path):
    """A file in its usual app, or a folder in the file manager."""
    if WINDOWS:
        os.startfile(str(p))  # noqa: the Windows "double-click"
    elif MAC:
        _detached(["open", p])
    else:
        _detached(["xdg-open", p])


def show_in_file_manager(p: Path):
    """The file manager with this file selected (Dolphin, Explorer, Finder)."""
    if WINDOWS:  # one command line, built by hand: Explorer doesn't understand "/select,C:\a b.jpg" in quotes
        subprocess.Popen(f'explorer /select,"{p}"', creationflags=subprocess.DETACHED_PROCESS)
    elif MAC:
        _detached(["open", "-R", p])
    else:  # the freedesktop "show this file" call, which every Linux file manager answers
        _detached(["dbus-send", "--session", "--dest=org.freedesktop.FileManager1", "--type=method_call",
                   "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                   f"array:string:{p.as_uri()}", "string:"])


_libc = None
if sys.platform.startswith("linux"):
    try:
        _libc = ctypes.CDLL("libc.so.6")
    except OSError:
        pass


def give_back():
    """Hand freed decode buffers back to the system (glibc keeps them otherwise; not needed elsewhere)."""
    if _libc:
        _libc.malloc_trim(0)
