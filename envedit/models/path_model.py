from __future__ import annotations

import os
from collections import Counter

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property
)


def _status(path: str) -> str:
    if os.path.islink(path):
        return "🔗"
    if os.path.isdir(path):
        return "✅"
    return "⚠"


class PathModel(QAbstractListModel):
    PathRole      = Qt.UserRole + 1
    ExpandedRole  = Qt.UserRole + 2
    StatusRole    = Qt.UserRole + 3
    PendingRole   = Qt.UserRole + 4
    DuplicateRole = Qt.UserRole + 5

    pendingCountChanged = Signal()

    def __init__(self, expand_fn=None, parent=None):
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        # Each entry: {"path": str, "original": str | None, "is_new": bool}
        # "original" holds the pre-edit value on first user edit; None = unedited
        self._entries: list[dict] = []
        self._original: list[str] = []   # snapshot for discard
        self._dirty = False
        self._filter: str = ""

    # ------------------------------------------------------------------ QML properties

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self) -> int:
        return 1 if self._dirty else 0

    # ------------------------------------------------------------------ QAbstractListModel

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._visible())

    def roleNames(self):
        return {
            self.PathRole:      b"path",
            self.ExpandedRole:  b"expanded",
            self.StatusRole:    b"status",
            self.PendingRole:   b"isPending",
            self.DuplicateRole: b"isDuplicate",
        }

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        visible = self._visible()
        if index.row() >= len(visible):
            return None
        entry = visible[index.row()]
        expanded = self._expand_fn(entry["path"])
        counts = Counter(e["path"] for e in self._entries)

        if role == self.PathRole:
            return entry["path"]
        if role == self.ExpandedRole:
            return expanded
        if role == self.StatusRole:
            return _status(expanded)
        if role == self.PendingRole:
            return entry["is_new"] or entry["original"] is not None
        if role == self.DuplicateRole:
            return counts[entry["path"]] > 1
        return None

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def addEntry(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        self._entries.append({"path": path, "original": None, "is_new": True})
        self._mark_dirty()

    @Slot(int, str)
    def editEntry(self, index: int, path: str) -> None:
        real = self._visible_indices()
        if index < 0 or index >= len(real):
            return
        entry = self._entries[real[index]]
        if entry["path"] == path:
            return
        if entry["original"] is None and not entry["is_new"]:
            entry["original"] = entry["path"]
        entry["path"] = path
        if entry["path"] == entry["original"]:
            entry["original"] = None
        self._mark_dirty()

    @Slot(int)
    def deleteEntry(self, index: int) -> None:
        real = self._visible_indices()
        if index < 0 or index >= len(real):
            return
        self._entries.pop(real[index])
        self._mark_dirty()

    @Slot(int)
    def moveUp(self, index: int) -> None:
        real = self._visible_indices()
        if index <= 0 or index >= len(real):
            return
        i, j = real[index], real[index - 1]
        self._entries[i], self._entries[j] = self._entries[j], self._entries[i]
        self._mark_dirty()

    @Slot(int)
    def moveDown(self, index: int) -> None:
        real = self._visible_indices()
        if index < 0 or index >= len(real) - 1:
            return
        i, j = real[index], real[index + 1]
        self._entries[i], self._entries[j] = self._entries[j], self._entries[i]
        self._mark_dirty()

    @Slot(int, int)
    def moveEntry(self, src: int, dst: int) -> None:
        real = self._visible_indices()
        if src < 0 or src >= len(real) or dst < 0 or dst >= len(real):
            return
        entry = self._entries.pop(real[src])
        insert_at = real[dst] if dst < src else real[dst]
        self._entries.insert(insert_at, entry)
        self._mark_dirty()

    @Slot()
    def removeDuplicates(self) -> None:
        seen: set[str] = set()
        deduped = []
        for e in self._entries:
            if e["path"] not in seen:
                seen.add(e["path"])
                deduped.append(e)
        if len(deduped) != len(self._entries):
            self._entries = deduped
            self._mark_dirty()

    @Slot(str)
    def setFilter(self, text: str) -> None:
        self._filter = text.lower()
        self._reset()

    @Slot()
    def discardChanges(self) -> None:
        self._entries = [{"path": e, "original": None, "is_new": False} for e in self._original]
        self._dirty = False
        self._reset()

    def loadData(self, entries: list[str]) -> None:
        self._entries = [{"path": e, "original": None, "is_new": False} for e in entries]
        self._original = list(entries)
        self._dirty = False
        self._reset()

    def getEntries(self) -> list[str]:
        return [e["path"] for e in self._entries]

    # ------------------------------------------------------------------ internals

    def _visible(self) -> list[dict]:
        if not self._filter:
            return self._entries
        return [e for e in self._entries if self._filter in e["path"].lower()]

    def _visible_indices(self) -> list[int]:
        if not self._filter:
            return list(range(len(self._entries)))
        return [i for i, e in enumerate(self._entries) if self._filter in e["path"].lower()]

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._reset()

    def _reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()
        self.pendingCountChanged.emit()
