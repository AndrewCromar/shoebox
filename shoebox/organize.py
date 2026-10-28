"""Tidying the library from Shoebox: rename an event (F2), make a new one (n), move photos to another event (m),
and z to undo the last of those. Nothing is deleted. Every change is logged in organize-log.jsonl in the settings
folder, so it can be put back (or fixed by hand) later.
"""
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import system

LOG = system.config_dir() / "organize-log.jsonl"
BAD = re.compile(r'[\\/:*?"<>|]')  # not allowed in a folder name on Windows (and / anywhere)


def clean_name(name: str) -> str:
    """A folder name from what was typed: no slashes or other characters Windows refuses, no spaces at the ends."""
    name = BAD.sub(" ", name).strip().strip(".")
    return re.sub(r"\s+", " ", name)


def _log(entry: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"when": datetime.now().isoformat(timespec="seconds"), **entry}) + "\n")


def rename_event(path: Path, name: str) -> Path:
    """The event folder gets a new name (in the same month folder). Returns the new path."""
    name = clean_name(name)
    if not name:
        raise ValueError("the name is empty")
    new = path.with_name(name)
    if new == path:
        return path
    if new.exists() and not (new.samefile(path)):  # samefile: only the case changed on Windows/macOS
        raise ValueError(f"there's already a folder called {name}")
    os.rename(path, new)
    _log({"do": "rename", "from": str(path), "to": str(new)})
    return new


def new_event(root: Path, year: int, month: int, name: str) -> Path:
    """root/YYYY/MM/name, made empty. Returns it."""
    name = clean_name(name)
    if not name:
        raise ValueError("the name is empty")
    path = root / f"{year:04d}" / f"{month:02d}" / name
    if path.exists():
        raise ValueError(f"{year}/{month:02d}/{name} is already there")
    path.mkdir(parents=True)
    _log({"do": "new", "path": str(path)})
    return path


def free_name(folder: Path, name: str) -> Path:
    """folder/name, or name (2), name (3)… if that's taken."""
    p, stem, ext, k = folder / name, Path(name).stem, Path(name).suffix, 2
    while p.exists():
        p, k = folder / f"{stem} ({k}){ext}", k + 1
    return p


def move(files: list[Path], dest: Path) -> list[tuple[Path, Path]]:
    """Move files into dest (renamed if the name is taken there). Returns (from, to) for each one moved."""
    done = []
    for f in files:
        if f.parent == dest:
            continue
        to = free_name(dest, f.name)
        shutil.move(str(f), str(to))
        done.append((f, to))
    if done:
        _log({"do": "move", "files": [[str(a), str(b)] for a, b in done]})
    return done


def last() -> dict | None:
    """The last change that hasn't been undone yet."""
    if not LOG.exists():
        return None
    stack = []
    for x in LOG.read_text().splitlines():
        if x.strip():
            e = json.loads(x)
            if e["do"] != "undo":
                stack.append(e)
            elif stack:
                stack.pop()
    return stack[-1] if stack else None


def describe(e: dict) -> str:
    if e["do"] == "rename":
        return f"renamed {Path(e['from']).name} to {Path(e['to']).name}"
    if e["do"] == "new":
        return f"made {Path(e['path']).name}"
    n = len(e["files"])
    return f"moved {n} file{'s' if n != 1 else ''} to {Path(e['files'][0][1]).parent.name}"


def undo() -> str:
    """Put the last change back. Returns what was undone (raises if it can't be)."""
    e = last()
    if not e:
        raise ValueError("nothing to undo")
    if e["do"] == "rename":
        src, dst = Path(e["to"]), Path(e["from"])
        if dst.exists():
            raise ValueError(f"{dst.name} exists again")
        os.rename(src, dst)
    elif e["do"] == "new":
        p = Path(e["path"])
        if p.exists():
            if any(p.iterdir()):
                raise ValueError(f"{p.name} isn't empty any more")
            p.rmdir()
    else:
        for a, b in reversed(e["files"]):
            if Path(b).exists() and not Path(a).exists():
                Path(a).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(b, a)
    _log({"do": "undo"})
    return describe(e)
