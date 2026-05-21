from __future__ import annotations

import os
import platform
import sys

from PySide6.QtCore import QObject, QSettings, Property, QUrl, Signal, Slot, Qt

from envedit.core.env_backend import EnvBackend, get_backend
from envedit.core.privilege import is_elevated, is_elevated_via_wrapper
from envedit.models.env_var_model import EnvVarModel
from envedit.models.path_model import PathModel


class AppController(QObject):
    themeChanged = Signal()
    errorOccurred = Signal(str)
    infoOccurred = Signal(str)
    isBusyChanged = Signal()
    # Fires after a successful Apply so the QML window can re-foreground
    # itself. Windows in particular tends to leave another app on top after
    # any disruption to focus (UAC consent for elevated apply, modal dialog
    # close on non-elevated apply), so the window asks the OS to come back.
    requestActivateWindow = Signal()
    _elevatedApplyDone = Signal(int, bool)  # (tab index, timed_out); from background thread

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("EnvEdit", "EnvEdit")
        self._backend: EnvBackend = get_backend()
        self._is_busy = False

        expand = self._backend.expand_value
        self._user_var_model  = EnvVarModel(expand_fn=expand)
        self._system_var_model = EnvVarModel(expand_fn=expand)
        self._user_path_model  = PathModel(expand_fn=expand)
        self._system_path_model = PathModel(expand_fn=expand)

        # Forward model-level errors (e.g. rename collisions, invalid PATH
        # entries) to the UI's snackbar.
        for m in (self._user_var_model, self._system_var_model,
                  self._user_path_model, self._system_path_model):
            m.errorOccurred.connect(self.errorOccurred)

        for m in (self._user_var_model, self._system_var_model):
            m.infoOccurred.connect(self.infoOccurred)

        # QueuedConnection ensures the slot runs in the main thread even when
        # the signal is emitted from a threading.Thread (not a QThread).
        self._elevatedApplyDone.connect(self._onElevatedApplyDone, Qt.ConnectionType.QueuedConnection)
        self._load_all()

    # ------------------------------------------------------------------ models (read-only properties)

    @Property(QObject, constant=True)
    def userVarModel(self) -> EnvVarModel:
        return self._user_var_model

    @Property(QObject, constant=True)
    def systemVarModel(self) -> EnvVarModel:
        return self._system_var_model

    @Property(QObject, constant=True)
    def userPathModel(self) -> PathModel:
        return self._user_path_model

    @Property(QObject, constant=True)
    def systemPathModel(self) -> PathModel:
        return self._system_path_model

    # ------------------------------------------------------------------ info properties

    @Property(bool, constant=True)
    def isElevated(self) -> bool:
        return is_elevated()

    @Property(bool, constant=True)
    def userTabsReadOnly(self) -> bool:
        # When launched via sudo/pkexec, $HOME points to /root; user-tab
        # writes would corrupt root's account instead of the invoking user's.
        # The UI uses this to lock the user tabs and surface a banner.
        return is_elevated_via_wrapper()

    @Property(bool, notify=isBusyChanged)
    def isBusy(self) -> bool:
        return self._is_busy

    @Property(str, constant=True)
    def platformName(self) -> str:
        return platform.system()

    # ------------------------------------------------------------------ theme

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        saved = self._settings.value("theme/mode", "")
        if saved in ("light", "dark"):
            return saved
        return self._detect_os_theme()

    @Slot()
    def toggleTheme(self) -> None:
        new = "dark" if self.theme == "light" else "light"
        self._settings.setValue("theme/mode", new)
        self.themeChanged.emit()

    # ------------------------------------------------------------------ window geometry

    @Slot(result=bool)
    def isWindowMaximized(self) -> bool:
        return bool(self._settings.value("window/maximized", False, type=bool))

    @Slot(int, int, int, int)
    def saveWindowGeometry(self, x: int, y: int, w: int, h: int) -> None:
        self._settings.setValue("window/x", x)
        self._settings.setValue("window/y", y)
        self._settings.setValue("window/width", w)
        self._settings.setValue("window/height", h)

    @Slot(result="QVariantList")
    def loadWindowGeometry(self):
        return [
            self._settings.value("window/x", 100, type=int),
            self._settings.value("window/y", 100, type=int),
            self._settings.value("window/width", 1100, type=int),
            self._settings.value("window/height", 680, type=int),
        ]

    @Slot(bool)
    def saveWindowMaximized(self, maximized: bool) -> None:
        self._settings.setValue("window/maximized", maximized)

    # ------------------------------------------------------------------ data

    @Slot()
    def reloadAll(self) -> None:
        self._load_all()

    @Slot(int)
    def reloadTab(self, idx: int) -> None:
        self._reload(idx)

    @Slot(int, result="QVariantList")
    def getDiffOps(self, idx: int) -> list:
        """Structured diff for a tab; QML renders the badges and rows.

        The lists from the models are returned verbatim — every op carries
        an `op` field ("add" / "remove" / "edit" / "move"). Var ops have
        name/old_value/new_value; path ops have path/old_pos/new_pos (and
        old_path/new_path for edits).
        """
        if idx == 0:
            return self._user_var_model.getDiffOperations()
        if idx == 1:
            return self._user_path_model.getDiffOperations()
        if idx == 2:
            return self._system_var_model.getDiffOperations()
        if idx == 3:
            return self._system_path_model.getDiffOperations()
        return []

    @Slot(int)
    def applyTab(self, idx: int) -> None:
        try:
            if idx in (0, 1) and is_elevated_via_wrapper():
                self.errorOccurred.emit(
                    "User variables can't be edited when EnvEdit is running "
                    "with elevated privileges. Restart as your normal user."
                )
                return
            if idx == 0:
                self._backend.apply_user_vars(self._user_var_model.getPendingChanges())
                self._reload(0)
                self.requestActivateWindow.emit()
            elif idx == 1:
                self._backend.apply_user_path(self._user_path_model.getEntries())
                self._reload(1)
                self.requestActivateWindow.emit()
            elif idx == 2:
                applied = self._backend.apply_system_vars(
                    self._system_var_model.getPendingChanges(),
                    on_complete=lambda timed_out=False: self._elevatedApplyDone.emit(2, timed_out),
                )
                if applied is None:
                    pass  # UAC cancelled — pending state preserved, no error shown
                elif applied:
                    self._reload(2)
                    self.requestActivateWindow.emit()
                else:
                    self._is_busy = True
                    self.isBusyChanged.emit()
            elif idx == 3:
                applied = self._backend.apply_system_path(
                    self._system_path_model.getEntries(),
                    on_complete=lambda timed_out=False: self._elevatedApplyDone.emit(3, timed_out),
                )
                if applied is None:
                    pass  # UAC cancelled — pending state preserved, no error shown
                elif applied:
                    self._reload(3)
                    self.requestActivateWindow.emit()
                else:
                    self._is_busy = True
                    self.isBusyChanged.emit()
        except Exception as exc:
            self.errorOccurred.emit(str(exc))

    @Slot(str, result=str)
    def expandValue(self, value: str) -> str:
        return self._backend.expand_value(value)

    @Slot(QUrl, result=str)
    def urlToLocalFile(self, url: QUrl) -> str:
        return url.toLocalFile()

    @Slot(str)
    def openFolder(self, path: str) -> None:
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            self.errorOccurred.emit(str(exc))

    # ------------------------------------------------------------------ internals

    def _load_all(self) -> None:
        self._user_var_model.loadData(self._backend.get_user_vars())
        self._system_var_model.loadData(self._backend.get_system_vars())
        self._user_path_model.loadData(self._backend.get_user_path())
        self._system_path_model.loadData(self._backend.get_system_path())

    @Slot(int, bool)
    def _onElevatedApplyDone(self, idx: int, timed_out: bool) -> None:
        self._is_busy = False
        self.isBusyChanged.emit()
        if timed_out:
            # Reloading on timeout would show stale state and obscure the
            # message — surface the error only.
            self.errorOccurred.emit(
                "Elevated apply did not complete — see system logs."
            )
            return
        self._reload(idx)
        self.requestActivateWindow.emit()

    def _reload(self, idx: int) -> None:
        if idx == 0:
            self._user_var_model.loadData(self._backend.get_user_vars())
        elif idx == 1:
            self._user_path_model.loadData(self._backend.get_user_path())
        elif idx == 2:
            self._system_var_model.loadData(self._backend.get_system_vars())
        elif idx == 3:
            self._system_path_model.loadData(self._backend.get_system_path())

    @staticmethod
    def _detect_os_theme() -> str:
        try:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtCore import Qt
            scheme = QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "light"
