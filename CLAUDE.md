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
| `platform_unix.py` | Linux/macOS: reads `os.environ` + `~/.config/envedit/env.sh`; user writes go to that file, system writes go to `/etc/profile.d/envedit.sh` via `pkexec`/`sudo` |
| `platform_windows.py` | Windows: `winreg` reads/writes; all `winreg`/`ctypes` imports are inside methods so the file imports cleanly on Linux |
| `privilege.py` | `is_elevated()`, `is_elevated_via_wrapper()` + `request_elevation_and_apply()` — re-launches via `pkexec`/`runas`/`osascript` |

**Python models + controller (`envedit/models/`, `envedit/controllers/`)** — QObject/QAbstractListModel bridge between the core and QML.

| File | Role |
|------|------|
| `models/env_var_model.py` | `EnvVarModel(QAbstractListModel)`: roles Name/Value/Expanded/Pending/Deleted; staged edits in `_pending` dict; `pendingCount` Property |
| `models/path_model.py` | `PathModel(QAbstractListModel)`: roles Path/Expanded/Status/Pending/Duplicate/Deleted; `_dirty` flag; moveUp/moveDown/moveEntry/removeDuplicates slots; `hasDuplicates` and `filterActive` properties |
| `controllers/app_controller.py` | `AppController(QObject)`: owns all 4 models; `theme`, `isElevated`, `isBusy`, `platformName` properties; `toggleTheme`, `reloadAll`, `reloadTab`, `applyTab`, `getDiffText`, `expandValue`, `openFolder`, window-geometry slots; `errorOccurred` signal (also forwards each model's `errorOccurred` to the UI snackbar) |

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

`main.py` wires everything together. On startup it first checks for `--apply-system-base64 <b64>` (the elevated child branch on Windows — the payload is base64-encoded JSON embedded in argv, not a temp-file path, to close the TOCTOU window), then takes a `QLockFile` single-instance lock, then launches the normal UI:
```python
app = QApplication(sys.argv)               # QApplication, not QGuiApplication, for QMessageBox
_load_fonts(app)                           # Roboto variable fonts from assets/
# QLockFile under QStandardPaths.TempLocation; tryLock(100) → second instance refuses to start
controller = AppController()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appController", controller)
engine.addImportPath(str(QML_DIR))         # enables  import "components"  in QML
engine.load(str(QML_DIR / "main.qml"))
```

## Key design decisions

- **Staged writes**: edits are held in model-level pending state (`_pending` dict in `EnvVarModel`, `_dirty` flag in `PathModel`) and only committed when the user clicks "Apply Changes". `pendingCount` Property drives the Apply button's enabled state via QML binding.
- **Async elevated apply**: system-tab Apply calls `apply_system_vars`/`apply_system_path` which may return `False` (dispatched to an elevated child via `pkexec`/`runas`/`osascript`). The controller sets `isBusy = True` until `_elevatedApplyDone` fires from the background thread, then reloads that tab. On Windows the child receives a base64-encoded JSON payload via `--apply-system-base64`; on Unix `_write_as_root` runs on a worker thread when `on_complete` is provided so the password prompt doesn't freeze the GUI.
- **Atomic user-var writes on Unix**: `_write_env_sh` writes to a `.tmp` sibling then calls `os.replace()`, which is a single `rename(2)` syscall — a kill mid-write cannot leave `env.sh` truncated.
- **POSIX single-quoting in env.sh**: values are written as `export NAME='value'` with the standard `'\''` escape for embedded single quotes. Single-quoted POSIX strings have no escape processing, so `$`, backticks, and `$(…)` round-trip literally instead of being interpreted by the shell on source. `_decode_shell_value` in `platform_unix.py` parses concatenated quoted/unquoted runs (so older double-quoted env.sh files and the PATH inheritance pattern below both round-trip).
- **Inherited PATH preservation**: when `~/.config/envedit/env.sh` has no `PATH` key yet, `UnixBackend.get_user_path` surfaces a `$PATH` sentinel row so the user's first edit *extends* the inherited PATH rather than replacing it. The writer special-cases PATH: `$PATH` segments stay outside the single quotes so the login shell expands them.
- **Passthrough of unparseable lines**: `_parse_shell_assigns_with_passthrough` returns `(assigns, extras)`. The writer re-emits the extras under a `# --- preserved …` marker section, so comments / conditionals / foreign exports the user added by hand survive the next Apply.
- **rc-file seeding**: `_ensure_sourced_in_profile` adds the source line to `~/.bashrc` and `~/.zshrc` in addition to the login profile, because most Linux terminals start interactive *non-login* shells and would otherwise never source env.sh.
- **Single-instance enforcement**: `QLockFile` at startup refuses to launch a second EnvEdit; in addition, `fcntl.flock` wraps the user env.sh read-modify-write in `apply_user_vars` as a belt-and-braces against concurrent writers (e.g. a CLI script invoking the backend directly).
- **Runtime-var filter on Unix**: `get_user_vars` returns the managed env.sh contents overlaid with the live values from `os.environ` for *managed* keys only. Other `os.environ` entries are surfaced only if they pass `_is_runtime_var` (filters DISPLAY, PWD, SSH_*, XDG_*, DBUS_*, TERM, LS_COLORS, …) so editing one of those doesn't accidentally write a permanent override to env.sh.
- **Variable name validation**: `EnvVarModel` rejects names that don't match `^[A-Za-z_][A-Za-z0-9_]{0,255}$` (the same regex `_parse_shell_assigns` uses). `PathModel.addEntry` rejects entries containing `os.pathsep`, newline, or NUL. Both surface a snackbar via `errorOccurred`.
- **Material theming**: `ApplicationWindow.Material.theme` is bound to `appController.theme`; a single property-change signal re-renders the entire UI with no palette manipulation.
- **Null guards in QML**: all bindings that read `appController` use `appController && appController.prop` guards because QML evaluates bindings before the context property resolves.
- **Platform isolation**: `platform_windows.py` imports `winreg`/`ctypes` only inside method bodies, never at module level. `get_backend()` in `env_backend.py` selects the right class at runtime.
- **Case-insensitive PATH lookup on Windows**: the registry stores the key as "Path", not "PATH". `_iget()` in `platform_windows.py` does a case-insensitive dict lookup.
- **Windows REG type preservation**: `_reg_type_for()` reads the existing value's type (REG_SZ vs REG_EXPAND_SZ) and re-uses it on write so EnvEdit doesn't silently upgrade values written by other tools. For new keys, it picks REG_EXPAND_SZ only when the value contains a likely `%…%` pair.
- **Windows elevation wait**: `privilege.request_elevation_and_apply` polls `WaitForSingleObject` with a 1 s interval and no upper bound, so a slow UAC consent (password lookup, fingerprint scan) won't trigger a spurious "timed out" reload while the elevated child is still mid-write.
- **User PATH writes on Unix** go through `apply_user_vars({"PATH": ...})` which lands in `~/.config/envedit/env.sh`. The file is auto-sourced from the user's login profile (`~/.bash_profile`, `~/.bash_login`, or `~/.profile`) on first write, plus `~/.bashrc` / `~/.zshrc` if present.
- **System writes on Unix** go to `/etc/profile.d/envedit.sh` (not `/etc/environment`), which EnvEdit owns end-to-end and can safely rewrite without corrupting foreign content managed by distro packages or cloud-init.

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

## CI (.github/workflows/build.yml)

The workflow has three jobs triggered differently:

| Job | Trigger | Platforms | What it does |
|-----|---------|-----------|--------------|
| `test` | push to `main`, pull requests | Linux only | `uv sync --extra test` + `pytest` |
| `build` | tags (`v*`), `workflow_dispatch` | Linux, Windows, macOS | `pytest` + Nuitka build + upload artifacts |
| `release` | tags (`v*`) (needs `build`) | ubuntu-latest | Creates a draft GitHub Release with all artifacts |

Qt system libraries needed by PySide6 are installed via the local composite action `.github/actions/install-qt-libs/action.yml` (Linux only; no-op on other platforms). Both `test` and `build` use it — add new system lib requirements there.

## Packaging (Nuitka)

Build scripts live in `build/`. CI invokes `build_windows.bat`, `build_linux.sh`, and `build_macos.sh` from `.github/workflows/build.yml`. The `build` extra in `pyproject.toml` is `nuitka[onefile]` (not bare `nuitka`) — the `[onefile]` is what pulls in `zstandard`. Without it Nuitka emits an uncompressed onefile and the .exe is ~5× larger than it should be.

**Qt module / DLL exclusion patterns differ by platform:**

| Platform | Library naming | Pattern that catches it |
|----------|----------------|-------------------------|
| Windows  | `Qt6WebEngineCore.dll` | `*Qt6WebEngine*` |
| Linux    | `libQt6WebEngineCore.so.6.7.2` | `*Qt6WebEngine*` |
| macOS    | `QtWebEngineCore.framework/Versions/A/QtWebEngineCore` | `*WebEngine*` *(no Qt6 prefix in framework binary names)* |

The build scripts include both `*Qt6Foo*` and `*Foo*`/`QtFoo*` variants so the same exclusion intent applies everywhere. If you add a new exclude, add both forms.

Excluding a framework's binary on macOS cascades to skipping the whole framework directory (Resources/, helper `.app` bundles, locale `.pak` files). No separate `--noinclude-data-files` for framework subtrees is needed.

Beyond top-level Qt DLLs, the per-module **QML plugins** under `qml/<Module>/<plugin>.dll` have completely different names (`qtwebenginequickplugin.dll`, not `Qt6WebEngine*`) and need their own exclusion patterns.

Two things that *cannot* be excluded without breaking the launch:
- `Qt6Network.dll` — Qt initializes it during QML engine setup even when the app does no networking.
- `Qt6OpenGL.dll` / `QtOpenGL.pyd` — Qt's RHI soft-loads it on Windows even when D3D11 is the active scene-graph backend.

Both were tried; both broke the build silently (CI succeeded, .exe failed to launch). See git history for `Revert "Exclude Qt6Network"` and `Revert "Exclude Qt6OpenGL"`.
