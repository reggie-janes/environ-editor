from __future__ import annotations

import json
import os
import re
import shlex
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
            if val.startswith('"') and val.endswith('"'):
                # Reverse the pair of replacements in _format_env_sh. Order
                # matters: unescape \" first so a literal trailing backslash
                # (written as \\) isn't paired up with the following quote
                # delimiter and consumed early.
                val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            elif val.startswith("'") and val.endswith("'"):
                # Single-quoted shell strings have no escape processing.
                val = val[1:-1]
            result[name] = val
    return result


def _read_envedit_vars() -> dict[str, str]:
    """Read variables from the EnvEdit-managed file.

    We do not parse arbitrary user shell-init scripts (`~/.profile`,
    `~/.bashrc`, etc.) because they contain conditionals, comments,
    multi-assign exports, and quoting forms that a regex parser cannot
    represent without misinterpretation. `_ENVEDIT_SH` is in a fixed
    `export NAME="VALUE"` format that we own end-to-end.
    """
    if not _ENVEDIT_SH.is_file():
        return {}
    try:
        return _parse_shell_assigns(_ENVEDIT_SH.read_text(errors="replace"))
    except OSError:
        return {}


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
        # os.environ wins (it's the live session state); the EnvEdit-managed
        # file fills in keys that haven't been re-sourced yet (e.g. just after
        # apply, before the user starts a new login shell).
        raw = _read_envedit_vars()
        raw.update(os.environ)
        return {k: v for k, v in raw.items() if k not in _PATH_KEYS}

    def get_system_vars(self) -> dict[str, str]:
        raw = _read_system_env_file()
        return {k: v for k, v in raw.items() if k not in _PATH_KEYS}

    def get_user_path(self) -> list[str]:
        # Return only what EnvEdit's managed file contributes — never the
        # merged session PATH. Reading the merged PATH would (a) clone the
        # entire system PATH on first apply, and (b) silently revert the
        # user's edits on the post-apply reload (since os.environ won't
        # change until the next login).
        envedit_vars = _read_envedit_vars()
        path_str = envedit_vars.get("PATH", "")
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

    def apply_system_vars(self, changes: dict[str, str | None], on_complete=None) -> bool:
        # Write to /etc/profile.d/envedit.sh rather than /etc/environment.
        # /etc/environment is co-managed (cloud-init, distro packages, PAM
        # comments) and parsing/rewriting it loses foreign content. The
        # profile.d file is something we own end-to-end and can safely
        # rewrite using the same escape-aware writer used for user vars.
        existing: dict[str, str] = {}
        if _SYSTEM_PROFILE_D.is_file():
            existing = _parse_shell_assigns(_SYSTEM_PROFILE_D.read_text(errors="replace"))
        for key, val in changes.items():
            if val is None:
                existing.pop(key, None)
            else:
                existing[key] = val
        content = _format_env_sh(existing)
        _write_as_root(_SYSTEM_PROFILE_D, content)
        return True

    def apply_user_path(self, entries: list[str]) -> None:
        self.apply_user_vars({"PATH": os.pathsep.join(entries)})

    def apply_system_path(self, entries: list[str], on_complete=None) -> bool:
        return self.apply_system_vars({"PATH": os.pathsep.join(entries)})

    def expand_value(self, value: str) -> str:
        return os.path.expandvars(value)


def _format_env_sh(vars_: dict[str, str]) -> str:
    lines = ["# Managed by EnvEdit — do not edit manually\n"]
    for k, v in sorted(vars_.items()):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'export {k}="{escaped}"\n')
    return "".join(lines)


def _write_env_sh(path: Path, vars_: dict[str, str]) -> None:
    # Write to a sibling temp file then os.replace() — a single rename(2)
    # syscall is atomic on POSIX, so a kill/OOM mid-write can't leave the
    # active env.sh truncated. Same-directory temp guarantees same filesystem.
    content = _format_env_sh(vars_)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def _login_profile() -> Path:
    # Bash reads ~/.bash_profile (or ~/.bash_login) instead of ~/.profile when
    # either exists, so we must write into the file the user's login shell will
    # actually source. Many distros ship a default ~/.bash_profile.
    home = Path.home()
    for name in (".bash_profile", ".bash_login", ".profile"):
        p = home / name
        if p.exists():
            return p
    return home / ".profile"


def _ensure_sourced_in_profile() -> None:
    profile = _login_profile()
    guard = f'[ -f "{_ENVEDIT_SH}" ] && . "{_ENVEDIT_SH}"'
    source_line = f'\n{guard}\n'
    if not profile.is_file():
        profile.write_text(source_line)
        return
    content = profile.read_text(errors="replace")
    # Match on the full functional guard, not just the path — a commented-out
    # source line should not suppress re-insertion.
    if guard not in content:
        with profile.open("a") as f:
            f.write(source_line)


def _write_as_root(path: Path, content: str) -> None:
    import tempfile, shutil
    with tempfile.NamedTemporaryFile("w", suffix=".tmp", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        if sys.platform == "darwin":
            # pkexec doesn't exist on macOS; sudo without a controlling terminal
            # fails in a GUI app. osascript with "administrator privileges"
            # shows the native macOS password sheet.
            shell_cmd = shlex.join(["install", "-m", "644", tmp_path, str(path)])
            script = (
                f"do shell script {json.dumps(shell_cmd)} "
                f"with administrator privileges"
            )
            subprocess.run(["osascript", "-e", script], check=True)
        else:
            tool = "pkexec" if shutil.which("pkexec") else "sudo"
            subprocess.run(
                [tool, "install", "-m", "644", tmp_path, str(path)],
                check=True,
            )
    finally:
        os.unlink(tmp_path)
