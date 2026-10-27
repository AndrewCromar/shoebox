"""shoebox --selftest [report file]: checks a build works on this machine, without anyone watching.

Makes a tiny library (a photo, and a video and a song when ffmpeg is there), then: scans it, makes every
thumbnail, starts the video player, and opens the window offscreen. Writes a report and exits 0 if all passed.
Used by the GitHub build for Windows and macOS (nobody can click around there).
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path


def run(report: Path) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            out = fn()
            lines.append(f"PASS {name}" + (f": {out}" if out else ""))
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n" + traceback.format_exc())

    from PIL import Image
    from . import library, system, thumbs
    tmp = Path(tempfile.mkdtemp(prefix="shoebox-selftest-"))
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    thumbs.CACHE = tmp / "cache" / "thumbs"
    event = tmp / "media" / "2026" / "06" / "Test Trip"
    event.mkdir(parents=True)
    Image.new("RGB", (640, 480), "#7fbf6a").save(event / "photo.jpg")
    check("ffmpeg found", lambda: thumbs.FFMPEG or (_ for _ in ()).throw(RuntimeError("no ffmpeg")))
    check("ffprobe found", lambda: thumbs.FFPROBE or (_ for _ in ()).throw(RuntimeError("no ffprobe")))
    if thumbs.FFMPEG:
        system.run([thumbs.FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "2",
                    "-pix_fmt", "yuv420p", str(event / "clip.mp4")])
        system.run([thumbs.FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2",
                    str(event / "song.mp3")])
    try:
        import pillow_heif  # noqa: F401
        lines.append("PASS HEIC support")
    except ImportError:
        ok = False
        lines.append("FAIL HEIC support: pillow_heif missing")

    folders = []
    check("scan", lambda: (folders.extend(library.scan(tmp / "media")), f"{folders[0].count()} files")[1])
    for p in sorted(event.iterdir()):
        check(f"thumbnail {p.name}", lambda p=p: (lambda r: f"{r[0].stat().st_size} bytes {r[1]}")(thumbs.make(p)))

    def player():
        system.prepare_mpv()
        import mpv
        m = mpv.MPV(vo="null", ao="null")
        m.play(str(event / "clip.mp4"))
        m.wait_until_playing(timeout=10)
        pos = m.time_pos
        m.terminate()
        return f"libmpv {mpv.__version__ if hasattr(mpv, '__version__') else ''} played to {pos}"
    if thumbs.FFMPEG:
        check("video player (libmpv)", player)

    def window():
        from PySide6.QtWidgets import QApplication
        from . import app
        a = QApplication.instance() or QApplication([])
        w = app.Shoebox(tmp / "media")
        w.show()
        a.processEvents()
        n = w.tree.topLevelItemCount()
        w.close()
        return f"{n} year(s) in the tree"
    check("window", window)

    lines.insert(0, f"Shoebox self-test on {sys.platform}: {'ALL PASSED' if ok else 'SOME FAILED'}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        print("\n".join(lines))
    except Exception:  # a windowed app on Windows has no console
        pass
    return 0 if ok else 1
