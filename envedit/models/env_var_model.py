from __future__ import annotations

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property
)


class EnvVarModel(QAbstractListModel):
    NameRole     = Qt.UserRole + 1
    ValueRole    = Qt.UserRole + 2
    ExpandedRole = Qt.UserRole + 3
    PendingRole  = Qt.UserRole + 4
    DeletedRole  = Qt.UserRole + 5

    pendingCountChanged = Signal()
    errorOccurred = Signal(str)

    def __init__(self, expand_fn=None, parent=None):
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        self._rows: list[dict] = []          # {name, value}
        self._original_rows: list[dict] = [] # snapshot for discard
        self._pending: dict[str, str | None] = {}  # name -> new value | None=delete
        self._filter: str = ""
        # name -> row dict; kept in sync with _rows so _stage and edit
        # paths don't need O(n) linear scans.
        self._by_name: dict[str, dict] = {}

    # ------------------------------------------------------------------ QML properties

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self) -> int:
        return len(self._pending)

    # ------------------------------------------------------------------ QAbstractListModel

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._visible_rows())

    def roleNames(self):
        return {
            self.NameRole:     b"name",
            self.ValueRole:    b"value",
            self.ExpandedRole: b"expanded",
            self.PendingRole:  b"isPending",
            self.DeletedRole:  b"isDeleted",
        }

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        rows = self._visible_rows()
        if index.row() >= len(rows):
            return None
        row = rows[index.row()]
        name = row["name"]
        pending_val = self._pending.get(name, ...)  # ... = not in pending

        if role == self.NameRole:
            return name
        if role == self.ValueRole:
            return self._pending[name] if (pending_val is not ... and pending_val is not None) else row["value"]
        if role == self.ExpandedRole:
            v = self._pending[name] if (pending_val is not ... and pending_val is not None) else row["value"]
            return self._expand_fn(v)
        if role == self.PendingRole:
            return pending_val is not ...
        if role == self.DeletedRole:
            return pending_val is None
        return None

    # ------------------------------------------------------------------ slots

    @Slot(str, str)
    def addVariable(self, name: str, value: str) -> None:
        name = name.strip()
        if not name:
            return
        if name in self._by_name:
            self._stage(name, value)
            return
        new_row = {"name": name, "value": ""}
        self._rows.append(new_row)
        self._rows.sort(key=lambda r: r["name"].lower())
        self._by_name[name] = new_row
        self._pending[name] = value
        self._reset()

    @Slot(int, str, str)
    def editVariable(self, index: int, name: str, value: str) -> None:
        rows = self._visible_rows()
        if index < 0 or index >= len(rows):
            return
        orig_name = rows[index]["name"]
        if orig_name != name:
            # Refuse the rename if the target name already exists — silently
            # overwriting another variable would discard its value with no
            # warning.
            if name in self._by_name:
                self.errorOccurred.emit(
                    f"A variable named '{name}' already exists."
                )
                # Snap just this row's name field back to model.name. A full
                # _reset() would rebuild the ListView's delegates and scroll
                # back to index 0, losing the user's scroll position and
                # focus.
                mi = self.index(index, 0)
                self.dataChanged.emit(mi, mi, [self.NameRole])
                return
            self._pending[orig_name] = None
            new_row = {"name": name, "value": ""}
            self._rows.append(new_row)
            self._by_name[name] = new_row
            self._pending[name] = value
            self._reset()
        else:
            self._stage(orig_name, value)

    @Slot(int)
    def deleteVariable(self, index: int) -> None:
        rows = self._visible_rows()
        if index < 0 or index >= len(rows):
            return
        name = rows[index]["name"]
        self._pending[name] = None
        self._notify_row(index)

    @Slot(int)
    def restoreVariable(self, index: int) -> None:
        rows = self._visible_rows()
        if index < 0 or index >= len(rows):
            return
        name = rows[index]["name"]
        if self._pending.get(name) is None:
            del self._pending[name]
            self._notify_row(index)

    @Slot(str)
    def setFilter(self, text: str) -> None:
        self._filter = text.lower()
        self._reset()

    @Slot()
    def discardChanges(self) -> None:
        self._rows = [dict(r) for r in self._original_rows]
        self._by_name = {r["name"]: r for r in self._rows}
        self._pending.clear()
        self._reset()

    def loadData(self, vars_: dict[str, str]) -> None:
        self._rows = [{"name": k, "value": v} for k, v in sorted(vars_.items())]
        self._original_rows = [dict(r) for r in self._rows]
        self._by_name = {r["name"]: r for r in self._rows}
        self._pending.clear()
        self._reset()

    def getPendingChanges(self) -> dict[str, str | None]:
        return dict(self._pending)

    # ------------------------------------------------------------------ internals

    def _visible_rows(self) -> list[dict]:
        if not self._filter:
            return self._rows
        return [r for r in self._rows
                if self._filter in r["name"].lower() or self._filter in r["value"].lower()]

    def _stage(self, name: str, value: str) -> None:
        row = self._by_name.get(name)
        orig = row["value"] if row is not None else None
        old_count = len(self._pending)
        if value == orig:
            self._pending.pop(name, None)
        else:
            self._pending[name] = value
        idx = next((i for i, r in enumerate(self._visible_rows()) if r["name"] == name), -1)
        if idx >= 0:
            mi = self.index(idx, 0)
            self.dataChanged.emit(mi, mi, [self.ValueRole, self.ExpandedRole, self.PendingRole])
        if len(self._pending) != old_count:
            self.pendingCountChanged.emit()

    def _notify_row(self, index: int) -> None:
        mi = self.index(index, 0)
        self.dataChanged.emit(mi, mi, list(self.roleNames().keys()))
        self.pendingCountChanged.emit()

    def _reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()
        self.pendingCountChanged.emit()
