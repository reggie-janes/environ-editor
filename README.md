# EnvEdit

A cross-platform desktop application for viewing and editing environment variables and PATH entries. Built with PySide6 and Qt Quick 2 (QML / Material style).

## Features

- **4 tabs**: User Variables, User PATH, System Variables, System PATH
- Inline editing with staged changes — nothing is written until you click **Apply Changes**
- Diff preview before any write is committed
- Modified rows highlighted; deleted rows tinted red
- PATH entries show live status icons: ✅ exists · ⚠ missing · 🔗 symlink
- Duplicate PATH entries highlighted in orange with a one-click **Remove Duplicates** action
- Live filter bar on every tab
- Unsaved-changes guard on window close
- Light/dark Material theme toggle (follows OS default, persisted in settings)
- Window geometry and maximized state persisted between sessions

## Requirements

| Dependency | Version |
|-----------|---------|
| Python | ≥ 3.14 |
| PySide6 | ≥ 6.7.0 |
| uv | any recent |

Linux also requires Qt native libs — see [Devcontainer](#devcontainer) or install manually:

```sh
sudo apt-get install libgl1 libegl1 libglib2.0-0 libdbus-1-3 libfontconfig1 \
  libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
  libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0
```

## Running from source

```sh
uv sync
uv run python main.py
```

Headless (no display, for testing):

```sh
QPA_PLATFORM=offscreen uv run python main.py
```

## Building a portable executable

Requires the optional `build` dependencies:

```sh
uv sync --extra build
```

Then run the script for your platform from the repo root:

| Platform | Command |
|----------|---------|
| Linux | `bash build/build_linux.sh` |
| Windows | `build\build_windows.bat` |
| macOS | `bash build/build_macos.sh` |

Output is a single self-contained file (`EnvEdit` / `EnvEdit.exe`). No installer required.

> Cross-compilation is not supported by Nuitka. Build Windows binaries on a Windows host or CI runner.

## Platform behaviour

### Linux / macOS

- **User variables** are read from the process environment and parsed from `~/.profile`, `~/.bashrc`, `~/.zshrc`.
- **Writes** go to `~/.config/envedit/env.sh`, automatically sourced from `~/.profile`. A new login session or `source ~/.profile` is needed to pick up changes in existing shells.
- **System writes** invoke `pkexec` (or `sudo` as fallback) to write `/etc/environment`.

### Windows

- **User variables** are read from and written to `HKCU\Environment` via `winreg`.
- **System variables** use `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment`; a UAC elevation prompt is shown when not already elevated.
- `WM_SETTINGCHANGE` is broadcast after every write so other processes pick up the change without a reboot.

## Devcontainer

The repo ships a ready-to-use devcontainer (VS Code / GitHub Codespaces).

- Base image: `mcr.microsoft.com/devcontainers/python:3.14`
- Package manager: [uv](https://github.com/astral-sh/uv) (installed as a devcontainer feature)
- Qt native libs are installed in the Dockerfile
- `uv sync` runs automatically on first container create (`post-create.sh`)
- `.venv` and `~/.claude` are stored in named Docker volumes so they survive container rebuilds

To rebuild the container after Dockerfile changes: **Rebuild Container** from the VS Code command palette.

## Project structure

```
assets/                          fonts (Roboto) and app icon
envedit/
├── core/
│   ├── env_backend.py           Abstract EnvBackend interface + get_backend() factory
│   ├── platform_unix.py         Linux / macOS implementation
│   ├── platform_windows.py      Windows implementation (winreg + UAC)
│   └── privilege.py             Elevation detection and re-launch helpers
├── models/
│   ├── env_var_model.py         QAbstractListModel for environment variables
│   └── path_model.py            QAbstractListModel for PATH entries
├── controllers/
│   └── app_controller.py        QObject owning all models; theme, settings, backend calls
└── qml/
    ├── main.qml                 ApplicationWindow, tab bar, theme, close guard
    └── components/
        ├── EnvTable.qml         Variable table (inline editing, pending highlights)
        ├── PathTable.qml        PATH table (status icons, move up/down, duplicates)
        ├── TabToolbar.qml       Add / Reload / Apply toolbar shared by all tabs
        ├── AddVarDialog.qml     Add variable dialog with live expansion preview
        ├── AddPathDialog.qml    Add PATH entry dialog with folder browser
        ├── ConfirmDialog.qml    Generic confirmation dialog
        └── DiffDialog.qml      Pending-changes diff before Apply
main.py                          Entry point (QGuiApplication + QQmlApplicationEngine)
build/                           Nuitka build scripts
```
