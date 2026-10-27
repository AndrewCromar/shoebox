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
    sort: float = 0.0         # when it started, for the order within a month
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


def month_of(name: str) -> int:
    """ "06", "6", "June", "06 June", "2026-06" -> 6; 0 if it isn't a month."""
    low = name.lower()
    m = re.match(r"^(?:\d{4}-)?(\d{1,2})\b", low)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    for i, mn in enumerate(MONTHS, 1):
        if low.startswith(mn.lower()[:3]):
            return i
    return 0


def _first_time(f: Folder) -> float:
    """When an event started: its oldest file (event folders have no date in their names)."""
    times = []
    for p in f.all_files():
        try:
            times.append(p.stat().st_mtime)
        except OSError:
            pass
    return min(times) if times else 0.0


def scan(root: Path) -> list[Folder]:
    """The library, in tree order:
        root/2026/06/Teton National Park/   year > month > event (newest first)
        root/misc/wallpapers/               any other top folder: a group below the years
    Older layouts still work: root/2026-06-05 Teton National Park/ (date in the name)."""
    years, groups = [], []
    for e in sorted(os.scandir(root), key=lambda e: e.name.lower()):
        if not e.is_dir() or e.name.startswith("."):
            continue
        path = Path(e.path)
        if re.fullmatch(r"\d{4}", e.name):
            for me in os.scandir(path):
                mo = month_of(me.name) if me.is_dir() else 0
                if not mo:
                    continue
                month = _scan(Path(me.path), me.name)
                events = month.children
                if month.files:  # photos straight in the month folder
                    events.append(Folder(month.path, "loose files", files=month.files))
                for ev in events:
                    ev.year, ev.month = e.name, mo
                    dm = DATE_RE.match(ev.name)
                    if dm and dm.group(4).strip():  # "2025-05-21 Animatronics Dragon": the day, then the name
                        ev.day, ev.name = dm.group(3) or "", dm.group(4).strip()
                    ev.sort = _first_time(ev)
                    years.append(ev)
            continue
        m = DATE_RE.match(e.name)
        if m and 1 <= int(m.group(2)) <= 12 and not re.match(r"^\d{4}-\d{4}$", e.name):
            f = _scan(path, e.name)
            f.year, f.month, f.day = m.group(1), int(m.group(2)), m.group(3) or ""
            f.name = m.group(4).strip() or e.name
            f.sort = _first_time(f)
            years.append(f)
            continue
        g = _scan(path, e.name)  # a group like misc: its folders, and any loose files
        for ev in g.children + ([Folder(path, "loose files", files=g.files)] if g.files else []):
            ev.year = e.name
            groups.append(ev)
    years.sort(key=lambda f: (f.year, f.month, f.sort), reverse=True)
    groups.sort(key=lambda f: (f.year != "misc", f.year.lower(), f.name.lower()))
    return years + groups
