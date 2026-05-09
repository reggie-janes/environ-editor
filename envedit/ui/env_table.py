from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from envedit.ui.dialogs import AddVariableDialog, ConfirmDeleteDialog

_MONO = QFont("Consolas, JetBrains Mono, Menlo, monospace")
_DELETE_RED = QColor("#e05555")


def _apply_delete_style(btn: QPushButton) -> None:
    """Red text, no stylesheet — background inherits from the app palette correctly on theme switch."""
    pal = btn.palette()
    pal.setColor(QPalette.ColorRole.ButtonText, _DELETE_RED)
    btn.setPalette(pal)
    font = btn.font()
    font.setBold(True)
    btn.setFont(font)
_MONO_ITALIC = QFont(_MONO)
_MONO_ITALIC.setItalic(True)
_EXPANDED_FG = QColor(150, 150, 150)
_PENDING_BG = QColor(255, 255, 200)
_DELETED_BG = QColor(255, 200, 200)


class _ExpandedValueDelegate(QStyledItemDelegate):
    """Read-only delegate: opens a selectable QLineEdit but never writes back."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setReadOnly(True)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor: QLineEdit, index):
        editor.setText(index.data() or "")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        pass  # never write back

COL_NAME = 0
COL_VALUE = 1
COL_EXPANDED = 2
COL_ACTIONS = 3


class EnvTableWidget(QWidget):
    changed = Signal()

    def __init__(self, expand_fn=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expand_fn = expand_fn or (lambda v: v)
        self._pending: dict[str, str | None] = {}  # name -> new value or None=delete

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter by name or value…")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Variable Name", "Value", "Expanded Value", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(COL_VALUE, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(COL_EXPANDED, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_NAME, 200)
        self._table.setColumnWidth(COL_ACTIONS, 90)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                    QAbstractItemView.EditTrigger.EditKeyPressed)
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)
        self._table.setItemDelegateForColumn(COL_EXPANDED, _ExpandedValueDelegate(self._table))
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)

    def load(self, vars_: dict[str, str]) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._pending.clear()
        for name, value in sorted(vars_.items()):
            self._insert_row(name, value, pending=False)
        self._table.blockSignals(False)

    def add_variable(self) -> None:
        dlg = AddVariableDialog(self, expand_fn=self._expand_fn)
        if dlg.exec():
            name, value = dlg.result_name(), dlg.result_value()
            if not name:
                return
            self._pending[name] = value
            self._insert_row(name, value, pending=True)
            self.changed.emit()

    def get_pending_changes(self) -> dict[str, str | None]:
        return dict(self._pending)

    def clear_pending(self) -> None:
        self._pending.clear()
        self._refresh_highlights()

    def _insert_row(self, name: str, value: str, pending: bool) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        name_item = QTableWidgetItem(name)
        name_item.setFont(_MONO)
        value_item = QTableWidgetItem(value)
        value_item.setFont(_MONO)

        expanded = self._expand_fn(value)
        exp_item = QTableWidgetItem(expanded)
        exp_item.setFont(_MONO_ITALIC)
        exp_item.setForeground(_EXPANDED_FG)

        actions_widget = self._make_actions_widget(name)

        self._table.setItem(row, COL_NAME, name_item)
        self._table.setItem(row, COL_VALUE, value_item)
        self._table.setItem(row, COL_EXPANDED, exp_item)
        self._table.setCellWidget(row, COL_ACTIONS, actions_widget)

        if pending:
            self._highlight_row(row, _PENDING_BG)

    def _make_actions_widget(self, name: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        btn = QPushButton("✕")
        btn.setToolTip(f"Delete {name}")
        btn.setFixedWidth(32)
        _apply_delete_style(btn)
        btn.clicked.connect(lambda: self._delete_row_for_name(name))
        h.addWidget(btn)
        return w

    def _delete_row_for_name(self, name: str) -> None:
        dlg = ConfirmDeleteDialog(name, self)
        if dlg.exec():
            for row in range(self._table.rowCount()):
                item = self._table.item(row, COL_NAME)
                if item and item.text() == name:
                    self._highlight_row(row, _DELETED_BG)
                    self._pending[name] = None
                    self.changed.emit()
                    break

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if col not in (COL_NAME, COL_VALUE):
            return

        name_item = self._table.item(row, COL_NAME)
        value_item = self._table.item(row, COL_VALUE)
        if not name_item or not value_item:
            return

        name = name_item.text()
        value = value_item.text()
        expanded = self._expand_fn(value)

        self._table.blockSignals(True)
        exp_item = self._table.item(row, COL_EXPANDED)
        if exp_item:
            exp_item.setText(expanded)
        self._table.blockSignals(False)

        self._pending[name] = value
        self._highlight_row(row, _PENDING_BG)
        self.changed.emit()

    def _highlight_row(self, row: int, color: QColor) -> None:
        for col in range(self._table.columnCount() - 1):  # skip actions column
            item = self._table.item(row, col)
            if item:
                item.setBackground(color)

    def _refresh_highlights(self) -> None:
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, COL_NAME)
            if name_item:
                color = _PENDING_BG if name_item.text() in self._pending else QColor(0, 0, 0, 0)
                self._highlight_row(row, color)

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for row in range(self._table.rowCount()):
            name = (self._table.item(row, COL_NAME) or QTableWidgetItem()).text().lower()
            value = (self._table.item(row, COL_VALUE) or QTableWidgetItem()).text().lower()
            self._table.setRowHidden(row, text not in name and text not in value)
