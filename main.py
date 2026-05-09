import sys
from pathlib import Path

ASSETS  = Path(__file__).parent / "assets"
QML_DIR = Path(__file__).parent / "envedit" / "qml"


def main() -> None:
    from PySide6.QtGui import QGuiApplication, QIcon, QFontDatabase, QFont
    from PySide6.QtQml import QQmlApplicationEngine

    app = QGuiApplication(sys.argv)
    app.setApplicationName("EnvEdit")
    app.setOrganizationName("EnvEdit")

    _load_fonts(app)

    icon_path = ASSETS / "environ-editor.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from envedit.controllers.app_controller import AppController
    controller = AppController()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appController", controller)
    engine.addImportPath(str(QML_DIR))          # lets main.qml find components/
    engine.load(str(QML_DIR / "main.qml"))

    if not engine.rootObjects():
        sys.exit(1)

    sys.exit(app.exec())


def _load_fonts(app) -> None:
    from PySide6.QtGui import QFontDatabase, QFont
    for name in ("Roboto-VariableFont_wdth,wght.ttf",
                 "Roboto-Italic-VariableFont_wdth,wght.ttf",
                 "RobotoMono-VariableFont_wght.ttf"):
        path = ASSETS / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    if "Roboto" in QFontDatabase.families():
        app.setFont(QFont("Roboto", 10))


if __name__ == "__main__":
    main()
