"""Duplicates: the same picture more than once in the library (a copy, a resized or re-saved one, a renamed one).

Shift+D on a year, month or event scans it with the matcher (the picture decides, not names or dates) and
shows each set side by side. The best copy (most pixels, then the biggest file) is suggested to keep; the rest
are marked for the trash. ←→ picks a copy, space keeps/trashes it, Enter does this set, ↑↓ moves between sets.
"Trash" is the system trash (Recycle Bin on Windows), so it can be restored; every set done is logged in
dupes-log.jsonl next to the settings, and z puts the last set back.
"""
import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QFile, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import library, matcher, system, thumbs
from .app import C, label, span

LOG = system.config_dir() / "dupes-log.jsonl"


# ---------------------------------------------------------------- finding (no GUI)
def find_groups(files: list[Path], progress=None) -> list[list[Path]]:
    """Sets of files showing the same picture (2 or more each), biggest sets first."""
    prints = []
    for i, p in enumerate(files):
        fp = matcher.fingerprint(p)
        if fp:
            prints.append((p, fp))
        if progress:
            progress(i + 1, len(files))
    matcher.save()
    parent = list(range(len(prints)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    by_kind: dict[str, list[int]] = {}
    for i, (_, fp) in enumerate(prints):
        by_kind.setdefault(fp["kind"], []).append(i)
    for idx in by_kind.values():
        for a_pos, a in enumerate(idx):
            fa = prints[a][1]
            for b in idx[a_pos + 1:]:
                d = matcher.distance(fa, prints[b][1])
                if d is not None and d <= matcher.SAME:
                    parent[root(a)] = root(b)
    groups: dict[int, list[Path]] = {}
    for i, (p, _) in enumerate(prints):
        groups.setdefault(root(i), []).append(p)
    out = [sorted(g, key=lambda p: -quality(p)) for g in groups.values() if len(g) > 1]
    return sorted(out, key=lambda g: (-len(g), str(g[0])))


def dims(p: Path) -> tuple[int, int]:
    """The real picture size (from the file's header, quick). Videos and audio: (0, 0)."""
    if library.kind(p) != "image":
        return 0, 0
    try:
        with Image.open(p) as im:
            return im.size
    except Exception:
        return 0, 0


def quality(p: Path) -> float:
    """Which copy to keep: the most pixels, then the biggest file (less compressed)."""
    w, h = dims(p)
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    return w * h * 1e3 + size / 1e6


# ---------------------------------------------------------------- trashing, the log, undo
def trash(files: list[Path], keep: list[Path]) -> dict:
    entry = {"id": uuid.uuid4().hex[:8], "when": datetime.now().isoformat(timespec="seconds"),
             "kept": [str(k) for k in keep], "trashed": []}
    try:
        for f in files:
            q = QFile(str(f))
            if q.moveToTrash():  # afterwards the QFile points at where it went in the trash
                entry["trashed"].append([str(f), q.fileName()])
    finally:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")
    return entry


def undo_last() -> tuple[int, int]:
    """Put the last set's trashed files back where they were. (restored, couldn't)"""
    try:
        all_ = [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return 0, 0
    todo = [e for e in all_ if not e.get("undone") and e["trashed"]]
    if not todo:
        return 0, 0
    e = todo[-1]
    back = failed = 0
    for old, where in e["trashed"]:
        if where and Path(where).exists() and not Path(old).exists():
            Path(old).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(where, old)
            back += 1
        else:
            failed += 1
    e["undone"] = datetime.now().isoformat(timespec="seconds")
    LOG.write_text("".join(json.dumps(x) + "\n" for x in all_), encoding="utf-8")
    return back, failed


# ---------------------------------------------------------------- the page
class Card(QWidget):
    """One copy in a set: its picture, KEEP or TRASH, and what it is."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setMinimumSize(1, 1)
        self.pic.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        v.addWidget(self.pic, 1)
        self.mark = label()
        v.addWidget(self.mark)
        self.info = label(color="mid", size=10)
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.pm: QPixmap | None = None

    def show_file(self, p: Path, keep: bool, current: bool, root: Path | None):
        hit = thumbs.cached(p)
        self.pm = QPixmap(str(hit[0])) if hit else None
        self.fit()
        self.mark.setText(span("KEEP", "keep", True) if keep else span("TRASH", "bad", True))
        where = p.parent
        try:
            where = p.parent.relative_to(root) if root else where
        except ValueError:
            pass
        w, h = dims(p)
        size = f"{w}×{h}" if w else ""
        self.info.setText(span(p.name, "fg", True) + "<br>" + span(str(where), "dim") + "<br>"
                          + span(f"{size}   {p.stat().st_size / 1e6:.1f} MB", "mid"))
        border = C["acc"] if current else C["line"]
        self.setStyleSheet(f"Card {{ border: 2px solid {border}; }}")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def fit(self):
        if self.pm:
            self.pic.setPixmap(self.pm.scaled(self.pic.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.pic.clear()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit()


class Dupes(QWidget):
    progress = Signal(int, int)
    found = Signal(object)
    back = Signal()
    changed = Signal()  # files went to the trash or came back: the main window reloads

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.groups: list[list[Path]] = []
        self.keep: list[set[Path]] = []
        self.g = 0      # current set
        self.i = 0      # current copy in it
        self.scanning = False
        self.scope_files: list[Path] = []
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.list = QListWidget()
        self.list.setFixedWidth(330)
        self.list.setIconSize(QSize(56, 56))
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.currentRowChanged.connect(self.pick_group)
        self.list.setStyleSheet(f"QListWidget {{ background:{C['panel']}; border:none; }} "
                                f"QListWidget::item:selected {{ background:{C['sel']}; color:{C['acc']}; }}")
        h.addWidget(self.list)
        right = QVBoxLayout()
        right.setContentsMargins(18, 14, 18, 14)
        self.head = label()
        self.head.setWordWrap(True)
        right.addWidget(self.head)
        self.status = label(color="mid")
        right.addWidget(self.status)
        self.row = QHBoxLayout()
        right.addLayout(self.row, 1)
        h.addLayout(right, 1)
        self.cards: list[Card] = []
        self.progress.connect(lambda d, t: self.status.setText(span(f"Comparing… {d} / {t}", "mid"))
                              if d % 10 == 0 or d == t else None)
        self.found.connect(self.got_groups)
        self.setFocusPolicy(Qt.StrongFocus)

    def start(self, title: str, files: list[Path]):
        self.title = title
        self.scope_files = files
        self.scan()

    def scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.head.setText(span("DUPLICATES", "acc", True) + span(f"   in {self.title}", "fg", True)
                          + span(f"   ({len(self.scope_files)} files)", "dim"))
        self.status.setText(span("Comparing…", "mid"))
        self.list.clear()
        self.show_group()
        files = [p for p in self.scope_files if p.exists()]
        threading.Thread(target=lambda: self.found.emit(find_groups(files, lambda d, t: self.progress.emit(d, t))),
                         daemon=True).start()

    def got_groups(self, groups):
        self.scanning = False
        self.groups = groups
        self.keep = [{g[0]} for g in groups]  # suggest the best copy
        self.list.clear()
        for g in groups:
            hit = thumbs.cached(g[0])
            it = QListWidgetItem(f"{len(g)} copies\n{g[0].name}")
            if hit:
                it.setIcon(QPixmap(str(hit[0])))
            self.list.addItem(it)
        if groups:
            self.list.setCurrentRow(0)
        self.count()
        self.setFocus()

    def count(self):
        extra = sum(len(g) - 1 for g in self.groups)
        self.status.setText(span(f"{len(self.groups)} sets", "fg", True)
                            + span(f"   {extra} extra copies", "mid") if self.groups
                            else span("No duplicates here: every picture is there once.", "keep"))

    def pick_group(self, row):
        if 0 <= row < len(self.groups):
            self.g, self.i = row, 0
            self.show_group()

    def show_group(self):
        for c in self.cards:
            c.setParent(None)
        self.cards = []
        if not self.groups:
            return
        g = self.groups[self.g]
        for k, p in enumerate(g[:6]):  # a set bigger than 6 shows the first 6 (rare)
            c = Card()
            self.row.addWidget(c, 1)
            self.cards.append(c)
            if p.exists():
                c.show_file(p, p in self.keep[self.g], k == self.i, self.win.root)

    def toggle(self):
        if not self.groups:
            return
        p = self.groups[self.g][self.i]
        self.keep[self.g] ^= {p}
        self.show_group()

    def apply(self):
        """Trash the copies marked TRASH in this set (at least one copy is always kept)."""
        if not self.groups:
            return
        g, keep = self.groups[self.g], self.keep[self.g]
        if not keep:
            self.status.setText(span("Keep at least one copy (space marks one KEEP).", "warn"))
            return
        out = [p for p in g if p not in keep and p.exists()]
        entry = trash(out, sorted(keep))
        self.status.setText(span(f"{len(entry['trashed'])} copies to the trash", "keep", True)
                            + span("   z puts them back", "dim"))
        del self.groups[self.g], self.keep[self.g]
        self.list.takeItem(self.g)
        self.g = min(self.g, len(self.groups) - 1)
        self.i = 0
        if self.groups:
            self.list.setCurrentRow(self.g)
        self.show_group()
        self.changed.emit()

    def undo(self):
        back, failed = undo_last()
        if not back and not failed:
            self.status.setText(span("Nothing to undo.", "dim"))
            return
        self.status.setText(span(f"Put {back} back.", "keep")
                            + (span(f"   {failed} couldn't (emptied from the trash?)", "warn") if failed else ""))
        self.changed.emit()
        self.scan()

    def keys(self):
        return [("DUPLICATES", ""), ("↑↓", "sets"), ("←→", "copies"), ("space", "keep / trash"),
                ("enter", "do this set"), ("z", "undo the last"), ("esc", "back")]

    def keyPressEvent(self, e):
        k = e.key()
        n = len(self.groups[self.g]) if self.groups else 0
        if k in (Qt.Key_Up, Qt.Key_Down) and self.groups:
            self.list.setCurrentRow(max(0, min(len(self.groups) - 1, self.g + (-1 if k == Qt.Key_Up else 1))))
        elif k in (Qt.Key_Left, Qt.Key_Right) and n:
            self.i = max(0, min(min(n, 6) - 1, self.i + (-1 if k == Qt.Key_Left else 1)))
            self.show_group()
        elif k == Qt.Key_Space:
            self.toggle()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.apply()
        elif e.text() == "z":
            self.undo()
        elif k in (Qt.Key_Escape, Qt.Key_Backspace):
            self.back.emit()
        else:
            super().keyPressEvent(e)
