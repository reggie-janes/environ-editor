# EnvEdit — Claude Code Guide

## Running the app

```sh
uv run python main.py                            # normal (needs a display)
QPA_PLATFORM=offscreen uv run python main.py     # headless smoke test
```

`uv sync` installs all runtime dependencies. The `build` extra (`uv sync --extra build`) adds Nuitka for packaging.

## Architecture

The codebase has three layers:

**Core (`envedit/core/`)** — pure Python, no Qt UI imports.

| File | Role |
|------|------|
| `env_backend.py` | `EnvBackend` ABC + `get_backend()` factory |
| `platform_unix.py` | Linux/macOS: reads `os.environ` + shell profiles; writes to `~/.config/envedit/env.sh` |
| `platform_windows.py` | Windows: `winreg` reads/writes; all `winreg`/`ctypes` imports are inside methods so the file imports cleanly on Linux |
| `privilege.py` | `is_elevated()` + `request_elevation_and_apply()` — re-launches via `pkexec`/`runas`/`osascript` |

**Python models + controller (`envedit/models/`, `envedit/controllers/`)** — QObject/QAbstractListModel bridge between the core and QML.

| File | Role |
|------|------|
| `models/env_var_model.py` | `EnvVarModel(QAbstractListModel)`: roles Name/Value/Expanded/Pending/Deleted; staged edits in `_pending` dict; `pendingCount` Property |
| `models/path_model.py` | `PathModel(QAbstractListModel)`: roles Path/Expanded/Status/Pending/Duplicate; `_dirty` flag; moveUp/moveDown/removeDuplicates slots |
| `controllers/app_controller.py` | `AppController(QObject)`: owns all 4 models; `theme`, `isElevated`, `platformName` properties; `toggleTheme`, `reloadTab`, `applyTab`, `getDiffText`, `expandValue`, window-geometry slots |

**QML UI (`envedit/qml/`)** — Qt Quick 2 with Material style; no Python logic.

| File | Role |
|------|------|
| `main.qml` | `ApplicationWindow`: Material theming, TabBar, StackLayout, theme toggle, close guard |
| `components/EnvTable.qml` | Variable table: inline `TextInput` editing, pending/deleted row highlights, filter bar |
| `components/PathTable.qml` | PATH table: status icons, move-up/down buttons, duplicate highlight, filter bar |
| `components/TabToolbar.qml` | Add / Reload / Apply toolbar; Apply enabled only when `pendingCount > 0` |
| `components/AddVarDialog.qml` | Add-variable dialog with live expanded preview |
| `components/AddPathDialog.qml` | Add-PATH dialog with folder browser |
| `components/ConfirmDialog.qml` | Generic confirm/cancel dialog |
| `components/DiffDialog.qml` | Pending-changes diff before Apply |
| `components/Theme.qml` | Singleton color palette — 7 semantic colors with dark/light variants; all QML components read from this instead of hardcoding colors |

`main.py` wires everything together:
```python
app = QGuiApplication(sys.argv)
controller = AppController()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appController", controller)
engine.addImportPath(str(QML_DIR))      # enables  import "components"  in QML
engine.load(str(QML_DIR / "main.qml"))
```

## Key design decisions

- **Staged writes**: edits are held in model-level pending state (`_pending` dict in `EnvVarModel`, `_dirty` flag in `PathModel`) and only committed when the user clicks "Apply Changes". `pendingCount` Property drives the Apply button's enabled state via QML binding.
- **Material theming**: `ApplicationWindow.Material.theme` is bound to `appController.theme`; a single property-change signal re-renders the entire UI with no palette manipulation.
- **Null guards in QML**: all bindings that read `appController` use `appController && appController.prop` guards because QML evaluates bindings before the context property resolves.
- **Platform isolation**: `platform_windows.py` imports `winreg`/`ctypes` only inside method bodies, never at module level. `get_backend()` in `env_backend.py` selects the right class at runtime.
- **Case-insensitive PATH lookup on Windows**: the registry stores the key as "Path", not "PATH". `_iget()` in `platform_windows.py` does a case-insensitive dict lookup.
- **User PATH writes on Unix** go through `apply_user_vars({"PATH": ...})` which lands in `~/.config/envedit/env.sh`. A source line is automatically appended to `~/.profile` on first write.

## Adding a new platform

1. Create `envedit/core/platform_<name>.py` implementing all methods of `EnvBackend`.
2. Add a branch in `get_backend()` in `env_backend.py`.
3. No model, controller, or QML changes required.

## Tests

```sh
uv run pytest          # all tests
uv run pytest tests/test_env_backend.py   # one file
```

Tests live in `tests/`. `conftest.py` sets `QT_QPA_PLATFORM=offscreen` so Qt can initialise without a display. The suite covers the core backend, models, controller, and privilege helpers.

## Devcontainer

- Package manager is **uv**. Always use `uv run` or `uv sync`, not `pip`.
- Qt native libs (`libgl1`, `libegl1`, xcb libs, etc.) are installed via the Dockerfile. If you add a dependency that needs a new system lib, add it there and rebuild the container.
- The `.venv` directory lives in a named Docker volume; it survives `Rebuild Container` as long as the volume is not deleted.
- For UI-less testing set `QPA_PLATFORM=offscreen`.
