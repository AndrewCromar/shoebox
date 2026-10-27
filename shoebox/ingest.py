"""Ingest: bring photos from outside (a friend's upload, a phone dump) into one event, without doubles.

Pick the folder to bring in and the event to add to. Shoebox fingerprints both (matcher.py) and marks each
incoming file NEW, HAVE (already in the event) or MAYBE (looks very like one). New ones start ticked; you tick
or untick with space and press Enter to move the ticked ones into the event. Nothing is deleted: what you
don't take stays where it was.

Every move is written to ingest-log.jsonl in the settings folder (one line per batch: when, from, to, each
file's old and new path), so a batch can be undone (z) or fixed by hand or by Claude later.
"""
import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import library, matcher, system, thumbs
from .app import C, FONT, Cell, Grid, Items, label, span

LOG = system.config_dir() / "ingest-log.jsonl"
BADGE = {"new": ("NEW", "keep"), "have": ("HAVE", "dim"), "maybe": ("MAYBE?", "warn"), "unreadable": ("?", "bad")}


# ---------------------------------------------------------------- moving files (no GUI)
def free_name(folder: Path, name: str) -> Path:
    """name in folder, or name (2), name (3)… if it's taken."""
    p = folder / name
    stem, ext, n = p.stem, p.suffix, 2
    while p.exists():
        p = folder / f"{stem} ({n}){ext}"
        n += 1
    return p


def move_in(files: list[Path], event: Path, source: Path) -> dict:
    """Move files into the event; returns the batch (also appended to the log)."""
    batch = {"id": uuid.uuid4().hex[:8], "when": datetime.now().isoformat(timespec="seconds"),
             "from": str(source), "to": str(event), "moves": []}
    try:
        for f in files:
            dest = free_name(event, f.name)
            shutil.move(str(f), str(dest))
            batch["moves"].append([str(f), str(dest)])
    finally:  # log whatever moved, even if something failed half way
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as log:
            log.write(json.dumps(batch) + "\n")
    return batch


def batches() -> list[dict]:
    try:
        return [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []


def undo_last() -> tuple[int, int]:
    """Move the last batch back where it came from. Returns (moved back, couldn't)."""
    all_ = batches()
    todo = [b for b in all_ if not b.get("undone") and b["moves"]]
    if not todo:
        return 0, 0
    b = todo[-1]
    back = failed = 0
    for old, new in reversed(b["moves"]):
        old, new = Path(old), Path(new)
        if new.exists() and not old.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(new), str(old))
            back += 1
        else:
            failed += 1
    b["undone"] = datetime.now().isoformat(timespec="seconds")
    LOG.write_text("".join(json.dumps(x) + "\n" for x in all_), encoding="utf-8")
    return back, failed


# ---------------------------------------------------------------- the page
class BadgeCell(Cell):
    """A thumbnail with its status (NEW / HAVE / MAYBE?) and a tick if it's going in."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        p = self.m.paths[index.row()]
        r = option.rect.adjusted(10, 10, -10, -10)
        painter.save()
        if self.m.status.get(p) == "have":  # already in the event: faded, so the new ones stand out
            painter.fillRect(option.rect.adjusted(6, 6, -6, -6), QColor(17, 19, 18, 150))
        painter.setFont(QFont(FONT, 9, QFont.DemiBold))
        text, col = BADGE.get(self.m.status.get(p, ""), ("…", "dim"))
        w = painter.fontMetrics().horizontalAdvance(text) + 12
        box = QRect(r.x(), r.y(), w, 20)
        painter.fillRect(box, QColor(0, 0, 0, 190))
        painter.setPen(QColor(C[col]))
        painter.drawText(box, Qt.AlignCenter, text)
        tick = QRect(r.right() - 24, r.y(), 24, 24)
        painter.fillRect(tick, QColor(C["keep"]) if p in self.m.ticked else QColor(0, 0, 0, 150))
        painter.setPen(QColor("black" if p in self.m.ticked else C["mid"]))
        painter.setFont(QFont(FONT, 12, QFont.Bold))
        painter.drawText(tick, Qt.AlignCenter, "✓" if p in self.m.ticked else "")
        painter.restore()


class IngestGrid(Grid):
    """The thumbnails; the page's own keys (space, enter, a, n, z, c, e, esc) go to the page."""
    page_key = Signal(object)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Backspace) \
                or e.text() in ("a", "n", "z", "c", "e"):
            self.page_key.emit(e)
        else:
            super().keyPressEvent(e)


class IngestItems(Items):
    def __init__(self):
        super().__init__()
        self.status: dict[Path, str] = {}
        self.match: dict[Path, Path | None] = {}
        self.ticked: set[Path] = set()


