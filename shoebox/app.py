"""The window: folders by year and month on the left, thumbnails on the right, a full-size viewer on Enter.

Looks like the drew.in.nature studio (same colours and font). Works with the keyboard or the mouse.
Read-only: it never moves, renames or edits a photo.
"""
import json
import locale
import re
import shutil
from collections import OrderedDict
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from . import system

system.prepare_mpv()
try:
    import mpv
except (ImportError, OSError):  # no libmpv: photos still work, videos open in their own app
    mpv = None
from PIL import Image, ImageOps
from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QIcon, QColor, QFont, QImage, QKeySequence, QOpenGLContext, QPainter, QPixmap, QShortcut,
                           QTransform)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QPushButton, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QSplitter,
                               QStackedWidget, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from . import __version__, info, library, organize, rotate, thumbs, updates

CONFIG = system.config_dir() / "settings.json"
ICON = Path(__file__).resolve().parent.parent / "assets" / "shoebox.svg"


def settings() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(d: dict):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(d, indent=1) + "\n")


def media_root() -> Path | None:
    """The library: SHOEBOX_ROOT, else the folder picked in Settings. No default: the first start asks."""
    r = os.environ.get("SHOEBOX_ROOT") or settings().get("root")
    return Path(r).expanduser() if r else None


ROOT = media_root()

C = {"bg": "#111312", "panel": "#171a18", "cur": "#232722", "sel": "#1b2a1f", "line": "#262a27",
     "fg": "#e8e6df", "mid": "#a3a69d", "dim": "#5d625a", "acc": "#cfe3a8", "keep": "#7fbf6a", "cyan": "#8fc1c9",
     "warn": "#e0b84f", "bad": "#e07a5f"}
FONT = "Noto Sans Mono"
MAX_PIX = 300  # thumbnails kept in memory
QSS = f"""
* {{ font-family: "{FONT}"; }}
QWidget {{ background: {C['bg']}; color: {C['fg']}; font-size: 11pt; }}
QLabel {{ background: transparent; }}
QTreeWidget, QListView {{ border: none; outline: none; }}
QTreeWidget {{ background: {C['panel']}; }}
QLineEdit {{ background: {C['bg']}; border: none; border-bottom: 1px solid {C['line']}; padding: 10px 14px;
            color: {C['fg']}; selection-background-color: #3a4036; }}
QLineEdit:focus {{ border-bottom: 1px solid {C['acc']}; }}
QTreeWidget::item {{ padding: 4px 2px; }}
QTreeWidget::item:selected {{ background: {C['sel']}; color: {C['acc']}; }}
QTreeWidget::item:hover {{ background: {C['cur']}; }}
QSplitter::handle {{ background: {C['line']}; width: 1px; }}
QScrollBar:vertical {{ background: {C['bg']}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {C['line']}; min-height: 30px; border-radius: 4px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


COMMANDS = {"n": "new", "e": "rename", "m": "move", "z": "undo"}  # organize.py; F2 renames too


def command_of(e) -> str | None:
    if e.key() == Qt.Key_F2:
        return "rename"
    return COMMANDS.get(e.text()) if not e.modifiers() & (Qt.ControlModifier | Qt.AltModifier) else None


def span(text, color="fg", bold=False) -> str:
    t = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<span style="color:{C.get(color, color)};{"font-weight:600;" if bold else ""}">{t}</span>'


def label(text="", color="fg", size=11) -> QLabel:
    lb = QLabel(text)
    lb.setTextFormat(Qt.RichText)
    lb.setStyleSheet(f"color:{C[color]}; font-size:{size}pt;")
    return lb


def fmt_len(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def taken(p: Path, meta: dict) -> str:
    """When it was taken: the photo's EXIF date or the video's creation time, else the file's date."""
    t = meta.get("taken", "")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            d = datetime.strptime(t, fmt)
            if fmt.endswith("Z"):  # videos store UTC
                d = d.replace(tzinfo=__import__("datetime").timezone.utc).astimezone()
            return d.strftime("%b %d %Y, %H:%M")
        except ValueError:
            pass
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%b %d %Y, %H:%M") + " (file date)"


