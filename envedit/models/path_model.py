from __future__ import annotations

import bisect
import os
from collections import Counter

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property
)


def _lis_values(seq: list[int]) -> set[int]:
    """Return the set of values that appear in a longest increasing subsequence."""
    if not seq:
        return set()
    n = len(seq)
    tails: list[int] = []          # smallest tail for subsequences of each length
    prev_idx: list[int] = [-1] * n # predecessor index in seq for each element
    tail_seq_idx: list[int] = []   # which seq index set each tail
    for i, x in enumerate(seq):
        pos = bisect.bisect_left(tails, x)
        if pos == len(tails):
            tails.append(x)
            tail_seq_idx.append(i)
        else:
            tails[pos] = x
            tail_seq_idx[pos] = i
        prev_idx[i] = tail_seq_idx[pos - 1] if pos > 0 else -1
    result: set[int] = set()
    idx = tail_seq_idx[-1]
    while idx != -1:
        result.add(seq[idx])
        idx = prev_idx[idx]
    return result


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
    NewRole       = Qt.UserRole + 7

    pendingCountChanged = Signal()
    filterChanged = Signal()
    errorOccurred = Signal(str)

    def __init__(self, expand_fn=None, parent=None):
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        # Each entry: {"path": str, "original": str | None, "is_new": bool,
        #              "is_deleted": bool, "original_index": int | None}
        # "original" holds the pre-edit value on first user edit; None = unedited.
        # "original_index" is the 0-indexed position in self._original at load
        # time; None for entries added by the user. Used by getDiffOperations
        # to identify which row is which even when paths repeat.
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
            self.NewRole:       b"isNew",
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
        if role == self.NewRole:
            return entry["is_new"]
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
        self._entries.append({"path": path, "original": None, "is_new": True, "is_deleted": False, "original_index": None})
        self._mark_dirty()

    @Slot(int, str)
    def editEntry(self, index: int, path: str) -> None:
        real = self._visible_indices()
        if index < 0 or index >= len(real):
            return
        entry = self._entries[real[index]]
        if entry["path"] == path:
            return
        reason = _path_rejection_reason(path)
        if reason is not None:
            self.errorOccurred.emit(reason)
            # Rebind the field to the current stored value.
            if self.rowCount() > 0:
                self.dataChanged.emit(self.index(0), self.index(self.rowCount() - 1))
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
        changed = False
        survivors: list[dict] = []
        for e in self._entries:
            if e["path"] in seen:
                if e["is_new"]:
                    # Scratch row; drop it entirely — no original position to record.
                    changed = True
                    continue
                # Original duplicate — soft-delete so getDiffOperations reports
                # a REMOVE op with the correct old_pos for the diff dialog.
                e["is_deleted"] = True
                changed = True
            else:
                seen.add(e["path"])
            survivors.append(e)
        if changed:
            self._entries = survivors
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
        self._entries = [
            {"path": e, "original": None, "is_new": False, "is_deleted": False, "original_index": i}
            for i, e in enumerate(self._original)
        ]
        self._dirty = False
        self._refresh_dup_counts()
        self._reset()

    def loadData(self, entries: list[str]) -> None:
        self._entries = [
            {"path": e, "original": None, "is_new": False, "is_deleted": False, "original_index": i}
            for i, e in enumerate(entries)
        ]
        self._original = list(entries)
        self._dirty = False
        self._refresh_dup_counts()
        self._reset()

    def getEntries(self) -> list[str]:
        return [e["path"] for e in self._entries if not e["is_deleted"]]

    def getDiffOperations(self) -> list[dict]:
        """Structured diff of pending changes against the loaded snapshot.

        Each operation is one of:
          {"op": "add",    "path", "new_pos"}
          {"op": "remove", "path", "old_pos"}
          {"op": "edit",   "old_path", "new_path", "old_pos", "new_pos"}
          {"op": "move",   "path", "old_pos", "new_pos"}

        Per-entry metadata (`is_new`, `is_deleted`, `original`, `original_index`)
        is used instead of comparing path strings so duplicates round-trip
        correctly — deleting one of two identical entries reports REMOVE for
        the row the user clicked, not "(no changes)".

        MOVE detection uses the longest increasing subsequence (LIS) of
        original_index values among pure survivors. Survivors whose
        original_index is in the LIS preserved their relative order and get
        no MOVE; only entries that left the LIS are emitted as moves.
        This collapses "N entries shifted by 1 deliberate move" into a
        single MOVE op instead of N spurious ones.
        """
        ops: list[dict] = []

        # Build the LIS over pure survivors (non-new, non-deleted, unedited)
        # to determine which entries preserved their relative order.
        pure_orig_indices = [
            e["original_index"]
            for e in self._entries
            if not e["is_deleted"] and not e["is_new"] and e["original"] is None
        ]
        lis = _lis_values(pure_orig_indices)

        new_pos = 0
        for entry in self._entries:
            if entry["is_deleted"]:
                old_path = entry["original"] if entry["original"] is not None else entry["path"]
                ops.append({
                    "op": "remove",
                    "path": old_path,
                    "old_pos": entry["original_index"] if entry["original_index"] is not None else 0,
                })
                continue
            current_pos = new_pos
            new_pos += 1
            if entry["is_new"]:
                ops.append({"op": "add", "path": entry["path"], "new_pos": current_pos})
                continue
            orig_idx = entry["original_index"]
            if entry["original"] is not None:
                ops.append({
                    "op": "edit",
                    "old_path": entry["original"],
                    "new_path": entry["path"],
                    "old_pos": orig_idx,
                    "new_pos": current_pos,
                })
                # EDIT already carries the position change; skip a separate MOVE.
                continue
            # Pure survivor: emit MOVE only if not in the LIS.
            if orig_idx not in lis:
                ops.append({
                    "op": "move",
                    "path": entry["path"],
                    "old_pos": orig_idx,
                    "new_pos": current_pos,
                })
        return ops

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
            # Re-baseline metadata so a subsequent edit diffs against the now-clean
            # state, not against pre-revert state. Reassign original_index by
            # current position among non-deleted survivors.
            new_idx = 0
            for entry in self._entries:
                if entry["is_deleted"]:
                    continue
                entry["is_new"] = False
                entry["original"] = None
                entry["original_index"] = new_idx
                new_idx += 1

    def _refresh_dup_counts(self) -> None:
        self._dup_counts = Counter(e["path"] for e in self._entries if not e["is_deleted"])

    def _reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()
        self.pendingCountChanged.emit()
