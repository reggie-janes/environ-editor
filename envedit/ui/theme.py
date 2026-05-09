from __future__ import annotations

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


LIGHT = "light"
DARK = "dark"


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(233, 233, 233))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link, QColor(0, 100, 200))
    return p


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
    p.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link, QColor(100, 180, 255))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(128, 128, 128))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(128, 128, 128))
    return p


def _detect_os_theme() -> str:
    try:
        hints = QApplication.styleHints()
        from PySide6.QtCore import Qt
        scheme = hints.colorScheme()
        return DARK if scheme == Qt.ColorScheme.Dark else LIGHT
    except Exception:
        bg = QApplication.palette().color(QPalette.ColorRole.Window)
        return DARK if bg.lightness() < 128 else LIGHT


class ThemeManager:
    _settings_key = "theme/mode"

    @classmethod
    def apply_startup_theme(cls, app: QApplication) -> None:
        settings = QSettings("EnvEdit", "EnvEdit")
        saved = settings.value(cls._settings_key, "")
        theme = saved if saved in (LIGHT, DARK) else _detect_os_theme()
        cls._apply(app, theme)

    @classmethod
    def toggle(cls, app: QApplication) -> str:
        settings = QSettings("EnvEdit", "EnvEdit")
        current = settings.value(cls._settings_key, _detect_os_theme())
        new_theme = DARK if current == LIGHT else LIGHT
        cls._apply(app, new_theme)
        return new_theme

    @classmethod
    def current(cls) -> str:
        settings = QSettings("EnvEdit", "EnvEdit")
        return settings.value(cls._settings_key, _detect_os_theme())

    @staticmethod
    def _apply(app: QApplication, theme: str) -> None:
        # Fusion style fully respects QPalette on all platforms.
        # The native Windows style ignores custom palettes, so dark mode requires Fusion.
        # Light mode also uses Fusion for consistency.
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(_dark_palette() if theme == DARK else _light_palette())
        settings = QSettings("EnvEdit", "EnvEdit")
        settings.setValue(ThemeManager._settings_key, theme)
