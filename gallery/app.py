"""The window: folders by year and month on the left, thumbnails on the right, a full-size viewer on Enter.

Looks like the drew.in.nature studio (same colours and font). Works with the keyboard or the mouse.
Read-only: it never moves, renames or edits a photo.
"""
import locale
from collections import OrderedDict
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import mpv
from PIL import Image, ImageOps
from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QOpenGLContext, QPainter, QPixmap, QShortcut
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QLabel, QListView, QSplitter,
                               QStackedWidget, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from . import library, thumbs

ROOT = Path(os.environ.get("GALLERY_ROOT", "~/storage/Dropbox/Kids/Andrew/media/_photos and videos")).expanduser()

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


def launch(*cmd):
    subprocess.Popen(list(map(str, cmd)), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


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
        selected = bool(option.state & option.state.State_Selected)
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
        if library.kind(p) == "video":
            d = self.m.meta.get(p, {}).get("duration")
            text = "▶ " + (fmt_len(d) if d else "")
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
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
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
                         input_default_bindings=False, input_vo_keyboard=False)
        self.ctx = None
        self.frame.connect(self.update, Qt.QueuedConnection)

    def initializeGL(self):
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
        self.m.command("loadfile", str(p), "replace")
        self.m.pause = False

    def stop(self):
        try:
            self.m.command("stop")
        except SystemError:
            pass

    def key(self, cmd, *args):
        try:
            self.m.command(cmd, *args)
        except SystemError:
            pass