class Ingest(QWidget):
    progress = Signal(int, int)
    compared = Signal(object)
    back = Signal()
    moved = Signal(object)  # the batch, so the main window can reload

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.source: Path | None = None
        self.target: Path | None = None
        self.scanning = False
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        self.head = label()
        self.head.setContentsMargins(18, 14, 18, 4)
        self.head.setWordWrap(True)
        left.addWidget(self.head)
        self.status_line = label(color="mid")
        self.status_line.setContentsMargins(18, 0, 18, 10)
        left.addWidget(self.status_line)
        self.items = IngestItems()
        self.grid = IngestGrid(self.items)
        self.grid.cell = BadgeCell(self.items)
        self.grid.setItemDelegate(self.grid.cell)
        self.grid.open_item.connect(lambda row: self.toggle())  # double-click ticks / unticks
        self.grid.page_key.connect(self.keyPressEvent)
        self.grid.selectionModel().currentChanged.connect(lambda *_: self.show_pair())
        left.addWidget(self.grid, 1)
        h.addLayout(left, 3)
        side = QVBoxLayout()
        side.setContentsMargins(16, 16, 16, 16)
        side.addWidget(label(span("INCOMING", "dim")))
        self.pic_in = self.picture()
        side.addWidget(self.pic_in, 1)
        side.addWidget(label(span("ALREADY IN THE EVENT", "dim")))
        self.pic_have = self.picture()
        side.addWidget(self.pic_have, 1)
        self.pair_text = label(color="mid")
        self.pair_text.setWordWrap(True)
        side.addWidget(self.pair_text)
        panel = QWidget()
        panel.setLayout(side)
        panel.setStyleSheet(f"background:{C['panel']};")
        panel.setFixedWidth(420)
        h.addWidget(panel)
        self.progress.connect(self.got_progress)
        self.compared.connect(self.got_compared)

    @staticmethod
    def picture() -> QLabel:
        p = QLabel()
        p.setAlignment(Qt.AlignCenter)
        p.setMinimumSize(1, 1)
        p.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        return p

    # ---- choosing
    def start(self, event: Path | None):
        """Opened from the main window; event: the folder selected there, if it's an event."""
        self.target = event
        self.show_head()
        if not self.source:
            self.choose_source()
        elif self.target:
            self.scan()

    def choose_source(self):
        d = QFileDialog.getExistingDirectory(self, "Which folder do you want to bring in?",
                                             str(self.source or Path.home()))
        if d:
            self.source = Path(d)
            self.show_head()
            if self.target:
                self.scan()
            else:
                self.choose_event()

    def choose_event(self):
        d = QFileDialog.getExistingDirectory(self, "Which event should they go into?",
                                             str(self.target or self.win.root or Path.home()))
        if d:
            self.target = Path(d)
            self.show_head()
            if self.source:
                self.scan()

    def show_head(self):
        def name(p, empty):
            return span(p.name, "fg", True) + span(f"   {p.parent}", "dim") if p else span(empty, "warn")
        self.head.setText(span("INGEST", "acc", True) + "<br>"
                          + span("from  ", "dim") + name(self.source, "choose a folder (c)") + "<br>"
                          + span("into  ", "dim") + name(self.target, "choose an event (e)"))

    # ---- comparing
    def scan(self):
        if self.scanning or not (self.source and self.target):
            return
        if self.source.resolve() == self.target.resolve():
            self.status_line.setText(span("That's the same folder twice: pick another one.", "bad"))
            return
        incoming = [p for p in sorted(self.source.rglob("*")) if p.is_file() and library.kind(p)]
        have = [p for p in sorted(self.target.rglob("*")) if p.is_file() and library.kind(p)]
        self.items.set_paths(incoming)
        self.items.status.clear()
        self.items.ticked.clear()
        if not incoming:
            self.status_line.setText(span("No photos, videos or audio in that folder.", "warn"))
            return
        self.scanning = True
        self.status_line.setText(span(f"Comparing {len(incoming)} files with the {len(have)} in the event…", "mid"))

        def work():
            res = matcher.compare(incoming, have, progress=lambda d, t: self.progress.emit(d, t))
            self.compared.emit(res)
        threading.Thread(target=work, daemon=True).start()

    def got_progress(self, done, total):
        if done % 5 == 0 or done == total:
            self.status_line.setText(span(f"Comparing… {done} / {total}", "mid"))

    def got_compared(self, res):
        self.scanning = False
        order = {"new": 0, "maybe": 1, "unreadable": 2, "have": 3}  # new first, what you have last
        res = sorted(res, key=lambda r: (order[r["status"]], r["path"].name.lower()))
        self.items.set_paths([r["path"] for r in res])
        for r in res:
            p = r["path"]
            self.items.status[p], self.items.match[p] = r["status"], r["match"]
            if r["status"] == "new":
                self.items.ticked.add(p)
            hit = thumbs.cached(p)
            if hit:
                self.items.got(p, *hit)
        for p in {r["match"] for r in res if r["match"]}:
            hit = thumbs.cached(p)
            if hit:
                self.items.jpg[p] = hit[0]
        self.grid.viewport().update()
        if self.items.paths:
            self.grid.setCurrentIndex(self.items.index(0))
        self.grid.setFocus()
        self.count()

    def count(self):
        n = {s: sum(v == s for v in self.items.status.values()) for s in BADGE}
        self.status_line.setText(
            span(f"{n['new']} new", "keep", True) + span(f"   {n['have']} you have", "mid")
            + (span(f"   {n['maybe']} maybe", "warn") if n["maybe"] else "")
            + (span(f"   {n['unreadable']} unreadable", "bad") if n["unreadable"] else "")
            + span(f"      {len(self.items.ticked)} ticked to bring in", "acc", True))

    # ---- the side panel: incoming next to what it matched
    def current(self) -> Path | None:
        i = self.grid.currentIndex()
        return self.items.paths[i.row()] if i.isValid() else None

    def show_pair(self):
        p = self.current()
        if not p:
            return
        self.set_pic(self.pic_in, p)
        m = self.items.match.get(p)
        self.set_pic(self.pic_have, m)
        st = self.items.status.get(p, "")
        why = {"new": "Not in the event yet.", "have": "Already in the event (same photo, maybe another size).",
               "maybe": "Looks very like one in the event: compare them.", "unreadable": "Couldn't read this file."}
        self.pair_text.setText(span(p.name, "fg", True) + "<br>" + span(why.get(st, ""), "mid")
                               + ("<br>" + span(f"matches {m.name}", "dim") if m else ""))

    def set_pic(self, lab: QLabel, p: Path | None):
        jpg = self.items.jpg.get(p) if p else None
        if not jpg:
            lab.clear()
            lab.setText(span("—", "dim") if p is None else "")
            return
        pm = QPixmap(str(jpg))
        lab.setPixmap(pm.scaled(lab.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ---- ticking and moving
    def toggle(self):
        p = self.current()
        if p:
            self.items.ticked ^= {p}
            self.grid.viewport().update()
            self.count()

    def tick_all(self, which: str):
        """which: "new" ticks every new one, "none" unticks all."""
        self.items.ticked = {p for p, s in self.items.status.items() if s == "new"} if which == "new" else set()
        self.grid.viewport().update()
        self.count()

    def bring_in(self):
        files = [p for p in self.items.paths if p in self.items.ticked and p.exists()]
        if not files or not self.target:
            return
        from PySide6.QtWidgets import QMessageBox
        ok = QMessageBox.question(self, "Bring them in?",
                                  f"Move {len(files)} files into “{self.target.name}”?\n\n"
                                  "The rest stay where they are. You can undo this with z.")
        if ok != QMessageBox.Yes:
            return
        batch = move_in(files, self.target, self.source)
        self.status_line.setText(span(f"Moved {len(batch['moves'])} files into {self.target.name}.", "keep", True)
                                 + span("   z undoes it", "dim"))
        self.moved.emit(batch)
        self.scan_after_move()

    def scan_after_move(self):
        self.items.set_paths([p for p in self.items.paths if p.exists()])
        self.items.ticked = {p for p in self.items.ticked if p.exists()}
        self.grid.viewport().update()

    def undo(self):
        back, failed = undo_last()
        if not back and not failed:
            self.status_line.setText(span("Nothing to undo.", "dim"))
            return
        self.status_line.setText(span(f"Moved {back} files back.", "keep")
                                 + (span(f"   {failed} couldn't (moved or renamed since)", "warn") if failed else ""))
        self.moved.emit(None)
        self.scan()

    def keys(self):
        return [("INGEST", ""), ("space", "tick / untick"), ("a", "tick all new"), ("n", "untick all"),
                ("enter", "bring the ticked in"), ("z", "undo the last"), ("c", "another folder"),
                ("e", "another event"), ("esc", "back")]

    def keyPressEvent(self, e):
        t = e.text()
        if e.key() == Qt.Key_Space:
            self.toggle()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.bring_in()
        elif e.key() in (Qt.Key_Escape, Qt.Key_Backspace):
            self.back.emit()
        elif t == "a":
            self.tick_all("new")
        elif t == "n":
            self.tick_all("none")
        elif t == "z":
            self.undo()
        elif t == "c":
            self.choose_source()
        elif t == "e":
            self.choose_event()
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.show_pair()