# ---------------------------------------------------------------- thumbnail grid
class Items(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.paths: list[Path] = []
        self.pix: OrderedDict[Path, QPixmap] = OrderedDict()  # the last MAX_PIX drawn; the rest load from disk
        self.jpg: dict[Path, Path] = {}  # thumbnail file in the cache
        self.meta: dict[Path, dict] = {}
        self.row: dict[Path, int] = {}

    def set_paths(self, paths: list[Path]):
        self.beginResetModel()
        self.paths = paths
        self.row = {p: i for i, p in enumerate(paths)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.paths)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.UserRole:
            return self.paths[index.row()]
        if role == Qt.ToolTipRole:
            return self.paths[index.row()].name
        return None

    def pixmap(self, p: Path) -> QPixmap | None:
        """The thumbnail, loaded from the disk cache when it's drawn; only the last MAX_PIX stay in memory."""
        pm = self.pix.get(p)
        if pm is not None:
            self.pix.move_to_end(p)
            return pm
        jpg = self.jpg.get(p)
        if not jpg:
            return None
        pm = QPixmap(str(jpg))
        if pm.isNull():
            return None
        self.pix[p] = pm
        if len(self.pix) > MAX_PIX:
            self.pix.popitem(last=False)
        return pm

    def got(self, p: Path, jpg, meta):
        if jpg:
            self.jpg[p] = jpg
        self.meta[p] = meta
        if p in self.row:
            i = self.index(self.row[p])
            self.dataChanged.emit(i, i)


class Cell(QStyledItemDelegate):
    def __init__(self, model: Items):
        super().__init__()
        self.m = model
        self.size = 180

    def sizeHint(self, option, index):
        return QSize(self.size + 12, self.size + 12)

    def paint(self, painter: QPainter, option, index):
        p = self.m.paths[index.row()]
        r = option.rect.adjusted(6, 6, -6, -6)
        selected = bool(option.state & option.state.State_Selected) and option.widget.hasFocus()
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        pm = self.m.pixmap(p)
        if pm:
            s = pm.size().scaled(r.size(), Qt.KeepAspectRatio)
            box = QRect(r.x() + (r.width() - s.width()) // 2, r.y() + (r.height() - s.height()) // 2, s.width(), s.height())
            painter.drawPixmap(box, pm)
        else:
            box = r.adjusted(r.width() // 6, r.height() // 6, -r.width() // 6, -r.height() // 6)
            painter.fillRect(box, QColor(C["panel"]))
            painter.setPen(QColor(C["dim"]))
            painter.drawText(box, Qt.AlignCenter, p.suffix.lower().lstrip("."))
        if library.kind(p) in ("video", "audio"):
            d = self.m.meta.get(p, {}).get("duration")
            text = ("▶ " if library.kind(p) == "video" else "♪ ") + (fmt_len(d) if d else "")
            f = QFont(FONT, 9)
            painter.setFont(f)
            w = painter.fontMetrics().horizontalAdvance(text) + 12
            badge = QRect(box.right() - w - 4, box.bottom() - 24, w, 20)
            painter.fillRect(badge, QColor(0, 0, 0, 170))
            painter.setPen(QColor("white"))
            painter.drawText(badge, Qt.AlignCenter, text)
        if selected:
            painter.setPen(QColor(C["acc"]))
            painter.drawRect(box.adjusted(-3, -3, 2, 2))
            painter.drawRect(box.adjusted(-2, -2, 1, 1))
        painter.restore()


class Grid(QListView):
    open_item = Signal(int)
    to_tree = Signal()
    command = Signal(str)

    def __init__(self, model: Items):
        super().__init__()
        self.setModel(model)
        self.cell = Cell(model)
        self.setItemDelegate(self.cell)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)  # shift / ctrl pick several to move (m)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(40)
        self.setSpacing(0)
        self.doubleClicked.connect(lambda i: self.open_item.emit(i.row()))

    def zoom(self, d: int):
        self.cell.size = max(90, min(360, self.cell.size + d))
        self.scheduleDelayedItemsLayout()
        self.viewport().update()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom(20 if e.angleDelta().y() > 0 else -20)
        else:
            super().wheelEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentIndex().isValid():
            self.open_item.emit(self.currentIndex().row())
        elif e.key() in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Tab):
            self.to_tree.emit()
        elif e.key() == Qt.Key_Left and self.currentIndex().row() == 0:
            self.to_tree.emit()
        elif command_of(e):
            self.command.emit(command_of(e))
        elif e.text() in ("+", "="):
            self.zoom(30)
        elif e.text() == "-":
            self.zoom(-30)
        else:
            super().keyPressEvent(e)


# ---------------------------------------------------------------- viewer
class Mpv(QOpenGLWidget):
    """mpv drawing into the window (render API), like the studio's player."""
    frame = Signal()

    def __init__(self):
        super().__init__()
        locale.setlocale(locale.LC_NUMERIC, "C")
        self.m = mpv.MPV(vo="libmpv", keep_open="yes", hwdec="auto-safe", osd_level=1,
                         input_default_bindings=False, input_vo_keyboard=False) if mpv else None
        self.ctx = None
        self.frame.connect(self.update, Qt.QueuedConnection)

    def initializeGL(self):
        if not self.m:
            return

        def gpa(_ctx, name):
            return int(QOpenGLContext.currentContext().getProcAddress(name.decode()) or 0)
        self._gpa = mpv.MpvGlGetProcAddressFn(gpa)
        self.ctx = mpv.MpvRenderContext(self.m, "opengl", opengl_init_params={"get_proc_address": self._gpa})
        self.ctx.update_cb = self.frame.emit

    def paintGL(self):
        if self.ctx:
            r = self.devicePixelRatio()
            self.ctx.render(flip_y=True, opengl_fbo={"w": int(self.width() * r), "h": int(self.height() * r),
                                                      "fbo": self.defaultFramebufferObject()})

    def play(self, p: Path):
        if self.m:
            self.m.command("loadfile", str(p), "replace")
            self.m.pause = False

    def stop(self):
        self.key("stop")

    def key(self, cmd, *args):
        if not self.m:
            return
        try:
            self.m.command(cmd, *args)
        except SystemError:
            pass

    def toggle(self):
        if self.m:
            self.m.pause = not self.m.pause


class Picture(QLabel):
    """The photo, fitted to the window, or zoomed in (Ctrl +/−) and moved around (Ctrl arrows, or drag).
    zoom is relative to fitting: 1 = the whole photo. (cx, cy): the middle of the view, as a fraction of the photo.
    Text (loading…, a song's name) shows like a normal label."""
    zoomed = Signal()

    def __init__(self):
        super().__init__()
        self.img: QImage | None = None
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        self.drag = None

    def setText(self, text):
        self.img = None
        super().setText(text)

    def set_image(self, img: QImage, keep_view: bool = False):
        if not keep_view:
            self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        super().setText("")
        self.img = img
        self.clamp()
        self.update()

    def scale(self) -> float:
        """Screen pixels per photo pixel."""
        return min(self.width() / self.img.width(), self.height() / self.img.height()) * self.zoom

    def clamp(self):
        """Keep the photo filling the view where it's bigger than it; centred where it's smaller."""
        if self.img is None:
            return
        s = self.scale()
        for attr, view, size in (("cx", self.width(), self.img.width()), ("cy", self.height(), self.img.height())):
            half = view / (2 * s * size)
            setattr(self, attr, 0.5 if half >= 0.5 else min(1 - half, max(half, getattr(self, attr))))

    def set_zoom(self, z: float):
        self.zoom = max(1.0, min(z, 40.0))
        self.clamp()
        self.update()
        self.zoomed.emit()

    def pan(self, dx: float, dy: float):
        """Move the view by a fraction of the view's size."""
        if self.img is None or self.zoom <= 1:
            return
        s = self.scale()
        self.cx += dx * self.width() / (s * self.img.width())
        self.cy += dy * self.height() / (s * self.img.height())
        self.clamp()
        self.update()

    def paintEvent(self, e):
        if self.img is None:
            return super().paintEvent(e)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000"))
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        s = self.scale()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(s, s)
        painter.translate(-self.cx * self.img.width(), -self.cy * self.img.height())
        painter.drawImage(0, 0, self.img)
        painter.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.clamp()

    def mousePressEvent(self, e):
        if self.img is not None and self.zoom > 1 and e.button() == Qt.LeftButton:
            self.drag = e.position()
            self.setCursor(Qt.ClosedHandCursor)
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            d = e.position() - self.drag
            self.drag = e.position()
            self.pan(-d.x() / self.width(), -d.y() / self.height())

    def mouseReleaseEvent(self, e):
        self.drag = None
        self.unsetCursor()


class Viewer(QWidget):
    """One photo or video, filling the window. ←→ next/previous, Esc back to the grid. Ctrl +/− zoom, Ctrl arrows
    move around, i the info panel (info.py), p a slideshow."""
    loaded = Signal(object, object, bool)  # (path, QImage or error text, full size)
    described = Signal(object, object)  # (path, info rows)
    back = Signal()
    changed = Signal()  # another photo/video: the keys bar follows
    command = Signal(str)
    SLIDE_SECONDS = 4

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        h.addLayout(main, 1)
        self.stack = QStackedWidget()
        self.pic = Picture()
        self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setStyleSheet("background:#000;")
        self.pic.setMinimumSize(1, 1)
        self.pic.zoomed.connect(self.zoom_changed)
        self.video = Mpv()
        self.stack.addWidget(self.pic)
        self.stack.addWidget(self.video)
        main.addWidget(self.stack, 1)
        self.info = label(color="mid")
        self.info.setContentsMargins(16, 8, 16, 8)
        main.addWidget(self.info)
        self.panel = label(color="mid", size=10)  # i: what the file and the camera say
        self.panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.panel.setWordWrap(True)
        self.panel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.panel.setContentsMargins(18, 18, 18, 18)
        self.panel.setFixedWidth(360)
        self.panel.setStyleSheet(f"background:{C['panel']}; color:{C['mid']}; font-size:10pt;")
        self.panel.hide()
        h.addWidget(self.panel)
        self.paths: list[Path] = []
        self.i = 0
        self.image: QImage | None = None
        self.cache: dict[Path, QImage] = {}
        self.full: tuple[Path, QImage] | None = None  # the current photo at full size, once zoomed in
        self.loaded.connect(self.got)
        self.described.connect(self.got_info)
        self.jpgs: dict[Path, Path] = {}
        self.cv = threading.Condition()
        self.queue: list[tuple[Path, bool]] = []
        self.size_px = QSize(1600, 1000)
        threading.Thread(target=self.loader, daemon=True).start()
        self.slides = QTimer(self)  # p: the slideshow
        self.slides.setSingleShot(True)
        self.slides.timeout.connect(self.next_slide)
        self.sliding = False

    def show_at(self, paths: list[Path], i: int, meta: dict, jpgs: dict):
        self.paths, self.i, self.meta, self.jpgs = paths, i, meta, jpgs
        self.show_current()

    def show_current(self):
        p = self.paths[self.i]
        self.full = None
        self.update_info()
        if self.panel.isVisible():
            self.ask_info()
        if library.kind(p) in ("video", "audio") and not self.video.m:
            self.image = None
            self.stack.setCurrentWidget(self.pic)
            self.pic.setStyleSheet("background:#000; font-size:16pt;")
            self.pic.setText(span(p.name, "fg", True) + "<br><br>"
                             + span("The video player (libmpv) isn't installed, so this can't play here.", "mid")
                             + "<br>" + span("Press o to open it in its usual app.", "dim"))
        elif library.kind(p) == "video":
            self.image = None
            self.stack.setCurrentWidget(self.video)
            self.video.play(p)
        elif library.kind(p) == "audio":  # plays through mpv; the page shows its name (and cover, if any)
            self.image = None
            self.stack.setCurrentWidget(self.pic)
            self.pic.setText(span("♪", "acc") + "<br><br>" + span(p.stem, "fg", True) + "<br>"
                             + span(fmt_len(self.meta.get(p, {}).get("duration") or 0), "mid"))
            self.pic.setStyleSheet(f"background:#000; font-size:28pt;")
            self.video.play(p)
        else:
            self.pic.setStyleSheet("background:#000;")
            self.video.stop()
            self.stack.setCurrentWidget(self.pic)
            if p in self.cache:
                self.got(p, self.cache[p], False)
            elif self.jpgs.get(p):  # the thumbnail at once, sharp version when it's decoded
                self.image = QImage(str(self.jpgs[p]))
                self.fit()
            else:
                self.image = None
                self.pic.setText(span("loading…", "dim"))
        # only this one, then its neighbours: pictures flipped past quickly are never decoded
        near = [self.paths[k] for k in (self.i, self.i + 1, self.i - 1) if 0 <= k < len(self.paths)]
        self.want([x for x in near if library.kind(x) == "image" and x not in self.cache])
        if self.sliding:
            self.time_slide()

    def want(self, paths: list[Path], full: bool = False):
        with self.cv:
            self.queue = [(p, full) for p in paths]
            self.size_px = self.size() * self.devicePixelRatio()
            self.cv.notify()

    def loader(self):
        """One decoder thread; each new picture replaces what it was going to load next."""
        while True:
            with self.cv:
                while not self.queue:
                    self.cv.wait()
                (p, full), size = self.queue.pop(0), self.size_px
            try:
                with Image.open(p) as im:
                    if not full:
                        im.draft("RGB", (size.width(), size.height()))
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    if not full:
                        im.thumbnail((max(size.width(), 400), max(size.height(), 400)), Image.LANCZOS)
                    q = QImage(im.tobytes(), im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
            except Exception as ex:
                q = f"can't open {p.name}: {ex}"
            thumbs.give_back()
            self.loaded.emit(p, q, full)

    def got(self, p, img, full=False):
        if isinstance(img, QImage):
            if full:
                self.full = (p, img)
            else:
                self.cache[p] = img
                if len(self.cache) > 4:
                    self.cache.pop(next(iter(self.cache)))
        if not self.paths or p != self.paths[self.i]:
            return
        if isinstance(img, str):
            self.pic.setText(span(img, "dim"))
            return
        if self.full and self.full[0] == p and not full:
            return  # already sharper
        self.image = img
        self.pic.set_image(img, keep_view=full or self.pic.zoom > 1)

    def fit(self):
        if self.image is not None:
            self.pic.set_image(self.image)

    def zoom_changed(self):
        """Zoomed in past what the screen-sized picture can show: decode the whole photo, once."""
        p = self.paths[self.i] if self.paths else None
        if p and self.pic.img is not None and not (self.full and self.full[0] == p) \
                and self.pic.scale() * self.devicePixelRatio() > 1.05:  # past one screen pixel per pixel
            self.want([p], full=True)
        self.update_info()

    def zoom_by(self, f: float):
        if self.stack.currentWidget() is self.pic and self.pic.img is not None:
            self.pic.set_zoom(1.0 if f == 0 else self.pic.zoom * f)

    def update_info(self):
        p = self.paths[self.i]
        when = taken(p, self.meta.get(p, {}))
        z = f"   ·   zoom ×{self.pic.zoom:.1f}" if self.pic.img is not None and self.pic.zoom > 1 else ""
        self.info.setText(span(p.name, "fg", True) + span(f"   {self.i + 1} / {len(self.paths)}   ", "mid")
                          + span(f"{p.parent.name}   ·   {when}", "dim") + span(z, "acc")
                          + (span("   ·   slideshow" + (" (paused)" if not self.slides.isActive()
                                                         and library.kind(p) == "image" else ""), "acc")
                             if self.sliding else ""))
        self.changed.emit()

    # ---- i: the info panel
    def toggle_panel(self):
        self.panel.setVisible(not self.panel.isVisible())
        if self.panel.isVisible() and self.paths:
            self.ask_info()
        QTimer.singleShot(0, self.pic.clamp)

    def ask_info(self):
        p = self.paths[self.i]
        self.panel.setText(span("reading…", "dim"))
        threading.Thread(target=lambda: self.described.emit(p, info.describe(p)), daemon=True).start()

    def got_info(self, p, rows):
        if not self.paths or p != self.paths[self.i]:
            return
        html = []
        for k, v in rows:
            if not v:
                html.append(("<br>" if html else "") + span(k, "acc", True))
            else:
                html.append(span(k, "dim") + "<br>&nbsp;&nbsp;" + span(v, "fg"))
        self.panel.setText("<br>".join(html))

    # ---- p: the slideshow
    def start_slides(self):
        self.sliding = True
        self.time_slide()
        self.update_info()

    def stop_slides(self):
        self.sliding = False
        self.slides.stop()
        self.update_info()

    def time_slide(self):
        """Photos stay SLIDE_SECONDS; a video or song plays to its end."""
        p = self.paths[self.i]
        d = self.meta.get(p, {}).get("duration") if library.kind(p) in ("video", "audio") else None
        self.slides.start(int(((d + 0.5) if d else self.SLIDE_SECONDS) * 1000))

    def next_slide(self):
        if not self.sliding:
            return
        if self.i >= len(self.paths) - 1:
            self.stop_slides()
            return
        self.i += 1
        self.show_current()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.pic.clamp)

    def step(self, d: int):
        if self.paths:
            self.i = max(0, min(len(self.paths) - 1, self.i + d))
            self.show_current()

    def keyPressEvent(self, e):
        k, t, ctrl = e.key(), e.text(), bool(e.modifiers() & Qt.ControlModifier)
        video = library.kind(self.paths[self.i]) in ("video", "audio") if self.paths else False
        if ctrl and k in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_by(1.5)
        elif ctrl and k in (Qt.Key_Minus, Qt.Key_Underscore):
            self.zoom_by(1 / 1.5)
        elif ctrl and k == Qt.Key_0:
            self.zoom_by(0)
        elif ctrl and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            self.pic.pan({Qt.Key_Left: -0.15, Qt.Key_Right: 0.15}.get(k, 0), {Qt.Key_Up: -0.15, Qt.Key_Down: 0.15}.get(k, 0))
        elif k in (Qt.Key_Right, Qt.Key_PageDown) and not (video and e.modifiers() & Qt.ShiftModifier):
            self.step(1)
        elif k in (Qt.Key_Left, Qt.Key_PageUp) and not (video and e.modifiers() & Qt.ShiftModifier):
            self.step(-1)
        elif k == Qt.Key_Home:
            self.i = 0
            self.show_current()
        elif k == Qt.Key_End:
            self.i = len(self.paths) - 1
            self.show_current()
        elif k == Qt.Key_Space and self.sliding and not video:
            if self.slides.isActive():
                self.slides.stop()
            else:
                self.time_slide()
            self.update_info()
        elif k == Qt.Key_Space and video:
            self.video.toggle()
            if self.sliding:  # paused video: the slideshow waits
                self.slides.stop() if self.video.m and self.video.m.pause else self.time_slide()
        elif video and k in (Qt.Key_Right, Qt.Key_Left):
            self.video.key("seek", "5" if k == Qt.Key_Right else "-5")
        elif video and t in (",", "."):
            self.video.key("seek", "-1" if t == "," else "1")
        elif command_of(e) in ("move", "undo"):
            self.command.emit(command_of(e))
        elif k in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Return, Qt.Key_Enter):
            if self.sliding:
                self.stop_slides()
            self.video.stop()
            self.back.emit()
        else:
            super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.video.stop()
        self.back.emit()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom_by(1.25 if e.angleDelta().y() > 0 else 1 / 1.25)
        else:
            self.step(-1 if e.angleDelta().y() > 0 else 1)


