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
    try:
        if "system_vars" in payload:
            backend.apply_system_vars(payload["system_vars"])
        if "system_path" in payload:
            backend.apply_system_path(payload["system_path"])
    except Exception as exc:
        print(f"envedit elevated apply failed: {exc}", file=sys.stderr)
        _allow_parent_to_foreground()
        return 2
    _allow_parent_to_foreground()
    return 0


def _allow_parent_to_foreground() -> None:
    """Lift Windows' SetForegroundWindow restriction for the parent.

    After UAC consent the foreground rights belong to this elevated child;
    when we exit, Windows by default does *not* return them to the parent
    EnvEdit, so the parent's requestActivate() is silently denied and
    whatever other app was previously focused stays on top. Calling
    AllowSetForegroundWindow(ASFW_ANY) before exit lets the parent
    re-foreground itself on its next try.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ASFW_ANY = 0xFFFFFFFF
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass


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

    from PySide6.QtCore import QUrl, QLockFile, QStandardPaths, QDir
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication, QMessageBox

    # QApplication (not QGuiApplication) so QMessageBox is available for the
    # single-instance prompt below. The rest of the UI is QML so the extra
    # Widgets dependency is paid only for this one dialog.
    app = QApplication(sys.argv)
    app.setApplicationName("EnvEdit")
    app.setOrganizationName("EnvEdit")

    # Single-instance enforcement. Two EnvEdits writing concurrently would
    # otherwise each read env.sh / the registry, apply their own pending
    # edits, and the later writer would silently clobber the earlier one's
    # changes. The lock lives under the per-user temp location so it's
    # cleaned up automatically on logout.
    runtime_dir = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
    QDir(runtime_dir).mkpath(".")
    lock_path = os.path.join(runtime_dir, "envedit.lock")
    lock_file = QLockFile(lock_path)
    lock_file.setStaleLockTime(0)
    if not lock_file.tryLock(100):
        QMessageBox.information(
            None,
            "EnvEdit already running",
            "Another instance of EnvEdit is already open. Switch to it and "
            "make your changes there.",
        )
        sys.exit(0)
    # Keep `lock_file` referenced for the process lifetime; QLockFile releases
    # the lock in its destructor.
    app._envedit_lock = lock_file  # type: ignore[attr-defined]

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
