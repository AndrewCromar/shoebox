"""Build the packaged Shoebox app for the system it runs on (Windows .exe folder, macOS .app, or Linux folder).

    python packaging/build.py

Put the tools to bundle in packaging/bin/ first (the GitHub workflow downloads them):
    Windows: ffmpeg.exe, ffprobe.exe, libmpv-2.dll
    macOS:   ffmpeg, ffprobe, libmpv.2.dylib (its other libraries are collected automatically)
Without them the app still runs, using an installed ffmpeg/mpv if there is one.
Output: dist/Shoebox/ (Windows, Linux) or dist/Shoebox.app (macOS).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "packaging"


def icon() -> Path:
    """The SVG icon as a PNG; PyInstaller turns it into .ico / .icns."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    app = QGuiApplication.instance() or QGuiApplication(["build", "-platform", "offscreen"])
    img = QImage(512, 512, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    QSvgRenderer(str(ROOT / "assets" / "shoebox.svg")).render(p)
    p.end()
    out = HERE / "build" / "shoebox.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return out


def main():
    sep = ";" if sys.platform == "win32" else ":"
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "Shoebox",
            "--icon", str(icon()), "--paths", str(ROOT),
            "--distpath", str(ROOT / "dist"), "--workpath", str(HERE / "build" / "work"),
            "--specpath", str(HERE / "build"),
            "--add-data", f"{ROOT / 'assets'}{sep}assets",
            "--collect-all", "pillow_heif",
            "--hidden-import", "mpv",
            "--osx-bundle-identifier", "io.github.andrewcromar.shoebox"]
    for f in sorted((HERE / "bin").glob("*")) if (HERE / "bin").is_dir() else []:
        args += ["--add-binary", f"{f}{sep}bin"]
    args.append(str(HERE / "shoebox_main.py"))
    print(" ".join(args))
    subprocess.run(args, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