# ---------------------------------------------------------------- window
class Shoebox(QWidget):
    thumb_ready = Signal(object, object, object)
    update_found = Signal(object, bool)  # (release or None, tell even if none)

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.setWindowTitle("Shoebox")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)

        browse = QSplitter()
        browse.setHandleWidth(1)
        self.tree = Tree()
        self.tree.to_grid.connect(lambda: self.grid_focus())
        self.tree.command.connect(self.command)
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIndentation(16)
        self.tree.setMinimumWidth(300)
        self.tree.currentItemChanged.connect(self.folder_changed)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        self.search = Search()
        self.search.setPlaceholderText("search folders  ( / )")
        self.search.textChanged.connect(self.filter_tree)
        self.search.done.connect(self.search_done)
        lv.addWidget(self.search)
        lv.addWidget(self.tree, 1)
        browse.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.update_bar = label()  # "Shoebox 1.1 is available" (updates.py); hidden until there is one
        self.update_bar.setContentsMargins(18, 10, 18, 10)
        self.update_bar.setStyleSheet(f"background:{C['sel']}; color:{C['acc']};")
        self.update_bar.hide()
        rv.addWidget(self.update_bar)
        self.head = label()
        self.head.setContentsMargins(18, 14, 18, 10)
        rv.addWidget(self.head)
        self.items = Items()
        self.grid = Grid(self.items)
        self.grid.open_item.connect(self.open_viewer)
        self.grid.command.connect(self.command)
        self.grid.to_tree.connect(lambda: self.tree.setFocus())
        self.grid.selectionModel().currentChanged.connect(lambda *_: self.show_keys())
        rv.addWidget(self.grid, 1)
        browse.addWidget(right)
        browse.setStretchFactor(1, 1)
        browse.setSizes([int(settings().get("pane", 400)), 1200])  # the folder pane keeps the width you drag it to
        self.pane_save = QTimer(self)
        self.pane_save.setSingleShot(True)
        self.pane_save.setInterval(400)
        self.pane_save.timeout.connect(lambda: save_settings({**settings(), "pane": browse.sizes()[0]}))
        browse.splitterMoved.connect(lambda *_: self.pane_save.start())
        self.pages.addWidget(browse)

        self.viewer = Viewer()
        self.viewer.back.connect(self.close_viewer)
        self.viewer.changed.connect(self.show_keys)
        self.viewer.command.connect(self.command)
        self.pages.addWidget(self.viewer)

        self.keys = label(color="dim", size=10)
        self.keys.setContentsMargins(16, 6, 16, 6)
        self.keys.setStyleSheet(f"color:{C['dim']}; font-size:10pt; background:{C['panel']};")
        outer.addWidget(self.keys)

        self.thumb_ready.connect(self.items.got)
        self.reorder = QTimer(self)  # after a scroll: make what's on screen first
        self.reorder.setSingleShot(True)
        self.reorder.setInterval(80)
        self.reorder.timeout.connect(self.ask_thumbs)
        self.grid.verticalScrollBar().valueChanged.connect(lambda *_: self.reorder.start())
        self.maker = thumbs.Maker(lambda p, jpg, meta: self.thumb_ready.emit(p, jpg, meta))
        QShortcut(QKeySequence("F"), self, self.toggle_full)
        QShortcut(QKeySequence("F11"), self, self.toggle_full)
        QShortcut(QKeySequence("O"), self, self.open_external)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_folder)
        QShortcut(QKeySequence("D"), self, self.open_folder)
        QShortcut(QKeySequence("Q"), self, QApplication.quit)
        QApplication.instance().focusChanged.connect(self.focus_moved)
        QShortcut(QKeySequence("F5"), self, self.reload)
        QShortcut(QKeySequence("R"), self, self.reload)
        QShortcut(QKeySequence("S"), self, self.open_settings)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence("/"), self, self.start_search)
        QShortcut(QKeySequence("Ctrl+F"), self, self.start_search)
        QShortcut(QKeySequence("U"), self, self.update_now)
        QShortcut(QKeySequence("I"), self, self.key_i)
        QShortcut(QKeySequence("P"), self, self.slideshow)
        QShortcut(QKeySequence("Shift+D"), self, self.open_dupes)
        QShortcut(QKeySequence("T"), self, self.turn)
        QShortcut(QKeySequence("Ctrl+Z"), self, lambda: self.command("undo"))
        self.ingest = self.dupes = None
        self.update_found.connect(self.got_update)
        self.release = None
        self.reload()
        self.tree.setFocus()
        if settings().get("check_updates", True) and not updates.is_disabled():
            self.check_updates()

    def key_i(self):
        """i: the info panel when viewing, else Ingest."""
        if self.pages.currentWidget() is self.viewer:
            self.viewer.toggle_panel()
        else:
            self.open_ingest()

    def slideshow(self):
        """p: full screen, one after another, from the photo you're on (or the start of the folder)."""
        if self.pages.currentWidget() is self.viewer:
            if self.viewer.sliding:
                self.viewer.stop_slides()
                return
        elif self.pages.currentIndex() == 0 and self.items.paths:
            i = self.grid.currentIndex()
            self.open_viewer(i.row() if self.side == "photos" and i.isValid() else 0)
        else:
            return
        if not self.isFullScreen():
            self.was_full = False
            self.showFullScreen()
        self.viewer.start_slides()

    # ---- open with: Shoebox as the app a photo opens in (shoebox photo.jpg, or the system's Open with)
    def open_file(self, p: Path):
        """Show p full size with the rest of its folder around it. In the library, its folder is selected in the
        tree as usual; outside it, Shoebox just looks (the folder isn't added to the library or remembered)."""
        p = p.resolve()
        it = None
        if self.root:
            try:
                p.relative_to(self.root.resolve())
                it = self.find(("folder", library.Folder(p.parent, p.parent.name)))
            except ValueError:
                pass
        if it:
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it, QAbstractItemView.PositionAtCenter)
        else:
            try:
                files = sorted((x for x in p.parent.iterdir() if library.kind(x) and not x.name.startswith(".")),
                               key=lambda x: x.name.lower())
            except OSError:
                files = [p]
            self.items.set_paths(files)
            for x in files:
                hit = thumbs.cached(x)
                if hit:
                    self.items.got(x, *hit)
            self.head.setText(span(p.parent.name, "fg", True) + span(f"   {p.parent}", "dim")
                              + span("   (not in your library: just looking)", "mid"))
            self.ask_thumbs()
        row = self.items.row.get(p)
        if row is None:
            self.say(f"can't show {p.name}", "bad")
            return
        self.side = "photos"
        self.grid.setCurrentIndex(self.items.index(row))
        self.open_viewer(row)

    # ---- organize (organize.py): n new event, F2 / e rename, m move, z undo
    def command(self, what: str):
        if not self.root or self.pages.currentWidget() not in (self.pages.widget(0), self.viewer):
            return
        try:
            {"new": self.new_event, "rename": self.rename_event, "move": self.move_files, "undo": self.undo}[what]()
        except (OSError, ValueError) as ex:
            self.say(str(ex), "bad")

    def say(self, text: str, color: str = "acc"):
        """A message in the keys bar until the next key."""
        self.keys.setText(span(text, color))

    def selected_event(self):
        it = self.tree.currentItem()
        kind, v = it.data(0, Qt.UserRole) if it else (None, None)
        return it, kind, v

    def rename_event(self):
        it, kind, v = self.selected_event()
        if kind != "folder" or v.name == "loose files" or v.path == self.root:
            self.say("pick an event folder to rename", "warn")
            return
        d = Ask(self, "Rename", [("new name", v.path.name)],
                "Only the folder's name changes; the photos stay in it. z puts the old name back.")
        if d.exec() and d.values()[0].strip() != v.path.name:
            new = organize.rename_event(v.path, d.values()[0])
            self.reload_at(new)
            self.say(f"renamed to {new.name}   (z undoes)")

    def new_event(self):
        it, kind, v = self.selected_event()
        now = datetime.now()
        y, m = now.year, now.month
        if kind == "folder" and v.month:
            y, m = int(v.year), v.month
        elif kind == "month":
            y, m = int(v[0]), v[1]
        elif kind == "year" and str(v).isdigit():
            y = int(v)
        d = Ask(self, "New event", [("month (year-month)", f"{y:04d}-{m:02d}"), ("name", "")],
                f"Makes an empty folder in {self.root} / year / month. Then move photos into it with m.")
        if not d.exec():
            return
        when, name = d.values()
        mt = re.match(r"^\s*(\d{4})\D+(\d{1,2})\s*$", when)
        if not mt or not 1 <= int(mt.group(2)) <= 12:
            raise ValueError("the month should look like 2026-06")
        path = organize.new_event(self.root, int(mt.group(1)), int(mt.group(2)), name)
        self.reload_at(path)
        self.say(f"made {path.name}: it shows once it has photos.  m on photos moves them here   (z undoes)")
        self.made = path

    made: Path | None = None  # a new, still empty event: offered first when moving

    def events(self) -> list[tuple[str, Path]]:
        """Every event and subfolder, as "2026 · 06 June · Grand Teton", for the move list."""
        out = []
        if self.made and self.made.is_dir():
            out.append((f"{self.made.parent.parent.name} · {self.made.parent.name} · {self.made.name}   (new)", self.made))

        def add(f: library.Folder, prefix: str):
            name = f"{prefix}{f.name}"
            if f.path not in [p for _, p in out]:
                out.append((name, f.path))
            for c in f.children:
                add(c, name + " / ")
        for f in self.folders:
            when = f"{f.year} · {f.month:02d} {library.MONTHS[f.month - 1]} · " if f.month else f"{f.year} · "
            add(f, when)
        return out

    def move_files(self):
        viewing = self.pages.currentWidget() is self.viewer
        if viewing:
            files = [self.viewer.paths[self.viewer.i]] if self.viewer.paths else []
        else:
            if self.side != "photos":
                self.say("m moves photos: go to the photos first", "warn")
                return
            rows = sorted({i.row() for i in self.grid.selectionModel().selectedIndexes()}) or \
                ([self.grid.currentIndex().row()] if self.grid.currentIndex().isValid() else [])
            files = [self.items.paths[r] for r in rows]
        if not files:
            return
        if viewing:
            self.viewer.video.stop()
        what = files[0].name if len(files) == 1 else f"{len(files)} files"
        d = PickEvent(self, f"Move {what} to…", self.events())
        if not d.exec() or not d.chosen:
            return
        done = organize.move(files, d.chosen)
        if viewing:  # carry on with the next one
            gone = {a for a, _ in done}
            i = self.viewer.i
            self.viewer.paths = [x for x in self.viewer.paths if x not in gone]
            if not self.viewer.paths:
                self.close_viewer()
            else:
                self.viewer.i = min(i, len(self.viewer.paths) - 1)
                self.viewer.show_current()
        self.reload_keep()
        self.say(f"moved {what} to {d.chosen.name}   (z undoes)")

    def undo(self):
        what = organize.undo()
        if self.pages.currentWidget() is self.viewer:
            self.close_viewer()
        self.reload_keep()
        self.say(f"undone: {what}")

    def reload_at(self, path: Path):
        """Reload the folders and land on the one at path (if it has anything in it)."""
        self.reload()
        it = self.find(("folder", library.Folder(path, path.name)))
        if it:
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it, QAbstractItemView.PositionAtCenter)
        self.tree.setFocus()

    def reload_keep(self):
        """Reload, staying on the same folder and roughly the same photo."""
        row = self.grid.currentIndex().row()
        self.reload()
        if self.items.paths and row >= 0:
            self.grid.setCurrentIndex(self.items.index(min(row, len(self.items.paths) - 1)))
        if self.side == "photos" and self.pages.currentIndex() == 0:
            self.grid.setFocus()

    # ---- ingest (ingest.py)
    def open_ingest(self):
        if self.pages.currentWidget() is not self.pages.widget(0):
            return
        if self.ingest is None:
            from .ingest import Ingest
            self.ingest = Ingest(self)
            self.ingest.back.connect(self.close_ingest)
            self.ingest.moved.connect(lambda _b: self.reload())
            self.pages.addWidget(self.ingest)
        it = self.tree.currentItem()
        kind, v = it.data(0, Qt.UserRole) if it else (None, None)
        self.pages.setCurrentWidget(self.ingest)
        self.ingest.grid.setFocus()
        self.show_keys()
        self.ingest.start(v.path if kind == "folder" and v.name != "loose files" else None)

    def open_dupes(self):
        """Duplicates (dupes.py) in whatever's selected: an event, a month, a year."""
        if self.pages.currentWidget() is not self.pages.widget(0) or not self.tree.currentItem():
            return
        if self.dupes is None:
            from .dupes import Dupes
            self.dupes = Dupes(self)
            self.dupes.back.connect(self.close_ingest)
            self.dupes.changed.connect(self.reload)
            self.pages.addWidget(self.dupes)
        it = self.tree.currentItem()
        self.pages.setCurrentWidget(self.dupes)
        self.dupes.setFocus()
        self.show_keys()
        self.dupes.start(it.text(0).strip(), self.files_of(it))

    def close_ingest(self):
        self.pages.setCurrentIndex(0)
        self.tree.setFocus()
        self.show_keys()

    # ---- updates
    def check_updates(self, tell=False):
        """In the background; tell: say so even when there's nothing new (the Settings button)."""
        threading.Thread(target=lambda: self.update_found.emit(updates.check(), tell), daemon=True).start()

    def got_update(self, rel, tell):
        self.release = rel
        if rel:
            how = "u installs it" if updates.can_self_update(rel) else "u opens the download page"
            self.update_bar.setText(span(f"Shoebox {rel['version']} is available", "acc", True)
                                    + span(f"   (you have {__version__}):  {how}", "mid"))
            self.update_bar.show()
        elif tell:
            self.update_bar.setText(span(f"Shoebox {__version__} is the newest version.", "mid"))
            self.update_bar.show()
            QTimer.singleShot(5000, self.update_bar.hide)

    def update_now(self):
        if not self.release:
            return
        if updates.can_self_update(self.release):
            self.update_bar.setText(span("Downloading the update…", "acc"))
            QApplication.processEvents()
            try:
                if updates.install(self.release):
                    QApplication.quit()  # the installer replaces Shoebox and opens it again
            except Exception as ex:
                self.update_bar.setText(span(f"The update didn't download: {ex}", "bad"))
        else:
            updates.install(self.release)

    # ---- tree
    def reload(self):
        cur = self.tree.currentItem()
        was = cur.data(0, Qt.UserRole) if cur else None
        self.tree.clear()
        folders = library.scan(self.root) if self.root and self.root.is_dir() else []
        self.folders = folders
        if not self.root:
            self.head.setText(span("Welcome to Shoebox.", "fg", True)
                              + span("   Press s (Settings) to choose your photos folder.", "mid"))
        elif not folders:
            self.head.setText(span(f"nothing found in {self.root}", "dim")
                              + span("   (s: choose another folder)", "mid"))
        years, months = {}, {}
        first = None
        for f in folders:
            if f.year not in years:
                y = QTreeWidgetItem(self.tree, [f.year, ""])
                y.setData(0, Qt.UserRole, ("year", f.year))
                y.setFont(0, self.bold())
                years[f.year] = y
            parent = years[f.year]
            if f.month:
                mk = (f.year, f.month)
                if mk not in months:
                    m = QTreeWidgetItem(parent, [f"{f.month:02d}  {library.MONTHS[f.month - 1]}", ""])
                    m.setData(0, Qt.UserRole, ("month", mk))
                    months[mk] = m
                parent = months[mk]
            item = self.add_folder(parent, f, show_day=bool(f.month))
            first = first or item
        for it in years.values():
            it.setText(1, str(self.count(it)))
        for it in months.values():
            it.setText(1, str(self.count(it)))
        self.tree.resizeColumnToContents(1)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, self.tree.header().ResizeMode.Stretch)
        for i in range(self.tree.topLevelItemCount()):  # newest year and month open, like Picasa's recent
            if i == 0:
                y = self.tree.topLevelItem(0)
                y.setExpanded(True)
                if y.childCount():
                    y.child(0).setExpanded(True)
        target = self.find(was) if was else self.find_key(settings().get("last"))  # where you left off
        self.tree.setCurrentItem(target or first)
        self.tree.scrollToItem(target or first, QAbstractItemView.PositionAtCenter)

    # ---- settings
    def open_settings(self):
        if self.pages.currentWidget() is self.viewer:
            return
        Settings(self).exec()

    def set_root(self, root: Path):
        self.root = root
        save_settings({**settings(), "root": str(root)})
        self.search.clear()
        self.items.set_paths([])
        self.reload()
        self.tree.setFocus()

    # ---- search
    def start_search(self):
        if self.pages.currentWidget() is self.viewer:
            return
        self.search.setFocus()
        self.search.selectAll()

    def filter_tree(self, text: str):
        """Show folders whose name has the text (and everything under a matching year, month or folder)."""
        q = text.strip().lower()

        def walk(it: QTreeWidgetItem, shown_by_parent: bool) -> bool:
            hit = shown_by_parent or not q or q in it.text(0).lower()
            child_hit = False
            for i in range(it.childCount()):
                child_hit |= walk(it.child(i), hit)
            visible = hit or child_hit
            it.setHidden(not visible)
            if q and child_hit:
                it.setExpanded(True)
            return visible
        first = None
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i), False)
        if q:  # land on the first matching folder
            it = self.tree.topLevelItem(0)
            while it:
                if not it.isHidden() and q in it.text(0).lower():
                    first = it
                    break
                it = self.tree.itemBelow(it)
            if first:
                self.tree.setCurrentItem(first)

    def search_done(self, keep: bool):
        """Enter or ↓: keep the filter and go to the folders. Esc: clear it."""
        if not keep:
            self.search.clear()
        self.tree.setFocus()

    def bold(self) -> QFont:
        f = QFont(FONT, 11)
        f.setWeight(QFont.DemiBold)
        return f

    def add_folder(self, parent, f: library.Folder, show_day: bool) -> QTreeWidgetItem:
        text = (f"{f.day}  " if show_day and f.day else "") + f.name
        it = QTreeWidgetItem(parent, [text, str(f.count())])
        it.setData(0, Qt.UserRole, ("folder", f))
        it.setForeground(1, QColor(C["dim"]))
        it.setToolTip(0, str(f.path))
        for c in f.children:
            self.add_folder(it, c, False)
        return it

    def count(self, it: QTreeWidgetItem) -> int:
        kind, v = it.data(0, Qt.UserRole)
        if kind == "folder":
            return v.count()
        return sum(self.count(it.child(i)) for i in range(it.childCount()))

    def find(self, data) -> QTreeWidgetItem | None:
        def walk(it):
            d = it.data(0, Qt.UserRole)
            if d and (d == data or (d[0] == "folder" and data[0] == "folder" and d[1].path == data[1].path)):
                return it
            for i in range(it.childCount()):
                got = walk(it.child(i))
                if got:
                    return got
            return None
        for i in range(self.tree.topLevelItemCount()):
            got = walk(self.tree.topLevelItem(i))
            if got:
                return got
        return None

    @staticmethod
    def key_of(data) -> list:
        """A tree item as something settings.json can hold."""
        kind, v = data
        if kind == "folder":
            return ["folder", str(v.path), v.name]
        return [kind, *v] if kind == "month" else [kind, v]

    def find_key(self, key) -> QTreeWidgetItem | None:
        if not key:
            return None
        it = self.tree.topLevelItem(0)
        while it:
            if self.key_of(it.data(0, Qt.UserRole)) == key:
                return it
            it = self._next(it)
        return None

    def _next(self, it: QTreeWidgetItem) -> QTreeWidgetItem | None:
        """The item after it in the whole tree, closed branches included."""
        if it.childCount():
            return it.child(0)
        while it:
            parent = it.parent()
            siblings = parent.childCount() if parent else self.tree.topLevelItemCount()
            i = (parent.indexOfChild(it) if parent else self.tree.indexOfTopLevelItem(it)) + 1
            if i < siblings:
                return parent.child(i) if parent else self.tree.topLevelItem(i)
            it = parent
        return None

    def remember(self, it: QTreeWidgetItem):
        try:
            save_settings({**settings(), "last": self.key_of(it.data(0, Qt.UserRole))})
        except OSError:
            pass

    def files_of(self, it: QTreeWidgetItem) -> list[Path]:
        kind, v = it.data(0, Qt.UserRole)
        if kind == "folder":
            return v.all_files()
        out = []
        for i in range(it.childCount()):
            out += self.files_of(it.child(i))
        return out

    def folder_changed(self, it, _prev=None):
        if not it:
            return
        self.remember(it)
        files = self.files_of(it)
        self.items.set_paths(files)
        kind, v = it.data(0, Qt.UserRole)
        if kind == "folder":
            title = v.name
            when = (f"{library.MONTHS[v.month - 1]} {int(v.day)}, {v.year}" if v.day else
                    f"{library.MONTHS[v.month - 1]} {v.year}") if v.month else v.year
        elif kind == "month":
            title, when = f"{library.MONTHS[v[1] - 1]} {v[0]}", ""
        else:
            title, when = v, ""
        n_vid = sum(library.kind(p) == "video" for p in files)
        n_aud = sum(library.kind(p) == "audio" for p in files)
        self.head.setText(span(title, "fg", True) + span(f"   {when}" if when else "", "mid")
                          + span(f"   {len(files) - n_vid - n_aud} photos · {n_vid} videos"
                                 + (f" · {n_aud} audio" if n_aud else ""), "dim"))
        for p in files:
            if p not in self.items.jpg:
                hit = thumbs.cached(p)
                if hit:
                    self.items.got(p, *hit)
        self.ask_thumbs()
        if files:
            self.grid.setCurrentIndex(self.items.index(0))
            self.grid.scrollToTop()
        self.show_keys()

    def ask_thumbs(self):
        """Thumbnails still to make, the ones on screen first, then below, then above. Ones scrolled past
        quickly drop out of the queue instead of holding up the rest."""
        paths = self.items.paths
        missing = [i for i, p in enumerate(paths) if p not in self.items.jpg]
        if not missing:
            self.maker.ask([])
            return
        vp = self.grid.viewport()
        top = self.grid.indexAt(QPoint(4, 4))
        bottom = self.grid.indexAt(QPoint(vp.width() - 4, vp.height() - 4))
        r0 = top.row() if top.isValid() else 0
        r1 = bottom.row() if bottom.isValid() else min(len(paths) - 1, r0 + 60)
        span_ = r1 - r0 + 1
        on = [i for i in missing if r0 <= i <= r1]
        below = [i for i in missing if r1 < i <= r1 + span_ * 2]
        above = [i for i in missing if r0 - span_ <= i < r0]
        first = set(on + below + above)
        rest = [i for i in missing if i not in first]
        self.maker.ask([paths[i] for i in on + below + above + rest])

    def grid_focus(self):
        if self.items.paths:
            self.grid.setFocus()
            if not self.grid.currentIndex().isValid():
                self.grid.setCurrentIndex(self.items.index(0))
        self.show_keys()

    # ---- viewer
    def open_viewer(self, row: int):
        self.pages.setCurrentWidget(self.viewer)
        self.viewer.setFocus()
        self.viewer.show_at(self.items.paths, row, self.items.meta, self.items.jpg)
        self.show_keys()

    def close_viewer(self):
        self.viewer.want([])
        self.grid.setCurrentIndex(self.items.index(self.viewer.i))
        self.pages.setCurrentIndex(0)
        if self.isFullScreen() and not self.was_full:
            self.showNormal()
        self.grid.setFocus()
        self.show_keys()

    def toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.was_full = self.pages.currentWidget() is not self.viewer
            self.showFullScreen()

    was_full = False
    side = "folders"  # where you are: "folders" or "photos" (d shows the folder, or the photo selected)

    def current_path(self) -> Path | None:
        if self.pages.currentWidget() is self.viewer and self.viewer.paths:
            return self.viewer.paths[self.viewer.i]
        i = self.grid.currentIndex()
        return self.items.paths[i.row()] if i.isValid() else None

    def turn(self):
        """t: the photo (or every selected one) a quarter turn clockwise, saved (rotate.py); again for more."""
        viewing = self.pages.currentWidget() is self.viewer
        if viewing:
            files = [self.viewer.paths[self.viewer.i]] if self.viewer.paths else []
        elif self.pages.currentIndex() == 0 and self.side == "photos":
            rows = sorted({i.row() for i in self.grid.selectionModel().selectedIndexes()})
            files = [self.items.paths[r] for r in rows] or ([self.current_path()] if self.current_path() else [])
        else:
            return
        files = [f for f in files if library.kind(f) == "image"]
        for p in files:
            if not rotate.can_rotate(p):
                self.say(f"{p.suffix} photos can't be turned", "warn")
                continue
            try:
                rotate.rotate(p)
            except Exception as ex:
                self.say(f"couldn't turn {p.name}: {ex}", "bad")
                continue
            self.items.pix.pop(p, None)  # the grid makes a new thumbnail
            self.items.jpg.pop(p, None)
            self.viewer.cache.pop(p, None)
            if viewing and self.viewer.image is not None and self.viewer.paths[self.viewer.i] == p:
                self.viewer.full = None
                self.viewer.image = self.viewer.image.transformed(QTransform().rotate(90))  # at once, then sharp
                self.viewer.fit()
                self.viewer.want([p])
        self.ask_thumbs()

    def open_external(self):
        p = self.current_path()
        if p:
            self.viewer.video.stop()
            system.open_path(p)

    def open_folder(self):
        """d: the file manager (Dolphin, Explorer, Finder), at the folder, or with the photo selected."""
        in_folders = self.pages.currentWidget() is not self.viewer and self.side == "folders"
        if in_folders:
            it = self.tree.currentItem()
            kind, v = it.data(0, Qt.UserRole) if it else (None, None)
            if kind == "folder" or self.root:
                system.open_path(v.path if kind == "folder" else self.root)
            return
        p = self.current_path()
        if p:
            system.show_in_file_manager(p)

    def show_keys(self, *_):
        if self.ingest is not None and self.pages.currentWidget() is self.ingest:
            keys = self.ingest.keys()
        elif self.dupes is not None and self.pages.currentWidget() is self.dupes:
            keys = self.dupes.keys()
        elif self.pages.currentWidget() is self.viewer:
            video = self.viewer.paths and library.kind(self.viewer.paths[self.viewer.i]) in ("video", "audio")
            keys = [("VIEWING", ""), ("←→", "previous / next"), ("home end", "first / last")]
            if video:
                keys += [("space", "play / pause"), ("shift ←→", "5 s"), (", .", "1 s")]
            else:
                keys += [("ctrl + −", "zoom"), ("ctrl ←→↑↓", "move")] if self.viewer.pic.zoom > 1 else [("ctrl +", "zoom")]
                keys += [("t", "turn")]
            keys += [("m", "move"), ("i", "info"), ("p", "stop slideshow" if self.viewer.sliding else "slideshow")]
            if self.viewer.sliding:
                keys += [("space", "pause")] if not video else []
            keys += [("o", "open in its app"), ("d", "show in file manager"), ("f", "full screen"),
                     ("esc", "back to thumbnails"), ("q", "quit")]
        elif self.search.hasFocus():
            keys = [("SEARCH", ""), ("type", "filter folders"), ("enter ↓", "to the folders"), ("esc", "clear")]
        elif self.grid.hasFocus():
            keys = [("PHOTOS", ""), ("arrows", "move"), ("enter", "view"), ("+ −", "size"), ("t", "turn"), ("m", "move to…"), ("shift ctrl", "pick several"), ("p", "slideshow"), ("z", "undo"), ("o", "open in its app"),
                    ("d", "show in file manager"), ("esc", "back to folders"), ("f", "full screen"), ("q", "quit")]
        else:
            keys = [("FOLDERS", ""), ("↑↓", "move"), ("←", "fold"), ("→", "unfold, then to the photos"), ("enter", "open / close, or to the photos"),
                    ("/", "search"), ("n", "new event"), ("F2", "rename"), ("z", "undo"), ("p", "slideshow"), ("i", "ingest"), ("D", "duplicates"), ("d", "open in file manager"), ("s", "settings"), ("r", "reload"), ("f", "full screen"), ("esc q", "quit")]
        self.keys.setText("   ".join(span(k, "acc" if not d else "mid", True) + (span(f" {d}", "dim") if d else "")
                                     for k, d in keys))

    def focus_moved(self, _old, new):
        # which side you're on: a click elsewhere (a dialog, the search box) keeps the last one
        if new is self.grid or new is self.tree:
            self.side = "photos" if new is self.grid else "folders"
        self.grid.viewport().update()  # the outline shows only while you're in the thumbnails
        self.show_keys()

    def closeEvent(self, e):
        self.viewer.video.stop()
        super().closeEvent(e)


