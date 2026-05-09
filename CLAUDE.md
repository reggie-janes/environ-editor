# EnvEdit — Claude Code Guide

## Running the app

```sh
uv run python main.py                            # normal (needs a display)
QPA_PLATFORM=offscreen uv run python main.py     # headless smoke test
```

`uv sync` installs all runtime dependencies. The `build` extra (`uv sync --extra build`) adds Nuitka for packaging.

## Architecture

The codebase has two independent layers:

**Core (`envedit/core/`)** — pure Python, no Qt imports.

| File | Role |
|------|------|
| `env_backend.py` | `EnvBackend` ABC + `get_backend()` factory |
| `platform_unix.py` | Linux/macOS: reads `os.environ` + shell profiles; writes to `~/.config/envedit/env.sh` |
| `platform_windows.py` | Windows: `winreg` reads/writes; all `winreg`/`ctypes` imports are inside methods so the file imports cleanly on Linux |
| `privilege.py` | `is_elevated()` + `request_elevation_and_apply()` — re-launches via `pkexec`/`runas`/`osascript` |

**UI (`envedit/ui/`)** — PySide6 only; no direct backend calls except from `MainWindow`.

| File | Role |
|------|------|
| `main_window.py` | `MainWindow(QMainWindow)`: 4-tab layout, toolbars, status bar, unsaved-changes guard |
| `env_table.py` | `EnvTableWidget`: variable table with inline editing and pending-change tracking |
| `path_table.py` | `PathTableWidget`: PATH table with status icons, drag-drop reorder, duplicate detection |
| `dialogs.py` | `AddVariableDialog`, `AddPathEntryDialog`, `ConfirmDeleteDialog`, `UnsavedChangesDialog`, `ElevationDialog`, `DiffDialog` |
| `theme.py` | `ThemeManager`: light/dark `QPalette` definitions, OS theme detection, `QSettings` persistence |

## Key design decisions

- **Staged writes**: edits are held in `_pending` dicts inside the table widgets and only committed when the user clicks "Apply Changes". `get_pending_changes()` / `clear_pending()` are the API between `MainWindow` and the table widgets.
- **Platform isolation**: `platform_windows.py` imports `winreg`/`ctypes` only inside method bodies, never at module level. `get_backend()` in `env_backend.py` selects the right class at runtime.
- **No pywin32 in pyproject.toml**: it is Windows-only and must be installed separately on a Windows host. It is not listed as a project dependency.
- **User PATH writes on Unix** go through `apply_user_vars({"PATH": ...})` which lands in `~/.config/envedit/env.sh`. A source line is automatically appended to `~/.profile` on first write.

## Adding a new platform

1. Create `envedit/core/platform_<name>.py` implementing all methods of `EnvBackend`.
2. Add a branch in `get_backend()` in `env_backend.py`.
3. No UI changes required.

## Devcontainer

- Package manager is **uv**. Always use `uv run` or `uv sync`, not `pip`.
- Qt native libs (`libgl1`, `libegl1`, xcb libs, etc.) are installed via the Dockerfile. If you add a dependency that needs a new system lib, add it there and rebuild the container.
- The `.venv` directory lives in a named Docker volume; it survives `Rebuild Container` as long as the volume is not deleted.
- For UI-less testing set `QPA_PLATFORM=offscreen`.
