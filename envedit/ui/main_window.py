from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMainWindow, QMessageBox,
    QPushButton, QSizePolicy, QTabWidget, QToolBar,
    QVBoxLayout, QWidget,
)

from envedit.core.env_backend import EnvBackend, get_backend
from envedit.core.privilege import is_elevated
from envedit.ui.dialogs import DiffDialog, ElevationDialog, UnsavedChangesDialog
from envedit.ui.env_table import EnvTableWidget
from envedit.ui.path_table import PathTableWidget
from envedit.ui.theme import DARK, ThemeManager


class _TabPage(QWidget):
    def __init__(self, table_widget: QWidget, toolbar: QToolBar,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(toolbar)
        layout.addWidget(table_widget)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EnvEdit — Environment Variable Editor")
        self.setMinimumSize(900, 600)

        self._backend: EnvBackend = get_backend()

        self._settings = QSettings("EnvEdit", "EnvEdit")
        self._restore_geometry()

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._prev_tab = 0
        self.setCentralWidget(self._tabs)

        self._build_tabs()
        self._build_theme_toggle()

        self._load_all()

    # ------------------------------------------------------------------ build

    def _build_tabs(self) -> None:
        expand = self._backend.expand_value

        self._user_var_table = EnvTableWidget(expand_fn=expand)
        self._user_path_table = PathTableWidget(expand_fn=expand)
        self._sys_var_table = EnvTableWidget(expand_fn=expand)
        self._sys_path_table = PathTableWidget(expand_fn=expand)

        self._user_var_table.changed.connect(lambda: self._on_changed(0))
        self._user_path_table.changed.connect(lambda: self._on_changed(1))
        self._sys_var_table.changed.connect(lambda: self._on_changed(2))
        self._sys_path_table.changed.connect(lambda: self._on_changed(3))

        specs = [
            ("User Variables",  self._user_var_table,  False),
            ("User PATH",       self._user_path_table, False),
            ("System Variables",self._sys_var_table,   True),
            ("System PATH",     self._sys_path_table,  True),
        ]
        self._apply_btns: list[QPushButton] = []
        for title, table, is_system in specs:
            toolbar, apply_btn = self._make_toolbar(table, is_system)
            self._apply_btns.append(apply_btn)
            page = _TabPage(table, toolbar)
            label = f"{'🛡 ' if is_system and not is_elevated() else ''}{title}"
            self._tabs.addTab(page, label)

    def _make_toolbar(self, table: QWidget, is_system: bool) -> tuple[QToolBar, QPushButton]:
        bar = QToolBar()
        bar.setMovable(False)

        add_btn = QPushButton("+ Add")
        add_btn.setToolTip("Add new entry")
        reload_btn = QPushButton("↺ Reload")
        reload_btn.setToolTip("Reload from system")
        apply_btn = QPushButton("✓ Apply Changes")
        apply_btn.setToolTip("Commit all pending changes")
        apply_btn.setEnabled(False)

        if isinstance(table, EnvTableWidget):
            add_btn.clicked.connect(table.add_variable)
        else:
            add_btn.clicked.connect(table.add_entry)
            dedup_btn = QPushButton("Remove Duplicates")
            dedup_btn.setToolTip("Remove duplicate PATH entries")
            dedup_btn.clicked.connect(table.remove_duplicates)
            bar.addWidget(dedup_btn)

        reload_btn.clicked.connect(lambda: self._reload_tab(self._tabs.indexOf(
            self._tabs.currentWidget())))
        apply_btn.clicked.connect(lambda: self._apply_tab(self._tabs.indexOf(
            self._tabs.currentWidget())))

        bar.addWidget(add_btn)
        bar.addWidget(reload_btn)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        bar.addWidget(apply_btn)
        return bar, apply_btn

    def _build_theme_toggle(self) -> None:
        self._theme_btn = QPushButton()
        self._update_theme_icon()
        self._theme_btn.setToolTip("Toggle light/dark theme")
        self._theme_btn.setFlat(True)
        self._theme_btn.clicked.connect(self._toggle_theme)
        # Add to the status bar area via a small toolbar
        tb = QToolBar()
        tb.setMovable(False)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(self._theme_btn)
        self.addToolBar(tb)

    # ------------------------------------------------------------------ data

    def _load_all(self) -> None:
        self._user_var_table.load(self._backend.get_user_vars())
        self._user_path_table.load(self._backend.get_user_path())
        self._sys_var_table.load(self._backend.get_system_vars())
        self._sys_path_table.load(self._backend.get_system_path())

    def _reload_tab(self, idx: int) -> None:
        if idx == 0:
            self._user_var_table.load(self._backend.get_user_vars())
        elif idx == 1:
            self._user_path_table.load(self._backend.get_user_path())
        elif idx == 2:
            self._sys_var_table.load(self._backend.get_system_vars())
        elif idx == 3:
            self._sys_path_table.load(self._backend.get_system_path())
        self._apply_btns[idx].setEnabled(False)

    def _apply_tab(self, idx: int) -> None:
        if idx in (2, 3) and not is_elevated():
            dlg = ElevationDialog(self)
            if not dlg.exec():
                return
            from envedit.core.privilege import request_elevation_and_apply
            # Build changes payload and hand off to elevated process
            if idx == 2:
                changes = self._sys_var_table.get_pending_changes()
                request_elevation_and_apply({"system_vars": changes})
            else:
                entries = self._sys_path_table.get_pending_entries()
                if entries is not None:
                    request_elevation_and_apply({"system_path": entries})
            return

        diff_lines: list[str] = []
        if idx == 0:
            changes = self._user_var_table.get_pending_changes()
            diff_lines = [f"  {k} = {v!r}" if v else f"  DELETE {k}" for k, v in changes.items()]
        elif idx == 1:
            entries = self._user_path_table.get_pending_entries()
            diff_lines = [f"  {e}" for e in (entries or [])]
        elif idx == 2:
            changes = self._sys_var_table.get_pending_changes()
            diff_lines = [f"  {k} = {v!r}" if v else f"  DELETE {k}" for k, v in changes.items()]
        elif idx == 3:
            entries = self._sys_path_table.get_pending_entries()
            diff_lines = [f"  {e}" for e in (entries or [])]

        if not diff_lines:
            return

        dlg = DiffDialog("\n".join(diff_lines), self)
        if not dlg.exec():
            return

        try:
            if idx == 0:
                self._backend.apply_user_vars(self._user_var_table.get_pending_changes())
                self._user_var_table.clear_pending()
            elif idx == 1:
                entries = self._user_path_table.get_pending_entries()
                if entries is not None:
                    self._backend.apply_user_path(entries)
                self._user_path_table.clear_pending()
            elif idx == 2:
                self._backend.apply_system_vars(self._sys_var_table.get_pending_changes())
                self._sys_var_table.clear_pending()
            elif idx == 3:
                entries = self._sys_path_table.get_pending_entries()
                if entries is not None:
                    self._backend.apply_system_path(entries)
                self._sys_path_table.clear_pending()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to apply changes:\n{exc}")
            return

        self._apply_btns[idx].setEnabled(False)

    # ---------------------------------------------------------------- signals

    def _on_changed(self, tab_idx: int) -> None:
        self._apply_btns[tab_idx].setEnabled(True)

    def _on_tab_changed(self, new_idx: int) -> None:
        prev = self._prev_tab
        self._prev_tab = new_idx
        if self._apply_btns[prev].isEnabled():
            dlg = UnsavedChangesDialog(self)
            if dlg.exec():
                choice = dlg.choice()
                if choice == UnsavedChangesDialog.Apply:
                    self._apply_tab(prev)
                elif choice == UnsavedChangesDialog.Discard:
                    self._reload_tab(prev)
                    self._apply_btns[prev].setEnabled(False)

    def _toggle_theme(self) -> None:
        from PySide6.QtWidgets import QApplication
        ThemeManager.toggle(QApplication.instance())
        self._update_theme_icon()

    def _update_theme_icon(self) -> None:
        self._theme_btn.setText("☀" if ThemeManager.current() == DARK else "🌙")

    # --------------------------------------------------------------- geometry

    def _restore_geometry(self) -> None:
        geom = self._settings.value("window/geometry")
        if geom:
            self.restoreGeometry(geom)

    def show(self) -> None:
        # showMaximized must be called instead of show() for reliable maximized restore on Windows.
        if self._settings.value("window/maximized", False, type=bool):
            self.showMaximized()
        else:
            super().show()

    def closeEvent(self, event) -> None:
        pending_tabs = [i for i, btn in enumerate(self._apply_btns) if btn.isEnabled()]
        if pending_tabs:
            dlg = UnsavedChangesDialog(self)
            if dlg.exec():
                choice = dlg.choice()
                if choice == UnsavedChangesDialog.Apply:
                    for i in pending_tabs:
                        self._apply_tab(i)
                elif choice == UnsavedChangesDialog.Cancel:
                    event.ignore()
                    return
        # saveGeometry() preserves the normal (un-maximized) size/position even when maximized.
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/maximized", self.isMaximized())
        super().closeEvent(event)