DIALOG_QSS = (f"QDialog {{ background: {C['panel']}; }} QPushButton {{ background: {C['cur']}; color: {C['fg']}; "
              f"border: 1px solid {C['line']}; padding: 7px 14px; }} "
              f"QPushButton:focus, QPushButton:hover {{ border-color: {C['acc']}; }}")


class Ask(QDialog):
    """A small question with text boxes: Enter OKs, Esc cancels. fields: [(label, starting text)]."""

    def __init__(self, win, title: str, fields: list[tuple[str, str]], note: str = ""):
        super().__init__(win)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.setStyleSheet(DIALOG_QSS)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(8)
        v.addWidget(label(span(title, "fg", True), size=13))
        self.boxes = []
        for name, text in fields:
            v.addWidget(label(span(name.upper(), "dim")))
            box = QLineEdit(text)
            box.returnPressed.connect(self.accept)
            v.addWidget(box)
            self.boxes.append(box)
        if note:
            n = label(span(note, "dim"), size=10)
            n.setWordWrap(True)
            v.addWidget(n)
        v.addWidget(label(span("enter", "acc", True) + span(" ok    ", "dim") + span("esc", "acc", True)
                          + span(" cancel", "dim"), size=10))
        self.boxes[-1].setFocus()
        self.boxes[-1].selectAll()

    def values(self) -> list[str]:
        return [b.text() for b in self.boxes]


