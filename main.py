import base64
import json
import os
import sys
from pathlib import Path

# Silence "qt.qpa.mime: Retrying to obtain clipboard" — fires whenever another
# app writes to the clipboard while we hold a TextInput listener. Harmless,
# unavoidable from app code. Must be set before any Qt import.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.mime.warning=false")

_ROOT   = Path(__file__).parent
ASSETS  = _ROOT / "assets"
QML_DIR = (_ROOT / "qml") if (_ROOT / "qml" / "main.qml").exists() else (_ROOT / "envedit" / "qml")


def _apply_system_payload(payload: dict) -> int:
    from envedit.core.env_backend import get_backend
    backend = get_backend()
    if "system_vars" in payload:
        backend.apply_system_vars(payload["system_vars"])
    if "system_path" in payload:
        backend.apply_system_path(payload["system_path"])
    return 0


def _maybe_run_elevated_apply() -> bool:
    """If invoked with --apply-system-base64 <b64>, decode the payload,
    apply it, and exit. Used by the Windows elevation flow — the parent
    process embeds the JSON payload in argv rather than handing the
    elevated child a path to a user-writable temp file (TOCTOU vector).

    Returns True if the flag was handled (caller should exit), False
    otherwise.
    """
    if len(sys.argv) >= 3 and sys.argv[1] == "--apply-system-base64":
        try:
            payload_bytes = base64.b64decode(sys.argv[2], validate=True)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:
            print(f"envedit: failed to decode payload: {exc}", file=sys.stderr)
            sys.exit(1)
        sys.exit(_apply_system_payload(payload))
    return False


def main() -> None:
    _maybe_run_elevated_apply()

    from PySide6.QtCore import QUrl
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
    engine.rootContext().setContextProperty(
        "assetsUrl", QUrl.fromLocalFile(str(ASSETS)).toString()
    )
    engine.addImportPath(str(QML_DIR))          # lets main.qml find components/
    engine.load(str(QML_DIR / "main.qml"))

    if not engine.rootObjects():
        sys.exit(1)

    sys.exit(app.exec())


def _load_fonts(app) -> None:
    from PySide6.QtGui import QFontDatabase, QFont
    for name in ("Roboto-VariableFont_wdth,wght.ttf",
                 "RobotoMono-VariableFont_wght.ttf"):
        path = ASSETS / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    if "Roboto" in QFontDatabase.families():
        app.setFont(QFont("Roboto", 10))


if __name__ == "__main__":
    main()
