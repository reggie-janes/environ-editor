from __future__ import annotations

import os
from collections import Counter

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property
)


def _path_rejection_reason(path: str) -> str | None:
    """Return a human-readable rejection reason, or None if the path is OK
    to add. Rejects empty input, os.pathsep-bearing input (would fan out
    into multiple entries after the round-trip), and newline/NUL (would
    corrupt the shell file or registry value)."""
    if not path.strip():
        return "Path cannot be empty."
    if os.pathsep in path:
        sep_name = "':'" if os.pathsep == ":" else "';'"
        return (
            f"Path entries cannot contain {sep_name}. Add one entry per row."
        )
    if "\n" in path or "\r" in path or "\x00" in path:
        return "Path entries cannot contain newline or null characters."
    return None


def _status(path: str) -> str:
    if os.path.islink(path):
        # os.path.isdir follows symlinks; broken links return False here.
        return "🔗" if os.path.isdir(path) else "⚠"
    if os.path.isdir(path):
        return "✅"
    return "⚠"


class PathModel(QAbstractListModel):
    PathRole      = Qt.UserRole + 1
    ExpandedRole  = Qt.UserRole + 2
    StatusRole    = Qt.UserRole + 3
    PendingRole   = Qt.UserRole + 4
    DuplicateRole = Qt.UserRole + 5
    DeletedRole   = Qt.UserRole + 6

    pendingCountChanged = Signal()
    filterChanged = Signal()
    errorOccurred = Signal(str)

    def __init__(self, expand_fn=None, parent=None):
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        # Each entry: {"path": str, "original": str | None, "is_new": bool}
        # "original" holds the pre-edit value on first user edit; None = unedited
        self._entries: list[dict] = []
        self._original: list[str] = []   # snapshot for discard
        self._dirty = False
        self._filter: str = ""
        # Cached Counter of paths so data() is O(1) per cell instead of O(n).
        self._dup_counts: Counter = Counter()

    # ------------------------------------------------------------------ QML properties

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self) -> int:
        return 1 if self._dirty else 0

    @Property(bool, notify=filterChanged)
    def filterActive(self) -> bool:
        return bool(self._filter)

    @Property(bool, notify=pendingCountChanged)
    def hasDuplicates(self) -> bool:
        return any(v > 1 for v in self._dup_counts.values())

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
            self.DeletedRole:   b"isDeleted",
        }

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        visible = self._visible()
        if index.row() >= len(visible):
            return None
        entry = visible[index.row()]

        if role == self.PathRole:
            return entry["path"]
        if role == self.ExpandedRole:
            return self._expand_fn(entry["path"])
        if role == self.StatusRole:
            return _status(self._expand_fn(entry["path"]))
        if role == self.PendingRole:
            return entry["is_new"] or entry["original"] is not None or entry["is_deleted"]
        if role == self.DuplicateRole:
            return self._dup_counts[entry["path"]] > 1
        if role == self.DeletedRole:
            return entry["is_deleted"]
        return None

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def addEntry(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        reason = _path_rejection_reason(path)
        if reason is not None:
            self.errorOccurred.emit(reason)
            return
        self._entries.append({"path": path, "original": None, "is_new": True, "is_deleted": False})
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
        # Edits can revert as well as introduce changes; recompute from scratch
        # so reverting the only outstanding edit clears _dirty.
        self._recalculate_dirty()
        self._refresh_dup_counts()
        # Use dataChanged instead of _reset() so ListView delegates are not
        # destroyed and recreated — that would steal focus from the TextInput
        # after every keystroke. Dup counts may affect any visible row so we
        # notify all rows; the focused TextInput's text binding is already
        # broken by user input so it won't be overwritten.
        if self.rowCount() > 0:
            self.dataChanged.emit(self.index(0), self.index(self.rowCount() - 1))
        self.pendingCountChanged.emit()

    @Slot(int)
    def restoreEntry(self, index: int) -> None:
        real = self._visible_indices()
        if index < 0 or index >= len(real):
            return
        entry = self._entries[real[index]]
        if entry["is_deleted"]:
            entry["is_deleted"] = False
            self._recalculate_dirty()
            self._refresh_dup_counts()
            self._reset()

    @Slot(int)
    def deleteEntry(self, index: int) -> None:
        real = self._visible_indices()
        if index < 0 or index >= len(real):
            return
        entry = self._entries[real[index]]
        if entry["is_new"]:
            self._entries.pop(real[index])
        else:
            entry["is_deleted"] = True
        self._recalculate_dirty()
        self._refresh_dup_counts()
        self._reset()

    # Move operations refuse to run when a filter is active. Crossing over
    # rows that aren't visible would silently rearrange unrelated entries
    # (visible-position adjacent != underlying-position adjacent), which
    # users can't see and don't expect. The QML UI should disable the
    # corresponding controls; these guards are also a runtime safety net.

    @Slot(int)
    def moveUp(self, index: int) -> None:
        if self._filter:
            return
        if index <= 0 or index >= len(self._entries):
            return
        self._entries[index], self._entries[index - 1] = (
            self._entries[index - 1], self._entries[index]
        )
        self._recalculate_dirty()
        self._refresh_dup_counts()
        self._reset()

    @Slot(int)
    def moveDown(self, index: int) -> None:
        if self._filter:
            return
        if index < 0 or index >= len(self._entries) - 1:
            return
        self._entries[index], self._entries[index + 1] = (
            self._entries[index + 1], self._entries[index]
        )
        self._recalculate_dirty()
        self._refresh_dup_counts()
        self._reset()

    @Slot(int, int)
    def moveEntry(self, src: int, dst: int) -> None:
        if self._filter:
            return
        if src < 0 or src >= len(self._entries) or dst < 0 or dst >= len(self._entries):
            return
        entry = self._entries.pop(src)
        self._entries.insert(dst, entry)
        self._recalculate_dirty()
        self._refresh_dup_counts()
        self._reset()

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
            self._recalculate_dirty()
            self._refresh_dup_counts()
            self._reset()

    @Slot(str)
    def setFilter(self, text: str) -> None:
        new = text.lower()
        changed = bool(new) != bool(self._filter)
        self._filter = new
        if changed:
            self.filterChanged.emit()
        self._reset()

    @Slot()
    def discardChanges(self) -> None:
        self._entries = [{"path": e, "original": None, "is_new": False, "is_deleted": False} for e in self._original]
        self._dirty = False
        self._refresh_dup_counts()
        self._reset()

    def loadData(self, entries: list[str]) -> None:
        self._entries = [{"path": e, "original": None, "is_new": False, "is_deleted": False} for e in entries]
        self._original = list(entries)
        self._dirty = False
        self._refresh_dup_counts()
        self._reset()

    def getEntries(self) -> list[str]:
        return [e["path"] for e in self._entries if not e["is_deleted"]]

    # ------------------------------------------------------------------ internals

    def _visible(self) -> list[dict]:
        if not self._filter:
            return self._entries
        return [e for e in self._entries if self._path_matches(e["path"])]

    def _visible_indices(self) -> list[int]:
        if not self._filter:
            return list(range(len(self._entries)))
        return [i for i, e in enumerate(self._entries) if self._path_matches(e["path"])]

    def _path_matches(self, path: str) -> bool:
        return self._filter in path.lower() or self._filter in self._expand_fn(path).lower()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._refresh_dup_counts()
        self._reset()

    def _recalculate_dirty(self) -> None:
        # Compare committed entries (excluding soft-deleted) against the snapshot.
        # Catches add/delete/move/edit; reverting all changes clears _dirty.
        self._dirty = self.getEntries() != self._original
        if not self._dirty:
            for entry in self._entries:
                entry["is_new"] = False
                entry["original"] = None

    def _refresh_dup_counts(self) -> None:
        self._dup_counts = Counter(e["path"] for e in self._entries if not e["is_deleted"])

    def _reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()
        self.pendingCountChanged.emit()