class PickEvent(QDialog):
    """Choose an event to move photos to: type to narrow the list, ↑↓, Enter."""

    def __init__(self, win, title: str, events: list[tuple[str, Path]]):
        super().__init__(win)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 560)
        self.setStyleSheet(DIALOG_QSS)
        self.events, self.chosen = events, None
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(8)
        v.addWidget(label(span(title, "fg", True), size=13))
        self.box = QLineEdit()
        self.box.setPlaceholderText("type to find an event…")
        self.box.textChanged.connect(self.fill)
        self.box.installEventFilter(self)
        v.addWidget(self.box)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _i: self.pick())
        v.addWidget(self.list, 1)
        v.addWidget(label(span("↑↓", "acc", True) + span(" choose    ", "dim") + span("enter", "acc", True)
                          + span(" move here    ", "dim") + span("esc", "acc", True) + span(" cancel", "dim"), size=10))
        self.fill("")
        self.box.setFocus()

    def fill(self, text: str):
        q = text.strip().lower()
        self.list.clear()
        for name, path in self.events:
            if all(w in name.lower() for w in q.split()):
                it = QListWidgetItem(name)
                it.setData(Qt.UserRole, path)
                self.list.addItem(it)
        self.list.setCurrentRow(0)

    def eventFilter(self, obj, e):
        if obj is self.box and e.type() == QEvent.KeyPress:
            if e.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                QApplication.sendEvent(self.list, e)
                return True
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.pick()
                return True
        return super().eventFilter(obj, e)

    def pick(self):
        it = self.list.currentItem()
        if it:
            self.chosen = it.data(Qt.UserRole)
            self.accept()


