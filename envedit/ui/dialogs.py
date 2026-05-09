from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)


class AddVariableDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 expand_fn=None, name: str = "", value: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Variable")
        self.setMinimumWidth(480)
        self._expand_fn = expand_fn or (lambda v: v)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(name)
        self._value_edit = QLineEdit(value)
        self._preview = QLabel()
        self._preview.setStyleSheet("color: gray; font-style: italic;")
        self._preview.setWordWrap(True)

        form.addRow("Name:", self._name_edit)
        form.addRow("Value:", self._value_edit)
        form.addRow("Expanded:", self._preview)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._value_edit.textChanged.connect(self._update_preview)
        self._update_preview(value)

    def _update_preview(self, text: str) -> None:
        expanded = self._expand_fn(text)
        self._preview.setText(expanded if expanded != text else "(same as value)")

    def result_name(self) -> str:
        return self._name_edit.text().strip()

    def result_value(self) -> str:
        return self._value_edit.text()


class AddPathEntryDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, expand_fn=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add PATH Entry")
        self.setMinimumWidth(480)
        self._expand_fn = expand_fn or (lambda v: v)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self._path_edit = QLineEdit()
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        row.addWidget(self._path_edit)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self._status = QLabel()
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._path_edit.textChanged.connect(self._update_status)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self._path_edit.setText(folder)

    def _update_status(self, text: str) -> None:
        expanded = self._expand_fn(text)
        if os.path.islink(expanded):
            self._status.setText("🔗 Symlink")
        elif os.path.isdir(expanded):
            self._status.setText("✅ Directory exists")
        else:
            self._status.setText("⚠ Does not exist")

    def result_path(self) -> str:
        return self._path_edit.text().strip()


class ConfirmDeleteDialog(QDialog):
    def __init__(self, item_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Delete")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'Delete "{item_name}"? This cannot be undone.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        delete_btn = buttons.addButton("Delete", QDialogButtonBox.ButtonRole.DestructiveRole)
        delete_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class UnsavedChangesDialog(QDialog):
    Apply = 1
    Discard = 2
    Cancel = 0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Unsaved Changes")
        self._choice = self.Cancel
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("You have unsaved changes. What would you like to do?"))
        btns = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        discard_btn = QPushButton("Discard")
        cancel_btn = QPushButton("Cancel")
        apply_btn.clicked.connect(self._apply)
        discard_btn.clicked.connect(self._discard)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(apply_btn)
        btns.addWidget(discard_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _apply(self) -> None:
        self._choice = self.Apply
        self.accept()

    def _discard(self) -> None:
        self._choice = self.Discard
        self.accept()

    def choice(self) -> int:
        return self._choice


class ElevationDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Administrator Privileges Required")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Modifying system variables requires administrator privileges.\nProceed?"
        ))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.addButton("🛡 Continue as Admin",
                                   QDialogButtonBox.ButtonRole.AcceptRole)
        ok_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class DiffDialog(QDialog):
    def __init__(self, diff_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pending Changes")
        self.setMinimumSize(560, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("The following changes will be applied:"))
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFontFamily("monospace")
        view.setPlainText(diff_text)
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
