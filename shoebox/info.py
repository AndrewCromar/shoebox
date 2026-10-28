"""What the info panel (i, full size) shows about a file: the file itself, then what the camera wrote.

Photos: EXIF via Pillow (camera, lens, exposure, GPS…). Videos and audio: ffprobe (length, size, codecs…).
Everything is read, nothing written.
"""
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from PIL import Image

from . import library, system, thumbs

ORIENT = {1: "normal", 2: "mirrored", 3: "upside down", 4: "mirrored, upside down", 5: "mirrored, turned left",
          6: "turned right", 7: "mirrored, turned right", 8: "turned left"}
FLASH_FIRED = 1


def size_text(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def describe(p: Path) -> list[tuple[str, str]]:
    """(label, value) rows; a label with an empty value is a heading."""
    st = p.stat()
    rows = [("FILE", ""), ("name", p.name), ("folder", str(p.parent)), ("size", size_text(st.st_size)),
            ("file date", datetime.fromtimestamp(st.st_mtime).strftime("%b %d %Y, %H:%M:%S"))]
    try:
        rows += _image(p) if library.kind(p) == "image" else _media(p)
    except Exception as ex:  # a damaged file still shows its name and size
        rows.append(("couldn't read", str(ex)))
    return rows


def _num(v) -> float | None:
    try:
        return float(Fraction(v)) if not isinstance(v, tuple) else v[0] / v[1]
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _gps(g: dict) -> str | None:
    def deg(v, ref):
        if not v:
            return None
        d, m, s = (_num(x) or 0 for x in v)
        x = d + m / 60 + s / 3600
        return -x if ref in ("S", "W") else x
    lat, lon = deg(g.get(2), g.get(1)), deg(g.get(4), g.get(3))
    if lat is None or lon is None:
        return None
    alt = _num(g.get(6))
    return f"{lat:.5f}, {lon:.5f}" + (f"  ({alt:.0f} m up)" if alt else "")


def _image(p: Path) -> list[tuple[str, str]]:
    with Image.open(p) as im:
        w, h = im.size
        exif = im.getexif()
        sub = exif.get_ifd(0x8769)
        gps = exif.get_ifd(0x8825)
        fmt = im.format or p.suffix.upper().lstrip(".")
    o = exif.get(0x0112, 1)
    if o in (5, 6, 7, 8):
        w, h = h, w
    rows = [("PICTURE", ""), ("size", f"{w} × {h}  ({w * h / 1e6:.1f} megapixels)"), ("type", fmt)]
    if o != 1:
        rows.append(("orientation", ORIENT.get(o, str(o))))
    t = sub.get(0x9003) or exif.get(0x0132)
    if t:
        rows.append(("taken", _date(t) + (f"  {sub[0x9011]}" if sub.get(0x9011) else "")))
    cam = " ".join(x for x in (str(exif.get(0x010F, "")).strip(), str(exif.get(0x0110, "")).strip()) if x)
    camera = []
    if cam:
        camera.append(("camera", cam))
    if sub.get(0xA434):
        camera.append(("lens", str(sub[0xA434]).strip()))
    f = _num(sub.get(0x829D))
    if f:
        camera.append(("aperture", f"f/{f:.1f}"))
    ex = _num(sub.get(0x829A))
    if ex:
        camera.append(("shutter", f"1/{round(1 / ex)} s" if ex < 1 else f"{ex:g} s"))
    if sub.get(0x8827):
        camera.append(("ISO", str(sub[0x8827])))
    fl = _num(sub.get(0x920A))
    if fl:
        f35 = sub.get(0xA405)
        camera.append(("focal length", f"{fl:.1f} mm" + (f"  ({f35} mm on 35 mm film)" if f35 else "")))
    if sub.get(0x9209) is not None:
        camera.append(("flash", "fired" if int(sub[0x9209]) & FLASH_FIRED else "off"))
    if exif.get(0x0131):
        camera.append(("software", str(exif[0x0131]).strip()))
    if camera:
        rows += [("CAMERA", "")] + camera
    where = _gps(gps)
    if where:
        rows += [("PLACE", ""), ("GPS", where)]
    return rows


def _date(t) -> str:
    try:
        return datetime.strptime(str(t).strip(), "%Y:%m:%d %H:%M:%S").strftime("%b %d %Y, %H:%M:%S")
    except ValueError:
        return str(t)


def _media(p: Path) -> list[tuple[str, str]]:
    if not thumbs.FFPROBE:
        return [("details", "need ffprobe")]
    r = system.run([thumbs.FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)], text=True)
    j = json.loads(r.stdout or "{}")
    fmt, streams = j.get("format", {}), j.get("streams", [])
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    dur = float(fmt.get("duration", 0) or 0)
    rows = [("VIDEO" if library.kind(p) == "video" else "AUDIO", ""),
            ("length", f"{int(dur // 60)}:{dur % 60:04.1f}")]
    if fmt.get("bit_rate"):
        rows.append(("bit rate", f"{int(fmt['bit_rate']) / 1e6:.1f} Mbit/s"))
    if tags.get("creation_time"):
        rows.append(("taken", tags["creation_time"].replace("T", " ").split(".")[0] + " UTC"))
    for s in streams:
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1:
            num, _, den = s.get("avg_frame_rate", "0/1").partition("/")
            fps = float(num) / float(den) if float(den or 0) else 0
            rows.append(("picture", f"{s.get('width')} × {s.get('height')}, {fps:.3g} fps, {s.get('codec_name', '?')}"))
        elif s.get("codec_type") == "audio":
            ch = {1: "mono", 2: "stereo"}.get(s.get("channels"), f"{s.get('channels')} channels")
            rows.append(("sound", f"{s.get('codec_name', '?')}, {ch}, {int(s.get('sample_rate', 0)) // 1000} kHz"))
    for k, label in (("com.apple.quicktime.make", "camera"), ("com.apple.quicktime.model", "model"),
                     ("make", "camera"), ("model", "model"), ("artist", "artist"), ("title", "title"),
                     ("album", "album"), ("location", "GPS"), ("com.apple.quicktime.location.iso6709", "GPS")):
        if tags.get(k) and (label, tags[k]) not in rows:
            rows.append((label, tags[k]))
    return rows
