import sys
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"


def main() -> None:
    from PySide6.QtGui import QFont, QFontDatabase, QIcon
    from PySide6.QtWidgets import QApplication
    from envedit.ui.main_window import MainWindow
    from envedit.ui.theme import ThemeManager

    app = QApplication(sys.argv)
    app.setApplicationName("EnvEdit")
    app.setOrganizationName("EnvEdit")

    _load_fonts(app)

    icon_path = ASSETS / "environ-editor.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    ThemeManager.apply_startup_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def _load_fonts(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase
    for name in ("Roboto-VariableFont_wdth,wght.ttf",
                 "Roboto-Italic-VariableFont_wdth,wght.ttf"):
        path = ASSETS / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.families()
    if "Roboto" in families:
        app.setFont(QFont("Roboto", 10))


if __name__ == "__main__":
    main()
