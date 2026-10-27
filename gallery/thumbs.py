"""Thumbnails, cached in ~/.cache/gallery (never next to the photos).

A thumbnail is a JPEG, longest side SIZE, keyed by the file's path, size and modified time, so an edited
file gets a new one. Videos: a frame 1 s in (or the first frame) and their length, from ffmpeg/ffprobe.
Worker threads make them in the order asked; asking for a new folder drops what's left of the old one.
"""
import ctypes
import hashlib
import json
import os
import queue
import subprocess
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:  # HEIC photos just show no thumbnail
    pass

from .library import kind

SIZE = 360
BIG = 20_000_000  # pixels; a 48 MP HEIC takes ~190 MB to decode, so only one of those at a time
big_lock = threading.Lock()
try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:
    _libc = None


def give_back():
    """Return freed decode buffers to the system (glibc keeps them otherwise)."""
    if _libc:
        _libc.malloc_trim(0)
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "gallery" / "thumbs"


def key(p: Path) -> str:
    st = p.stat()
    return hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()


def cached(p: Path) -> tuple[Path, dict] | None:
    try:
        k = key(p)
    except OSError:
        return None
    jpg = CACHE / k[:2] / f"{k}.jpg"
    if jpg.exists():
        meta = jpg.with_suffix(".json")
        return jpg, (json.loads(meta.read_text()) if meta.exists() else {})
    return None


def probe(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=creation_time",
                        "-of", "json", str(p)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    try:
        f = json.loads(r.stdout)["format"]
        return {"duration": float(f.get("duration", 0)), "taken": f.get("tags", {}).get("creation_time", "")}
    except (ValueError, KeyError):
        return {}


def make(p: Path) -> tuple[Path, dict]:
    k = key(p)
    jpg = CACHE / k[:2] / f"{k}.jpg"
    jpg.parent.mkdir(parents=True, exist_ok=True)
    tmp = jpg.with_name(f".{k}.{threading.get_ident()}.jpg")
    meta = {}
    if kind(p) == "audio":
        meta = probe(p)
        # its cover art if it has one, else a plain tile with a note
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-an", "-frames:v", "1",
                            "-vf", f"scale={SIZE}:-2", str(tmp)], capture_output=True, stdin=subprocess.DEVNULL)
        if r.returncode != 0 or not tmp.exists() or not tmp.stat().st_size:
            tile = Image.new("RGB", (SIZE, SIZE), "#1d2320")
            d = ImageDraw.Draw(tile)
            found = subprocess.run(["fc-match", "-f", "%{file}", "sans:charset=266a"], capture_output=True, text=True)
            font = ImageFont.truetype(found.stdout or "DejaVuSans.ttf", SIZE // 3)  # a font that has ♪
            d.text((SIZE / 2, SIZE / 2), "♪", font=font, fill="#cfe3a8", anchor="mm")
            tile.save(tmp, "JPEG", quality=90)
    elif kind(p) == "video":
        meta = probe(p)
        for at in ("1", "0"):
            r = subprocess.run(["nice", "ffmpeg", "-v", "error", "-y", "-ss", at, "-i", str(p), "-frames:v", "1",
                                "-vf", f"scale='if(gt(iw,ih),{SIZE},-2)':'if(gt(iw,ih),-2,{SIZE})'", str(tmp)],
                               capture_output=True, stdin=subprocess.DEVNULL)
            if r.returncode == 0 and tmp.exists() and tmp.stat().st_size:
                break
        else:
            raise RuntimeError(f"no frame from {p.name}")
    else:
        with Image.open(p) as im, (big_lock if im.width * im.height > BIG and im.format != "JPEG" else _nolock):
            im.draft("RGB", (SIZE * 2, SIZE * 2))  # fast JPEG decode at a smaller size
            taken = im.getexif().get_ifd(0x8769).get(36867) or im.getexif().get(306) or ""  # DateTimeOriginal
            im = ImageOps.exif_transpose(im)
            meta = {"w": im.width, "h": im.height, "taken": str(taken).strip()}
            im = im.convert("RGB")
            im.thumbnail((SIZE, SIZE), Image.LANCZOS)
            im.save(tmp, "JPEG", quality=85)
    give_back()
    tmp.replace(jpg)
    jpg.with_suffix(".json").write_text(json.dumps(meta))
    return jpg, meta


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_nolock = _NoLock()


class Maker:
    """Background thumbnail makers. ask() replaces the queue; done(path, jpg, meta) is called from a worker
    thread (connect it to a Qt signal)."""

    def __init__(self, done, workers: int = 3):
        self.done = done
        self.q: queue.Queue = queue.Queue()
        self.gen = 0
        self.lock = threading.Lock()
        for _ in range(workers):
            threading.Thread(target=self.work, daemon=True).start()

    def ask(self, paths: list[Path]):
        with self.lock:
            self.gen += 1
            while not self.q.empty():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break
            for p in paths:
                self.q.put((self.gen, p))

    def work(self):
        while True:
            gen, p = self.q.get()
            if gen != self.gen:
                continue
            try:
                jpg, meta = cached(p) or make(p)
            except Exception:  # unreadable file: it keeps its placeholder
                jpg, meta = None, {}
            self.done(p, jpg, meta)