class Settings(QDialog):
    """The media folder (if it moves), and the thumbnail cache."""

    def __init__(self, win: "Shoebox"):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Shoebox settings")
        self.setMinimumWidth(640)
        self.setStyleSheet(f"QDialog {{ background: {C['panel']}; }} QPushButton {{ background: {C['cur']}; "
                           f"color: {C['fg']}; border: 1px solid {C['line']}; padding: 7px 14px; }} "
                           f"QPushButton:focus, QPushButton:hover {{ border-color: {C['acc']}; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        v.addWidget(label(span("MEDIA FOLDER", "dim")))
        self.path = label()
        self.path.setWordWrap(True)
        v.addWidget(self.path)
        row = QHBoxLayout()
        change = QPushButton("Choose a folder…")
        change.clicked.connect(self.change)
        row.addWidget(change)
        row.addStretch(1)
        v.addLayout(row)
        v.addSpacing(14)
        v.addWidget(label(span("THUMBNAILS", "dim")))
        self.cache = label()
        self.cache.setWordWrap(True)
        v.addWidget(self.cache)
        row2 = QHBoxLayout()
        clear = QPushButton("Clear thumbnails")
        clear.clicked.connect(self.clear)
        row2.addWidget(clear)
        row2.addStretch(1)
        v.addLayout(row2)
        v.addSpacing(14)
        v.addWidget(label(span("UPDATES", "dim")))
        v.addWidget(label(span(f"Shoebox {__version__}", "mid")))
        row3 = QHBoxLayout()
        self.auto = QPushButton()
        self.auto.clicked.connect(self.toggle_auto)
        row3.addWidget(self.auto)
        now = QPushButton("Check now")
        now.clicked.connect(lambda: self.win.check_updates(tell=True))
        row3.addWidget(now)
        row3.addStretch(1)
        v.addLayout(row3)
        v.addSpacing(14)
        close = QPushButton("Done")
        close.clicked.connect(self.accept)
        v.addWidget(close, 0, Qt.AlignRight)
        self.show_state()
        change.setFocus()

    def toggle_auto(self):
        save_settings({**settings(), "check_updates": not settings().get("check_updates", True)})
        self.show_state()

    def show_state(self):
        self.auto.setText("Check for updates when Shoebox starts: " + ("on" if settings().get("check_updates", True)
                                                                        else "off"))
        r = self.win.root
        if not r:
            self.path.setText(span("none yet: choose the folder with your photos and videos", "mid"))
        else:
            self.path.setText(span(str(r), "fg" if r.is_dir() else "bad")
                              + ("" if r.is_dir() else span("   (not found)", "dim")))
        size = sum(f.stat().st_size for f in thumbs.CACHE.rglob("*") if f.is_file()) if thumbs.CACHE.exists() else 0
        self.cache.setText(span(f"{size / 1e6:.0f} MB in {thumbs.CACHE}", "mid")
                           + span("   (made again when needed; your photos aren't touched)", "dim"))

    def change(self):
        d = QFileDialog.getExistingDirectory(self, "Choose your media folder", str(self.win.root or Path.home()))
        if d:
            self.pick(Path(d))

    def pick(self, root: Path):
        self.win.set_root(root)
        self.show_state()

    def clear(self):
        shutil.rmtree(thumbs.CACHE, ignore_errors=True)
        self.win.items.jpg.clear()
        self.win.items.pix.clear()
        self.win.folder_changed(self.win.tree.currentItem())
        self.show_state()


class Search(QLineEdit):
    done = Signal(bool)  # True: keep the filter

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
            self.done.emit(True)
        elif e.key() == Qt.Key_Escape:
            self.done.emit(False)
        else:
            super().keyPressEvent(e)


class Tree(QTreeWidget):
    """Enter (or a double-click) opens or closes a year, month or folder with subfolders, and goes to the
    thumbnails of a folder with only photos. → on an open or photos-only folder goes to the thumbnails."""
    to_grid = Signal()
    command = Signal(str)

    def mouseDoubleClickEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        if it and not it.childCount():
            self.to_grid.emit()
        else:
            super().mouseDoubleClickEvent(e)  # toggles it

    def keyPressEvent(self, e):
        it = self.currentItem()
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and it:
            if it.childCount():
                it.setExpanded(not it.isExpanded())
            else:
                self.to_grid.emit()
        elif e.key() == Qt.Key_Right and it and (it.isExpanded() or not it.childCount()):
            self.to_grid.emit()
        elif e.key() == Qt.Key_Escape:  # viewer -> photos -> folders -> quit: Esc all the way out
            QApplication.quit()
        elif command_of(e) in ("new", "rename", "undo"):
            self.command.emit(command_of(e))
        else:
            super().keyPressEvent(e)


def main():
    if "--selftest" in sys.argv:  # used by the Windows/macOS builds; see selftest.py
        from . import selftest
        i = sys.argv.index("--selftest")
        out = Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else Path("shoebox-selftest.txt")
        os._exit(selftest.run(out))
    QApplication.setApplicationName("Shoebox")
    QApplication.setDesktopFileName("shoebox")
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setWindowIcon(QIcon(str(ICON)))
    arg = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    opened = arg if arg and arg.is_file() else None  # shoebox photo.jpg (Open with)
    root = arg if arg and arg.is_dir() else ROOT  # shoebox some/folder: look at that folder this once
    w = Shoebox(root)
    w.resize(1600, 980)  # the size it comes back to if you un-maximize it
    w.showMaximized()
    if opened:
        QTimer.singleShot(0, lambda: w.open_file(opened))
    elif not root:  # first start: pick the photos folder
        QTimer.singleShot(300, w.open_settings)

    class OpenEvents(QObject):  # macOS sends a file opened with Shoebox as an event, not an argument
        def eventFilter(self, obj, e):
            if e.type() == QEvent.FileOpen and e.file():
                w.open_file(Path(e.file()))
                return True
            return False
    app.installEventFilter(opener := OpenEvents())
    code = app.exec()
    os._exit(code)  # don't wait for thumbnail workers
