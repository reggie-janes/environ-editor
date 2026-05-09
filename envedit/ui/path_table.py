from __future__ import annotations

import os
from collections import Counter

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from envedit.ui.dialogs import AddPathEntryDialog, ConfirmDeleteDialog
from envedit.ui.env_table import _ExpandedValueDelegate, _MONO_ITALIC, _EXPANDED_FG, _apply_delete_style

_MONO = QFont("Consolas, JetBrains Mono, Menlo, monospace")
_PENDING_BG = QColor(255, 255, 200)
_DUPLICATE_BG = QColor(255, 200, 100)

COL_PATH = 0
COL_EXPANDED = 1
COL_STATUS = 2
COL_ACTIONS = 3


def _path_status(path: str) -> str:
    if os.path.islink(path):
        return "🔗"
    if os.path.isdir(path):
        return "✅"
    return "⚠"


class _DraggableTable(QTableWidget):
    """QTableWidget subclass that intercepts drag-drop and emits row_moved
    instead of letting QTableWidget's broken internal-move machinery run."""

    row_moved = Signal(int, int)  # src_row, dst_row

    def dropEvent(self, event) -> None:
        if event.source() is not self:
            super().dropEvent(event)
            return

        src_rows = sorted({i.row() for i in self.selectedIndexes()})
        if not src_rows:
            event.ignore()
            return
        src_row = src_rows[0]

        target = self.indexAt(event.position().toPoint())
        dst_row = target.row() if target.isValid() else self.rowCount() - 1

        if src_row != dst_row:
            self.row_moved.emit(src_row, dst_row)
        event.accept()  # skip super() — prevents the "invalid index" dataChanged error


class PathTableWidget(QWidget):
    changed = Signal()

    def __init__(self, expand_fn=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        self._original: list[str] = []
        self._entries: list[str] = []
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter entries…")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._table = _DraggableTable(0, 4)
        self._table.setHorizontalHeaderLabels(["Path Entry", "Expanded", "Status", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(COL_PATH, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(COL_EXPANDED, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_STATUS, 60)
        self._table.setColumnWidth(COL_ACTIONS, 110)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._table.setDragEnabled(True)
        self._table.setAcceptDrops(True)
        self._table.setDropIndicatorShown(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                    QAbstractItemView.EditTrigger.EditKeyPressed)
        self._table.setItemDelegateForColumn(COL_EXPANDED, _ExpandedValueDelegate(self._table))
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.row_moved.connect(self._on_row_moved)
        layout.addWidget(self._table)

    def load(self, entries: list[str]) -> None:
        self._original = list(entries)
        self._entries = list(entries)
        self._dirty = False
        self._rebuild_table()

    def add_entry(self) -> None:
        dlg = AddPathEntryDialog(self, expand_fn=self._expand_fn)
        if dlg.exec():
            path = dlg.result_path()
            if path:
                self._entries.append(path)
                self._dirty = True
                self._rebuild_table()
                self.changed.emit()

    def remove_duplicates(self) -> None:
        seen: set[str] = set()
        new_entries = []
        for e in self._entries:
            if e not in seen:
                seen.add(e)
                new_entries.append(e)
        if len(new_entries) != len(self._entries):
            self._entries = new_entries
            self._dirty = True
            self._rebuild_table()
            self.changed.emit()

    def get_pending_entries(self) -> list[str] | None:
        return list(self._entries) if self._dirty else None

    def clear_pending(self) -> None:
        self._original = list(self._entries)
        self._dirty = False
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        counts = Counter(self._entries)
        for i, entry in enumerate(self._entries):
            self._insert_row(i, entry, duplicate=(counts[entry] > 1))
        self._table.blockSignals(False)

    def _insert_row(self, index: int, entry: str, duplicate: bool = False) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        path_item = QTableWidgetItem(entry)
        path_item.setFont(_MONO)

        expanded = self._expand_fn(entry)
        exp_item = QTableWidgetItem(expanded)
        exp_item.setFont(_MONO_ITALIC)
        exp_item.setForeground(_EXPANDED_FG)

        status = _path_status(expanded)
        status_item = QTableWidgetItem(status)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        actions_widget = self._make_actions_widget(row)

        self._table.setItem(row, COL_PATH, path_item)
        self._table.setItem(row, COL_EXPANDED, exp_item)
        self._table.setItem(row, COL_STATUS, status_item)
        self._table.setCellWidget(row, COL_ACTIONS, actions_widget)

        if duplicate:
            for col in range(COL_ACTIONS):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(_DUPLICATE_BG)
        elif self._dirty:
            for col in range(COL_ACTIONS):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(_PENDING_BG)

    def _make_actions_widget(self, row: int) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(2)

        up_btn = QPushButton("⬆")
        up_btn.setToolTip("Move up")
        up_btn.setFixedWidth(28)
        up_btn.clicked.connect(lambda: self._move_row(row, -1))

        down_btn = QPushButton("⬇")
        down_btn.setToolTip("Move down")
        down_btn.setFixedWidth(28)
        down_btn.clicked.connect(lambda: self._move_row(row, 1))

        del_btn = QPushButton("✕")
        del_btn.setToolTip("Delete entry")
        del_btn.setFixedWidth(28)
        _apply_delete_style(del_btn)
        del_btn.clicked.connect(lambda: self._delete_row(row))

        h.addWidget(up_btn)
        h.addWidget(down_btn)
        h.addWidget(del_btn)
        return w

    def _move_row(self, row: int, delta: int) -> None:
        new_row = row + delta
        if new_row < 0 or new_row >= len(self._entries):
            return
        self._entries[row], self._entries[new_row] = self._entries[new_row], self._entries[row]
        self._dirty = True
        self._rebuild_table()
        self.changed.emit()

    def _on_row_moved(self, src: int, dst: int) -> None:
        entry = self._entries.pop(src)
        self._entries.insert(dst, entry)
        self._dirty = True
        self._rebuild_table()
        self.changed.emit()

    def _delete_row(self, row: int) -> None:
        if row >= len(self._entries):
            return
        entry = self._entries[row]
        dlg = ConfirmDeleteDialog(entry, self)
        if dlg.exec():
            self._entries.pop(row)
            self._dirty = True
            self._rebuild_table()
            self.changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != COL_PATH:
            return
        row = item.row()
        if row < len(self._entries):
            self._entries[row] = item.text()
            self._dirty = True
            self.changed.emit()

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for row in range(self._table.rowCount()):
            entry = (self._table.item(row, COL_PATH) or QTableWidgetItem()).text().lower()
            self._table.setRowHidden(row, text not in entry)
