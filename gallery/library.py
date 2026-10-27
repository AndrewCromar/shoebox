"""The photo library: folders named "YYYY-MM-DD Title" under one root, grouped by year and month.

Read-only: nothing here writes inside the library.
A folder that doesn't start with a date (e.g. "2007-2023") goes in its own group at the bottom.
Subfolders ("andrew camera", "nick phone") hang under their folder. Kdenlive proxy folders are skipped.
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mts", ".mkv", ".avi", ".webm", ".3gp"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac", ".wma", ".aiff", ".aif"}
SKIP_DIRS = {"proxy", ".thumbnails", "@eaDir"}
DATE_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?\s*(.*)$")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def kind(p: Path) -> str | None:
    ext = p.suffix.lower()
    return "image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT else "audio" if ext in AUDIO_EXT else None


@dataclass
class Folder:
    path: Path
    name: str                 # shown in the tree: the title without the date
    year: str = ""            # "2026", or the whole name for undated folders
    month: int = 0            # 1-12, 0 if unknown
    day: str = ""
    files: list = field(default_factory=list)      # media directly in this folder, sorted
    children: list = field(default_factory=list)   # subfolders (Folder)

    def all_files(self) -> list[Path]:
        out = list(self.files)
        for c in self.children:
            out += c.all_files()
        return out

    def count(self) -> int:
        return len(self.files) + sum(c.count() for c in self.children)


def _scan(path: Path, name: str) -> Folder:
    f = Folder(path, name)
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
    except OSError:
        return f
    for e in entries:
        if e.name.startswith("."):
            continue
        if e.is_dir(follow_symlinks=False):
            if e.name.lower() not in SKIP_DIRS:
                sub = _scan(Path(e.path), e.name)
                if sub.count():
                    f.children.append(sub)
        elif kind(Path(e.name)):
            f.files.append(Path(e.path))
    return f


def scan(root: Path) -> list[Folder]:
    """Top-level folders, newest first; undated ones last."""
    out = []
    for e in os.scandir(root):
        if not e.is_dir() or e.name.startswith("."):
            continue
        f = _scan(Path(e.path), e.name)
        m = DATE_RE.match(e.name)
        if m and 1 <= int(m.group(2)) <= 12 and not re.match(r"^\d{4}-\d{4}$", e.name):
            f.year, f.month, f.day = m.group(1), int(m.group(2)), m.group(3) or ""
            f.name = m.group(4).strip() or e.name
        else:
            f.year = e.name
        out.append(f)
    dated = sorted((f for f in out if f.month), key=lambda f: f.path.name, reverse=True)
    undated = sorted((f for f in out if not f.month), key=lambda f: f.path.name, reverse=True)
    return dated + undated
