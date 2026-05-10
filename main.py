import json
import os
import sys
from pathlib import Path

ASSETS  = Path(__file__).parent / "assets"
QML_DIR = Path(__file__).parent / "envedit" / "qml"


def _apply_system_payload(payload: dict) -> int:
    from envedit.core.env_backend import get_backend
    backend = get_backend()
    if "system_vars" in payload:
        backend.apply_system_vars(payload["system_vars"])
    if "system_path" in payload:
        backend.apply_system_path(payload["system_path"])
    return 0


def _maybe_run_elevated_apply() -> bool:
    """If invoked with --apply-system-file <path>, perform the apply and exit.

    Returns True if the flag was handled (caller should exit), False otherwise.
    """
    if len(sys.argv) >= 3 and sys.argv[1] == "--apply-system-file":
        payload_path = sys.argv[2]
        try:
            with open(payload_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            print(f"envedit: failed to read payload: {exc}", file=sys.stderr)
            try:
                os.unlink(payload_path)
            except OSError:
                pass
            sys.exit(1)
        try:
            os.unlink(payload_path)
        except OSError:
            pass
        sys.exit(_apply_system_payload(payload))
    return False


def main() -> None:
    _maybe_run_elevated_apply()

    from PySide6.QtGui import QGuiApplication, QIcon
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
