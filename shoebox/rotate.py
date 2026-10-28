"""Turn a photo a quarter turn clockwise, for good (the `t` key; press it again for more).

A JPEG keeps every pixel: only its EXIF orientation changes (the tag every camera and viewer understands), so
nothing is re-compressed and it can go round as often as you like. Other pictures (PNG, HEIC, WebP…) are turned
and saved again. The file keeps its date, so it stays in the same place in its folder.
"""
import io
import os
import struct
from pathlib import Path

from PIL import Image, ImageOps

from . import thumbs

ORIENTATION = 0x0112
# EXIF orientation after a further quarter turn clockwise; 2, 4, 5, 7 are the mirrored ones
TURN = {1: 6, 6: 3, 3: 8, 8: 1, 2: 7, 7: 4, 4: 5, 5: 2}
LOSSLESS = {".jpg", ".jpeg", ".jfif"}
SAVE_AS = {".png": "PNG", ".webp": "WEBP", ".heic": "HEIF", ".heif": "HEIF", ".tif": "TIFF", ".tiff": "TIFF",
           ".bmp": "BMP", ".gif": "GIF"}


def can_rotate(p: Path) -> bool:
    return p.suffix.lower() in LOSSLESS or p.suffix.lower() in SAVE_AS


def rotate(p: Path):
    """A quarter turn clockwise. Raises on a file it can't turn (the caller shows the message)."""
    st = p.stat()
    old = thumbs.cached(p)
    if p.suffix.lower() in LOSSLESS:
        _turn_jpeg(p)
    elif p.suffix.lower() in SAVE_AS:
        _turn_resave(p)
    else:
        raise ValueError(f"can't turn {p.suffix} files")
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # same date: it stays where it was in the folder
    if old:  # the old thumbnail has the same size and date as the new file: drop it so it's made again
        for f in (old[0], old[0].with_suffix(".json")):
            f.unlink(missing_ok=True)


def _segments(data: bytes):
    """(marker, start of the segment's data, its length) for each JPEG header segment, up to the image itself."""
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker == 0xDA:  # start of scan: the picture follows
            return
        n = struct.unpack(">H", data[i + 2:i + 4])[0]
        yield marker, i + 4, n - 2
        i += 2 + n


def _turn_jpeg(p: Path):
    data = bytearray(p.read_bytes())
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    for marker, start, n in _segments(data):
        if marker == 0xE1 and data[start:start + 6] == b"Exif\x00\x00":
            at = _orientation_at(data, start + 6, n - 6)
            if at is not None:  # change the two bytes in place: nothing else in the file moves
                tiff = start + 6
                e = "<" if data[tiff:tiff + 2] == b"II" else ">"
                cur = struct.unpack(e + "H", data[at:at + 2])[0]
                data[at:at + 2] = struct.pack(e + "H", TURN.get(cur, 6))
                _write(p, bytes(data))
                return
            break
    # no orientation tag yet: write the EXIF block again with one (the picture data is copied as it is)
    with Image.open(p) as im:
        exif = im.getexif()
        for ifd in (0x8769, 0x8825):  # load the camera and GPS parts, so they're written back too
            exif.get_ifd(ifd)
    exif[ORIENTATION] = TURN.get(exif.get(ORIENTATION, 1), 6)
    block = b"Exif\x00\x00" + exif.tobytes()
    seg = b"\xff\xe1" + struct.pack(">H", len(block) + 2) + block
    for marker, start, n in _segments(data):
        if marker == 0xE1 and data[start:start + 6] == b"Exif\x00\x00":
            data[start - 4:start + n] = seg
            break
    else:  # no EXIF at all: after JFIF's APP0 if there is one, else right after the start
        app0 = next(((s, n) for m, s, n in _segments(data) if m == 0xE0), None)
        at = app0[0] + app0[1] if app0 else 2
        data[at:at] = seg
    _write(p, bytes(data))


def _orientation_at(data, tiff: int, n: int) -> int | None:
    """Where the orientation value sits in the file, or None if IFD0 doesn't have one."""
    if n < 8 or data[tiff:tiff + 2] not in (b"II", b"MM"):
        return None
    e = "<" if data[tiff:tiff + 2] == b"II" else ">"
    ifd = tiff + struct.unpack(e + "I", data[tiff + 4:tiff + 8])[0]
    count = struct.unpack(e + "H", data[ifd:ifd + 2])[0]
    for k in range(count):
        entry = ifd + 2 + 12 * k
        tag, typ = struct.unpack(e + "HH", data[entry:entry + 4])
        if tag == ORIENTATION and typ == 3:  # SHORT, stored in the entry itself
            return entry + 8
    return None


def _turn_resave(p: Path):
    with Image.open(p) as im:
        exif = im.getexif()
        fmt = SAVE_AS[p.suffix.lower()]
        out = ImageOps.exif_transpose(im).transpose(Image.Transpose.ROTATE_270)  # 270 counter-clockwise
        exif[ORIENTATION] = 1
        kw = {"exif": exif.tobytes()} if fmt in ("PNG", "WEBP", "HEIF", "TIFF") else {}
        if fmt in ("WEBP", "HEIF"):
            kw["quality"] = 95
        if im.info.get("icc_profile"):
            kw["icc_profile"] = im.info["icc_profile"]
        buf = io.BytesIO()
        out.save(buf, fmt, **kw)
    _write(p, buf.getvalue())


def _write(p: Path, data: bytes):
    """Write next to it, then swap: a crash halfway never leaves half a photo."""
    tmp = p.with_name(f".{p.name}.turning")
    tmp.write_bytes(data)
    os.replace(tmp, p)
