from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from envedit.core.env_backend import EnvBackend

_ENVEDIT_SH = Path.home() / ".config" / "envedit" / "env.sh"
_SYSTEM_ENV = Path("/etc/environment")
_SYSTEM_PROFILE_D = Path("/etc/profile.d/envedit.sh")

# Variables we never expose in the user-vars table (shown in PATH tab instead)
_PATH_KEYS = {"PATH"}


def _parse_shell_assigns(text: str) -> dict[str, str]:
    """Extract VAR=value / export VAR=value lines from shell-script text."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if m:
            name, val = m.group(1), m.group(2)
            # Strip surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            result[name] = val
    return result


def _read_user_shell_vars() -> dict[str, str]:
    candidates = [
        Path.home() / ".profile",
        Path.home() / ".bash_profile",
        Path.home() / ".bashrc",
        Path.home() / ".zshrc",
        _ENVEDIT_SH,
    ]
    merged: dict[str, str] = {}
    for p in candidates:
        if p.is_file():
            try:
                merged.update(_parse_shell_assigns(p.read_text(errors="replace")))
            except OSError:
                pass
    return merged


def _read_system_env_file() -> dict[str, str]:
    result: dict[str, str] = {}
    if _SYSTEM_ENV.is_file():
        try:
            result.update(_parse_shell_assigns(_SYSTEM_ENV.read_text(errors="replace")))
        except OSError:
            pass
    if _SYSTEM_PROFILE_D.is_file():
        try:
            result.update(_parse_shell_assigns(_SYSTEM_PROFILE_D.read_text(errors="replace")))
        except OSError:
            pass
    return result


class UnixBackend(EnvBackend):
    def get_user_vars(self) -> dict[str, str]:
        raw = dict(os.environ)
        raw.update(_read_user_shell_vars())
        return {k: v for k, v in raw.items() if k not in _PATH_KEYS}

    def get_system_vars(self) -> dict[str, str]:
        raw = _read_system_env_file()
        return {k: v for k, v in raw.items() if k not in _PATH_KEYS}

    def get_user_path(self) -> list[str]:
        path_str = os.environ.get("PATH", "")
        return [p for p in path_str.split(os.pathsep) if p]

    def get_system_path(self) -> list[str]:
        sys_vars = _read_system_env_file()
        path_str = sys_vars.get("PATH", "")
        return [p for p in path_str.split(os.pathsep) if p]

    def apply_user_vars(self, changes: dict[str, str | None]) -> None:
        _ENVEDIT_SH.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, str] = {}
        if _ENVEDIT_SH.is_file():
            existing = _parse_shell_assigns(_ENVEDIT_SH.read_text(errors="replace"))
        for key, val in changes.items():
            if val is None:
                existing.pop(key, None)
            else:
                existing[key] = val
        _write_env_sh(_ENVEDIT_SH, existing)
        _ensure_sourced_in_profile()

    def apply_system_vars(self, changes: dict[str, str | None]) -> None:
        existing: dict[str, str] = {}
        if _SYSTEM_ENV.is_file():
            existing = _parse_shell_assigns(_SYSTEM_ENV.read_text(errors="replace"))
        for key, val in changes.items():
            if val is None:
                existing.pop(key, None)
            else:
                existing[key] = val
        content = "\n".join(f'{k}="{v}"' for k, v in sorted(existing.items())) + "\n"
        _write_as_root(_SYSTEM_ENV, content)

    def apply_user_path(self, entries: list[str]) -> None:
        self.apply_user_vars({"PATH": os.pathsep.join(entries)})

    def apply_system_path(self, entries: list[str]) -> None:
        self.apply_system_vars({"PATH": os.pathsep.join(entries)})

    def expand_value(self, value: str) -> str:
        return os.path.expandvars(value)


def _write_env_sh(path: Path, vars_: dict[str, str]) -> None:
    lines = ["# Managed by EnvEdit — do not edit manually\n"]
    for k, v in sorted(vars_.items()):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'export {k}="{escaped}"\n')
    path.write_text("".join(lines))


def _ensure_sourced_in_profile() -> None:
    profile = Path.home() / ".profile"
    source_line = f'\n[ -f "{_ENVEDIT_SH}" ] && . "{_ENVEDIT_SH}"\n'
    if not profile.is_file():
        profile.write_text(source_line)
        return
    content = profile.read_text(errors="replace")
    if str(_ENVEDIT_SH) not in content:
        with profile.open("a") as f:
            f.write(source_line)


def _write_as_root(path: Path, content: str) -> None:
    import tempfile, shutil
    with tempfile.NamedTemporaryFile("w", suffix=".tmp", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        tool = "pkexec" if shutil.which("pkexec") else "sudo"
        subprocess.run(
            [tool, "cp", tmp_path, str(path)],
            check=True,
        )
    finally:
        os.unlink(tmp_path)
