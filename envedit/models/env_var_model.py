from __future__ import annotations

import re

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, Qt, Signal, Slot, Property
)


# Identifier rules matching the Unix env.sh parser: first char letter or
# underscore, rest alphanumeric or underscore. Capped at 256 chars to keep
# the UI sane (registry max is much larger but no real var needs it).
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,255}$")
_VAR_NAME_HELP = (
    "Names must start with a letter or underscore and contain only letters, "
    "digits, or underscores."
)
_VAR_VALUE_HELP = "Variable values cannot contain newline or null characters."

# Names that belong to a dedicated tab and must not appear in the variable
# table. Case-insensitive so that `Path`/`path`/`PATH` all match on Windows.
_RESERVED_NAMES_UPPER = {"PATH"}
_RESERVED_MSG = "PATH is managed on the PATH tab — switch tabs to edit it."


def _value_rejection_reason(value: str) -> str | None:
    if "\n" in value or "\r" in value or "\x00" in value:
        return _VAR_VALUE_HELP
    return None


class EnvVarModel(QAbstractListModel):
    NameRole     = Qt.UserRole + 1
    ValueRole    = Qt.UserRole + 2
    ExpandedRole = Qt.UserRole + 3
    PendingRole  = Qt.UserRole + 4
    DeletedRole  = Qt.UserRole + 5
    NewRole      = Qt.UserRole + 6

    pendingCountChanged = Signal()
    errorOccurred = Signal(str)
    infoOccurred = Signal(str)

    def __init__(self, expand_fn=None, parent=None):
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        self._rows: list[dict] = []          # {name, value}
        self._original_rows: list[dict] = [] # snapshot for discard
        self._pending: dict[str, str | None] = {}  # name -> new value | None=delete
        self._new_names: set[str] = set()  # added but never applied
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
            self.NewRole:      b"isNew",
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
        if role == self.NewRole:
            return name in self._new_names
        return None

    # ------------------------------------------------------------------ slots

    @Slot(str, str, result=bool)
    def addVariable(self, name: str, value: str) -> bool:
        name = name.strip()
        if not name:
            return False
        if not _VAR_NAME_RE.match(name):
            self.errorOccurred.emit(f"Invalid variable name '{name}'. {_VAR_NAME_HELP}")
            return False
        if name.upper() in _RESERVED_NAMES_UPPER:
            self.errorOccurred.emit(_RESERVED_MSG)
            return False
        reason = _value_rejection_reason(value)
        if reason is not None:
            self.errorOccurred.emit(reason)
            return False
        if name in self._by_name:
            existing_val = self._by_name[name]["value"]
            was_pending_deletion = (
                name in self._pending and self._pending[name] is None
            )
            self._stage(name, value)
            if was_pending_deletion:
                self.infoOccurred.emit(f"'{name}' restored — pending deletion cancelled.")
            elif value == existing_val and name not in self._new_names:
                self.infoOccurred.emit(
                    f"'{name}' already exists with that value — nothing changed."
                )
            else:
                self.infoOccurred.emit(
                    f"'{name}' already existed — its value was replaced."
                )
            return True
        new_row = {"name": name, "value": ""}
        self._rows.append(new_row)
        self._rows.sort(key=lambda r: r["name"].lower())
        self._by_name[name] = new_row
        self._pending[name] = value
        self._new_names.add(name)
        self._reset()
        return True

    @Slot(str, result=bool)
    def hasVariable(self, name: str) -> bool:
        return name.strip() in self._by_name

    @Slot(int, str, str)
    def editVariable(self, index: int, name: str, value: str) -> None:
        rows = self._visible_rows()
        if index < 0 or index >= len(rows):
            return
        reason = _value_rejection_reason(value)
        if reason is not None:
            self.errorOccurred.emit(reason)
            return
        orig_name = rows[index]["name"]
        if orig_name != name:
            if not _VAR_NAME_RE.match(name):
                self.errorOccurred.emit(
                    f"Invalid variable name '{name}'. {_VAR_NAME_HELP}"
                )
                mi = self.index(index, 0)
                self.dataChanged.emit(mi, mi, [self.NameRole])
                return
            if name.upper() in _RESERVED_NAMES_UPPER:
                self.errorOccurred.emit(_RESERVED_MSG)
                mi = self.index(index, 0)
                self.dataChanged.emit(mi, mi, [self.NameRole])
                return
            collided = self._by_name.get(name)
            if collided is not None:
                is_pending_deleted = (
                    name in self._pending and self._pending[name] is None
                )
                if not is_pending_deleted:
                    # Live collision (the name belongs to a non-deleted row).
                    # Refuse rather than silently overwrite the other row.
                    self.errorOccurred.emit(
                        f"A variable named '{name}' already exists."
                    )
                    mi = self.index(index, 0)
                    self.dataChanged.emit(mi, mi, [self.NameRole])
                    return
                # Target name is pending-deleted (the user renamed B→A and is
                # now renaming A back to B, or similar). Undelete it and
                # stage a value edit so the rename round-trips to a restore.
                del self._pending[name]
                if orig_name in self._new_names:
                    # The "new" row B was scratch; drop it entirely.
                    self._rows.remove(self._by_name[orig_name])
                    del self._by_name[orig_name]
                    del self._pending[orig_name]
                    self._new_names.discard(orig_name)
                else:
                    # orig_name is an original row; mark it deleted so the
                    # rename actually removes it on apply (not just unlinks B).
                    self._pending[orig_name] = None
                if value != collided["value"]:
                    self._pending[name] = value
                self._reset()
                return
            if orig_name in self._new_names:
                self._rows.remove(self._by_name[orig_name])
                del self._by_name[orig_name]
                del self._pending[orig_name]
                self._new_names.discard(orig_name)
            else:
                self._pending[orig_name] = None
            new_row = {"name": name, "value": ""}
            self._rows.append(new_row)
            self._by_name[name] = new_row
            self._pending[name] = value
            self._new_names.add(name)
            self._reset()
        else:
            self._stage(orig_name, value)

    @Slot(int)
    def deleteVariable(self, index: int) -> None:
        rows = self._visible_rows()
        if index < 0 or index >= len(rows):
            return
        name = rows[index]["name"]
        if name in self._new_names:
            self._rows.remove(self._by_name[name])
            del self._by_name[name]
            del self._pending[name]
            self._new_names.discard(name)
            self._reset()
        else:
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
        self._new_names.clear()
        self._reset()

    def loadData(self, vars_: dict[str, str]) -> None:
        self._rows = [{"name": k, "value": v} for k, v in sorted(vars_.items(), key=lambda kv: kv[0].lower())]
        self._original_rows = [dict(r) for r in self._rows]
        self._by_name = {r["name"]: r for r in self._rows}
        self._pending.clear()
        self._new_names.clear()
        self._reset()

    def getPendingChanges(self) -> dict[str, str | None]:
        return dict(self._pending)

    def getDiffOperations(self) -> list[dict]:
        """Structured diff of pending changes against the loaded snapshot.

        Each operation is one of:
          {"op": "add",    "name", "new_value"}
          {"op": "remove", "name", "old_value"}
          {"op": "edit",   "name", "old_value", "new_value"}

        Sorted case-insensitively by name for stable rendering. Add vs.
        edit is decided by `_new_names` so a name re-added after delete
        still reports as ADD.
        """
        orig_by_name = {r["name"]: r["value"] for r in self._original_rows}
        ops: list[dict] = []
        for name in sorted(self._pending.keys(), key=str.lower):
            pending_val = self._pending[name]
            if pending_val is None:
                ops.append({
                    "op": "remove",
                    "name": name,
                    "old_value": orig_by_name.get(name, ""),
                })
            elif name in self._new_names:
                ops.append({
                    "op": "add",
                    "name": name,
                    "new_value": pending_val,
                })
            else:
                ops.append({
                    "op": "edit",
                    "name": name,
                    "old_value": orig_by_name.get(name, ""),
                    "new_value": pending_val,
                })
        return ops

    # ------------------------------------------------------------------ internals

    def _visible_rows(self) -> list[dict]:
        if not self._filter:
            return self._rows
        def _match(r: dict) -> bool:
            name = r["name"]
            pv = self._pending.get(name, ...)
            val = self._pending[name] if (pv is not ... and pv is not None) else r["value"]
            return (self._filter in name.lower()
                    or self._filter in val.lower()
                    or self._filter in self._expand_fn(val).lower())
        return [r for r in self._rows if _match(r)]

    def _stage(self, name: str, value: str) -> None:
        row = self._by_name.get(name)
        orig = row["value"] if row is not None else None
        old_count = len(self._pending)
        if value == orig and name not in self._new_names:
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
