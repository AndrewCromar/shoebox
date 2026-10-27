"""Is there a newer Shoebox? Asks GitHub for the latest release (works once the repo is public).

check() returns the newer release, or None (up to date, offline, or the repo is private).
install() gets it: on Windows it downloads the installer and runs it (it closes Shoebox, updates, and opens it
again); elsewhere it opens the release page to download.
"""
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import __version__, system

REPO = "AndrewCromar/shoebox"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
SETUP = "Shoebox-Setup.exe"


def parse(v: str) -> tuple:
    """ "v1.2.0" -> (1, 2, 0); anything odd -> (0,)."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def newer(latest: str, current: str = __version__) -> bool:
    return parse(latest) > parse(current)


def check(timeout: float = 8.0) -> dict | None:
    """The latest release if it's newer than this one: {"version", "page", "setup" (Windows installer URL)}."""
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"Shoebox/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.load(r)
    except Exception:  # offline, rate-limited, or the repo isn't public yet
        return None
    tag = rel.get("tag_name", "")
    if rel.get("draft") or rel.get("prerelease") or not newer(tag):
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
    return {"version": tag.lstrip("v"), "page": rel.get("html_url", f"https://github.com/{REPO}/releases/latest"),
            "setup": assets.get(SETUP)}


def can_self_update(rel: dict) -> bool:
    """Only an installed Windows app updates itself; the rest opens the download page."""
    return system.WINDOWS and system.FROZEN and bool(rel.get("setup"))


def install(rel: dict, progress=None) -> bool:
    """Windows: download the installer and start it (Shoebox should quit right after). Returns True if started.
    Elsewhere: open the release page."""
    if not can_self_update(rel):
        system.open_path_url(rel["page"])
        return False
    dest = Path(tempfile.gettempdir()) / f"Shoebox-Setup-{rel['version']}.exe"
    req = urllib.request.Request(rel["setup"], headers={"User-Agent": f"Shoebox/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done * 100 // total)
    # /SILENT shows a small progress window; the installer closes Shoebox, updates it, and starts it again
    subprocess.Popen([str(dest), "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
                      "/NORESTART", "/UPDATE=1"], creationflags=subprocess.DETACHED_PROCESS)
    return True


def is_disabled() -> bool:
    return bool(os.environ.get("SHOEBOX_NO_UPDATE_CHECK"))