class Viewer(QWidget):
    """One photo or video, filling the window. ←→ next/previous, Esc back to the grid."""
    loaded = Signal(object, object)  # (path, QImage or error text)
    back = Signal()

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

    def show_at(self, paths: list[Path], i: int, meta: dict):
        self.paths, self.i, self.meta = paths, i, meta
        self.show_current()

    def show_current(self):
        p = self.paths[self.i]
        self.update_info()
        if library.kind(p) == "video":
            self.image = None
            self.stack.setCurrentWidget(self.video)
            self.video.play(p)
        else:
            self.video.stop()
            self.stack.setCurrentWidget(self.pic)
            if p in self.cache:
                self.got(p, self.cache[p])
            else:
                self.pic.setText(span("loading…", "dim"))
                self.load(p)
            for k in (self.i + 1, self.i - 1):  # the next one is usually already there
                if 0 <= k < len(self.paths) and library.kind(self.paths[k]) == "image" and self.paths[k] not in self.cache:
                    self.load(self.paths[k])

    def load(self, p: Path):
        size = self.size() * self.devicePixelRatio()

        def work():
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
        threading.Thread(target=work, daemon=True).start()

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
                          + span(f"{p.parent.name}   ·   {when}", "dim")
                          + span("     ←→ next   " + ("space play/pause   shift ←→ 5 s   , . 1 s   "
                                                        if library.kind(p) == "video" else "")
                                 + "f full screen   o open in its app   esc back", "dim"))

    def step(self, d: int):
        if self.paths:
            self.i = max(0, min(len(self.paths) - 1, self.i + d))
            self.show_current()

    def keyPressEvent(self, e):
        k, t = e.key(), e.text()
        video = self.stack.currentWidget() is self.video
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
            self.video.m.pause = not self.video.m.pause
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
class Gallery(QWidget):
    thumb_ready = Signal(object, object, object)

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.setWindowTitle("gallery")
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
        self.tree.itemActivated.connect(lambda *_: self.grid_focus())
        browse.addWidget(self.tree)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
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
        browse.setSizes([400, 1200])
        self.pages.addWidget(browse)

        self.viewer = Viewer()
        self.viewer.back.connect(self.close_viewer)
        self.pages.addWidget(self.viewer)

        self.keys = label(color="dim", size=10)
        self.keys.setContentsMargins(16, 6, 16, 6)
        self.keys.setStyleSheet(f"color:{C['dim']}; font-size:10pt; background:{C['panel']};")
        outer.addWidget(self.keys)

        self.thumb_ready.connect(self.items.got)
        self.maker = thumbs.Maker(lambda p, jpg, meta: self.thumb_ready.emit(p, jpg, meta))
        QShortcut(QKeySequence("F"), self, self.toggle_full)
        QShortcut(QKeySequence("F11"), self, self.toggle_full)
        QShortcut(QKeySequence("O"), self, self.open_external)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_folder)
        QShortcut(QKeySequence("F5"), self, self.reload)
        self.reload()
        self.tree.setFocus()

    # ---- tree
    def reload(self):
        cur = self.tree.currentItem()
        was = cur.data(0, Qt.UserRole) if cur else None
        self.tree.clear()
        folders = library.scan(self.root) if self.root.is_dir() else []
        if not folders:
            self.head.setText(span(f"nothing found in {self.root}", "dim"))
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
                    m = QTreeWidgetItem(parent, [library.MONTHS[f.month - 1], ""])
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
        target = self.find(was) if was else None
        self.tree.setCurrentItem(target or first)

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
        files = self.files_of(it)
        self.items.set_paths(files)
        kind, v = it.data(0, Qt.UserRole)
        if kind == "folder":
            title = v.name
            when = f"{library.MONTHS[v.month - 1]} {int(v.day)}, {v.year}" if v.month and v.day else v.year
        elif kind == "month":
            title, when = f"{library.MONTHS[v[1] - 1]} {v[0]}", ""
        else:
            title, when = v, ""
        n_vid = sum(library.kind(p) == "video" for p in files)
        self.head.setText(span(title, "fg", True) + span(f"   {when}" if when else "", "mid")
                          + span(f"   {len(files) - n_vid} photos · {n_vid} videos", "dim"))
        need = []
        for p in files:
            if p in self.items.jpg:
                continue
            hit = thumbs.cached(p)
            if hit:
                self.items.got(p, *hit)
            else:
                need.append(p)
        self.maker.ask(need)
        if files:
            self.grid.setCurrentIndex(self.items.index(0))
            self.grid.scrollToTop()
        self.show_keys()

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
        self.viewer.show_at(self.items.paths, row, self.items.meta)
        self.show_keys()

    def close_viewer(self):
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

    def current_path(self) -> Path | None:
        if self.pages.currentWidget() is self.viewer and self.viewer.paths:
            return self.viewer.paths[self.viewer.i]
        i = self.grid.currentIndex()
        return self.items.paths[i.row()] if i.isValid() else None

    def open_external(self):
        p = self.current_path()
        if p:
            self.viewer.video.stop()
            launch("xdg-open", p)

    def open_folder(self):
        p = self.current_path()
        if p:
            launch("dolphin", "--select", p)

    def show_keys(self):
        if self.pages.currentWidget() is self.viewer:
            self.keys.setText("")
            return
        self.keys.setText("↑↓ folders   → or enter: thumbnails   enter opens   tab back to folders   "
                          "+ − size (ctrl+wheel)   o open in its app   ctrl+o show in Dolphin   f full screen   "
                          "f5 reload")

    def closeEvent(self, e):
        self.viewer.video.stop()
        super().closeEvent(e)


class Tree(QTreeWidget):
    """→ on an open or empty folder goes to the thumbnails."""
    to_grid = Signal()

    def keyPressEvent(self, e):
        it = self.currentItem()
        if e.key() == Qt.Key_Right and it and (it.isExpanded() or not it.childCount()):
            self.to_grid.emit()
        else:
            super().keyPressEvent(e)


def main():
    QApplication.setApplicationName("gallery")
    QApplication.setDesktopFileName("gallery")
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
    w = Gallery(root)
    w.resize(1600, 980)
    w.show()
    code = app.exec()
    os._exit(code)  # don't wait for thumbnail workers
