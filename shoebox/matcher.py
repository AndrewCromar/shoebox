"""Is this photo one we already have? Used by Ingest (and later Duplicates).

Each file gets a fingerprint from its thumbnail (so it's quick and works for HEIC and videos alike):
- a difference hash: the 64 brighter/darker steps of a tiny 9x8 grey version. A resized, re-saved, renamed or
  slightly re-encoded copy keeps almost the same 64 bits; a different photo differs in many.
- when it was taken (EXIF or the video's creation time), and a video's length.
Two files are the same photo when their hashes differ in only a few bits and, if both know when they were taken,
those times agree (that keeps a burst of near-identical shots apart). Fingerprints are cached next to the
thumbnails.
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import thumbs
from .library import kind

SAME, MAYBE = 6, 11  # bits that may differ: <= SAME is the same photo, <= MAYBE probably
FILE = thumbs.CACHE.parent / "fingerprints.json"
_lock = threading.Lock()
_db: dict | None = None


def _load() -> dict:
    global _db
    if _db is None:
        try:
            _db = json.loads(FILE.read_text())
        except (OSError, ValueError):
            _db = {}
    return _db


def save():
    with _lock:
        if _db is not None:
            FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(_db))
            tmp.replace(FILE)


def dhash(img: Image.Image) -> int:
    g = img.convert("L").resize((9, 8), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = bits << 1 | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def _when(taken: str) -> float | None:
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(taken, fmt).timestamp()
        except (ValueError, TypeError):
            pass
    return None


def fingerprint(p: Path) -> dict | None:
    """{"h": hash, "t": when taken or None, "d": video length or None, "kind"}; None if the file can't be read."""
    try:
        k = thumbs.key(p)
    except OSError:
        return None
    with _lock:
        hit = _load().get(k)
    if hit:
        return hit
    try:
        jpg, meta = thumbs.cached(p) or thumbs.make(p)
        with Image.open(jpg) as im:
            h = dhash(im)
    except Exception:
        return None
    fp = {"h": h, "t": _when(meta.get("taken", "")), "d": meta.get("duration"), "kind": kind(p)}
    with _lock:
        _load()[k] = fp
    return fp


def distance(a: dict, b: dict) -> int | None:
    """How different two fingerprints are (bits), or None if they can't be the same file at all."""
    if a["kind"] != b["kind"]:
        return None
    if a["kind"] in ("video", "audio") and a.get("d") and b.get("d") and abs(a["d"] - b["d"]) > 0.6:
        return None  # a different length is a different clip (a trimmed copy counts as new)
    if a.get("t") and b.get("t") and abs(a["t"] - b["t"]) > 2 and abs(a["t"] - b["t"]) % 3600 > 2:
        return None  # taken at different moments (an exact hours' gap is just a time zone)
    return bin(a["h"] ^ b["h"]).count("1")


def compare(new: list[Path], have: list[Path], progress=None) -> list[dict]:
    """For each new file: {"path", "status": "new" | "have" | "maybe" | "unreadable", "match": path or None,
    "bits"}. progress(done, total) is called as fingerprints are made."""
    total = len(new) + len(have)
    done = 0
    prints = {}
    for p in [*have, *new]:
        prints[p] = fingerprint(p)
        done += 1
        if progress:
            progress(done, total)
    save()
    have_fps = [(p, prints[p]) for p in have if prints[p]]
    out = []
    for p in new:
        fp = prints[p]
        if not fp:
            out.append({"path": p, "status": "unreadable", "match": None, "bits": None})
            continue
        best, best_d = None, None
        for q, qfp in have_fps:
            d = distance(fp, qfp)
            if d is not None and (best_d is None or d < best_d):
                best, best_d = q, d
        status = "have" if best_d is not None and best_d <= SAME else \
            "maybe" if best_d is not None and best_d <= MAYBE else "new"
        out.append({"path": p, "status": status, "match": best if status != "new" else None, "bits": best_d})
    return out
