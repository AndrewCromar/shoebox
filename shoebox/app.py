"""The window: folders by year and month on the left, thumbnails on the right, a full-size viewer on Enter.

Looks like the drew.in.nature studio (same colours and font). Works with the keyboard or the mouse.
Read-only: it never moves, renames or edits a photo.
"""
import json
import locale
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
from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QColor, QFont, QImage, QKeySequence, QOpenGLContext, QPainter, QPixmap, QShortcut
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QPushButton, QHBoxLayout, QLabel, QLineEdit, QListView, QSplitter,
                               QStackedWidget, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from . import __version__, library, thumbs, updates

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
     "fg": "#e8e6df", "mid": "#a3a69d", "dim": "#5d625a", "acc": "#cfe3a8", "keep": "#7fbf6a", "cyan": "#8fc1c9"}
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

    def __init__(self, model: Items):
        super().__init__()
        self.setModel(model)
        self.cell = Cell(model)
        self.setItemDelegate(self.cell)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)  # one at a time until there's a use for more
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


class Viewer(QWidget):
    """One photo or video, filling the window. ←→ next/previous, Esc back to the grid."""
    loaded = Signal(object, object)  # (path, QImage or error text)
    back = Signal()
    changed = Signal()  # another photo/video: the keys bar follows

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.stack = QStackedWidget()
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setStyleSheet("background:#000;")
        self.pic.setMinimumSize(1, 1)
        self.video = Mpv()
        self.stack.addWidget(self.pic)
        self.stack.addWidget(self.video)
        v.addWidget(self.stack, 1)
        self.info = label(color="mid")
        self.info.setContentsMargins(16, 8, 16, 8)
        v.addWidget(self.info)
        self.paths: list[Path] = []
        self.i = 0
        self.image: QImage | None = None
        self.cache: dict[Path, QImage] = {}
        self.loaded.connect(self.got)
        self.jpgs: dict[Path, Path] = {}
        self.cv = threading.Condition()
        self.queue: list[Path] = []
        self.size_px = QSize(1600, 1000)
        threading.Thread(target=self.loader, daemon=True).start()

    def show_at(self, paths: list[Path], i: int, meta: dict, jpgs: dict):
        self.paths, self.i, self.meta, self.jpgs = paths, i, meta, jpgs
        self.show_current()

    def show_current(self):
        p = self.paths[self.i]
        self.update_info()
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
                self.got(p, self.cache[p])
            elif self.jpgs.get(p):  # the thumbnail at once, sharp version when it's decoded
                self.image = QImage(str(self.jpgs[p]))
                self.fit()
            else:
                self.image = None
                self.pic.setText(span("loading…", "dim"))
        # only this one, then its neighbours: pictures flipped past quickly are never decoded
        near = [self.paths[k] for k in (self.i, self.i + 1, self.i - 1) if 0 <= k < len(self.paths)]
        self.want([x for x in near if library.kind(x) == "image" and x not in self.cache])

    def want(self, paths: list[Path]):
        with self.cv:
            self.queue = paths
            self.size_px = self.size() * self.devicePixelRatio()
            self.cv.notify()

    def loader(self):
        """One decoder thread; each new picture replaces what it was going to load next."""
        while True:
            with self.cv:
                while not self.queue:
                    self.cv.wait()
                p, size = self.queue.pop(0), self.size_px
            try:
                with Image.open(p) as im:
                    im.draft("RGB", (size.width(), size.height()))
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((max(size.width(), 400), max(size.height(), 400)), Image.LANCZOS)
                    q = QImage(im.tobytes(), im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
            except Exception as ex:
                q = f"can't open {p.name}: {ex}"
            thumbs.give_back()
            self.loaded.emit(p, q)

    def got(self, p, img):
        if isinstance(img, QImage):
            self.cache[p] = img
            if len(self.cache) > 4:
                self.cache.pop(next(iter(self.cache)))
        if not self.paths or p != self.paths[self.i]:
            return
        if isinstance(img, str):
            self.pic.setText(span(img, "dim"))
            return
        self.image = img
        self.fit()

    def fit(self):
        if self.image is not None:
            pm = QPixmap.fromImage(self.image)
            pm.setDevicePixelRatio(self.devicePixelRatio())
            target = self.pic.size() * self.devicePixelRatio()
            self.pic.setPixmap(pm.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.fit)

    def update_info(self):
        p = self.paths[self.i]
        when = taken(p, self.meta.get(p, {}))
        self.info.setText(span(p.name, "fg", True) + span(f"   {self.i + 1} / {len(self.paths)}   ", "mid")
                          + span(f"{p.parent.name}   ·   {when}", "dim"))
        self.changed.emit()

    def step(self, d: int):
        if self.paths:
            self.i = max(0, min(len(self.paths) - 1, self.i + d))
            self.show_current()

    def keyPressEvent(self, e):
        k, t = e.key(), e.text()
        video = library.kind(self.paths[self.i]) in ("video", "audio") if self.paths else False
        if k in (Qt.Key_Right, Qt.Key_PageDown) and not (video and e.modifiers() & Qt.ShiftModifier):
            self.step(1)
        elif k in (Qt.Key_Left, Qt.Key_PageUp) and not (video and e.modifiers() & Qt.ShiftModifier):
            self.step(-1)
        elif k == Qt.Key_Home:
            self.i = 0
            self.show_current()
        elif k == Qt.Key_End:
            self.i = len(self.paths) - 1
            self.show_current()
        elif k == Qt.Key_Space and video:
            self.video.toggle()
        elif video and k in (Qt.Key_Right, Qt.Key_Left):
            self.video.key("seek", "5" if k == Qt.Key_Right else "-5")
        elif video and t in (",", "."):
            self.video.key("seek", "-1" if t == "," else "1")
        elif k in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Return, Qt.Key_Enter):
            self.video.stop()
            self.back.emit()
        else:
            super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.video.stop()
        self.back.emit()

    def wheelEvent(self, e):
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
        QShortcut(QKeySequence("S"), self, self.open_settings)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence("/"), self, self.start_search)
        QShortcut(QKeySequence("Ctrl+F"), self, self.start_search)
        QShortcut(QKeySequence("U"), self, self.update_now)
        self.update_found.connect(self.got_update)
        self.release = None
        self.reload()
        self.tree.setFocus()
        if settings().get("check_updates", True) and not updates.is_disabled():
            self.check_updates()

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
        if self.pages.currentWidget() is self.viewer:
            video = self.viewer.paths and library.kind(self.viewer.paths[self.viewer.i]) in ("video", "audio")
            keys = [("VIEWING", ""), ("←→", "previous / next"), ("home end", "first / last")]
            if video:
                keys += [("space", "play / pause"), ("shift ←→", "5 s"), (", .", "1 s")]
            keys += [("o", "open in its app"), ("d", "show in file manager"), ("f", "full screen"),
                     ("esc", "back to thumbnails"), ("q", "quit")]
        elif self.search.hasFocus():
            keys = [("SEARCH", ""), ("type", "filter folders"), ("enter ↓", "to the folders"), ("esc", "clear")]
        elif self.grid.hasFocus():
            keys = [("PHOTOS", ""), ("arrows", "move"), ("enter", "view"), ("+ −", "size"), ("o", "open in its app"),
                    ("d", "show in file manager"), ("esc", "back to folders"), ("f", "full screen"), ("q", "quit")]
        else:
            keys = [("FOLDERS", ""), ("↑↓", "move"), ("←", "fold"), ("→", "unfold, then to the photos"), ("enter", "open / close, or to the photos"),
                    ("/", "search"), ("d", "open in file manager"), ("s", "settings"), ("f5", "reload"), ("f", "full screen"), ("esc q", "quit")]
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
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
    w = Shoebox(root)
    w.resize(1600, 980)  # the size it comes back to if you un-maximize it
    w.showMaximized()
    if not root:  # first start: pick the photos folder
        QTimer.singleShot(300, w.open_settings)
    code = app.exec()
    os._exit(code)  # don't wait for thumbnail workers
