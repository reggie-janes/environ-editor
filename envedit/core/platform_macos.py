"""macOS-specific backend.

GUI apps launched from Finder, Dock, or Spotlight inherit their environment
from `launchd`, not from `~/.profile`/`~/.zshrc`. The Unix backend's writes to
`~/.config/envedit/env.sh` only reach Terminal sessions; to affect GUI apps we
must use `launchctl setenv` plus a `LaunchAgent`/`LaunchDaemon` plist that
re-applies the values at next login/boot.

This backend extends `UnixBackend` so we keep `env.sh` writes intact (Terminal
users still expect shell-init semantics) and layer the macOS-specific work on
top.

Storage layout:

| Scope  | env.sh                                | plist                                                          | PATH-only            |
|--------|---------------------------------------|----------------------------------------------------------------|----------------------|
| User   | `~/.config/envedit/env.sh`            | `~/Library/LaunchAgents/com.envedit.user-env.plist`            | (in plist's PATH)    |
| System | (not written — macOS shells don't     | `/Library/LaunchDaemons/com.envedit.system-env.plist`          | `/etc/paths.d/envedit` |
|        | reliably source `/etc/profile.d/*`)   |                                                                |                      |

The plist stores variables in the standard `EnvironmentVariables` dict (so it
round-trips trivially via `plistlib`) and *also* invokes
`launchctl setenv NAME 'VALUE'; …` from a `RunAtLoad` `ProgramArguments`
script — only the latter actually affects the global launchd environment, but
the dict is what we read back as the canonical store.
"""
from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
from pathlib import Path

from envedit.core.platform_unix import (
    UnixBackend,
    _PATH_INHERIT_TOKEN,
    _PATH_KEYS,
    _is_runtime_var,
    _read_envedit_vars,
)
from envedit.core.privilege import is_elevated

_USER_AGENT_LABEL = "com.envedit.user-env"
_SYSTEM_DAEMON_LABEL = "com.envedit.system-env"

_USER_AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_USER_AGENT_LABEL}.plist"
_SYSTEM_DAEMON_PLIST = Path("/Library/LaunchDaemons") / f"{_SYSTEM_DAEMON_LABEL}.plist"
_SYSTEM_PATHS_D = Path("/etc/paths.d/envedit")


def _build_setenv_script(env_vars: dict[str, str]) -> str:
    """Build the `launchctl setenv …` shell command embedded in the plist's
    ProgramArguments. Each value is single-quoted with the standard `'\\''`
    escape so `$`, backticks, and `$(...)` round-trip literally — the same
    invariant `_shell_single_quote` enforces in env.sh."""
    if not env_vars:
        # An empty ProgramArguments script would make launchd treat the agent
        # as crashed and disable it. `true` is a no-op that exits 0.
        return "true"
    parts: list[str] = []
    for k in sorted(env_vars):
        v = env_vars[k]
        parts.append(f"launchctl setenv {k} {shlex.quote(v)}")
    return "; ".join(parts)


def _render_plist(label: str, env_vars: dict[str, str]) -> bytes:
    """Render a `RunAtLoad` LaunchAgent/LaunchDaemon plist as XML bytes.

    `EnvironmentVariables` is the canonical store we read back from.
    `ProgramArguments` is what actually applies the values to launchd at load
    time via `launchctl setenv`.
    """
    plist: dict = {
        "Label": label,
        "EnvironmentVariables": dict(sorted(env_vars.items())),
        "ProgramArguments": ["/bin/sh", "-c", _build_setenv_script(env_vars)],
        "RunAtLoad": True,
        "KeepAlive": False,
    }
    return plistlib.dumps(plist)


def _read_plist_env_vars(path: Path) -> dict[str, str]:
    """Read the `EnvironmentVariables` dict from a previously-written plist.
    Returns an empty dict when the file is absent, unreadable, or doesn't
    contain the key. Non-string values are coerced to str."""
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}
    env = data.get("EnvironmentVariables") if isinstance(data, dict) else None
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v) for k, v in env.items()}


def _update_environ(changes: dict[str, str | None]) -> None:
    """Mirror applied changes into this process's `os.environ` so subprocesses
    spawned by EnvEdit (e.g. from `openFolder`) see the new values without a
    restart. Issue 01 Notes item."""
    for k, v in changes.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _launchctl_setenv_live(changes: dict[str, str | None]) -> None:
    """Apply `changes` to the running gui/$UID launchd session so already-open
    apps' children and freshly launched GUI apps see new values immediately.

    `launchctl setenv` is per-session and resets at logout — the persisted
    plist re-applies the same values at next login.
    """
    for name, val in changes.items():
        try:
            if val is None:
                subprocess.run(
                    ["launchctl", "unsetenv", name],
                    check=False,
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["launchctl", "setenv", name, val],
                    check=False,
                    capture_output=True,
                )
        except OSError:
            # launchctl is part of macOS; the only realistic OSError here is
            # PATH stripping in a weird subprocess environment. Swallow rather
            # than fail the whole apply — the persisted plist still wins at
            # next login.
            pass


def _render_paths_d(entries: list[str]) -> str:
    """Render `/etc/paths.d/envedit` content. `path_helper(8)` reads one path
    per line, ignoring blanks; entries with whitespace or `:` are unsafe but
    we already validate against `os.pathsep`/newline upstream in PathModel."""
    return "".join(entry + "\n" for entry in entries if entry)


def _read_paths_d() -> list[str]:
    if not _SYSTEM_PATHS_D.is_file():
        return []
    try:
        return [
            line.strip()
            for line in _SYSTEM_PATHS_D.read_text(errors="replace").splitlines()
            if line.strip()
        ]
    except OSError:
        return []


class MacOSBackend(UnixBackend):
    """Layered on top of `UnixBackend`: keeps env.sh writes intact for Terminal
    users, adds launchd plist + `launchctl setenv` so GUI apps see edits."""

    # ---- reads ------------------------------------------------------------

    def get_user_vars(self) -> dict[str, str]:
        # Prefer the LaunchAgent plist as the canonical store — that's the
        # file that actually drives GUI-app env on this platform. Fall back
        # to env.sh when the plist doesn't exist yet (first run after macOS
        # backend was added) so the migration is seamless.
        managed = _read_plist_env_vars(_USER_AGENT_PLIST)
        if not managed:
            managed = _read_envedit_vars()
        result: dict[str, str] = {}
        for k, v in managed.items():
            if k in _PATH_KEYS:
                continue
            result[k] = os.environ.get(k, v)
        for k, v in os.environ.items():
            if k in _PATH_KEYS or k in result:
                continue
            if _is_runtime_var(k):
                continue
            result[k] = v
        return result

    def get_system_vars(self) -> dict[str, str]:
        return {
            k: v
            for k, v in _read_plist_env_vars(_SYSTEM_DAEMON_PLIST).items()
            if k not in _PATH_KEYS
        }

    def get_user_path(self) -> list[str]:
        managed = _read_plist_env_vars(_USER_AGENT_PLIST)
        if not managed:
            managed = _read_envedit_vars()
        if "PATH" not in managed:
            return [_PATH_INHERIT_TOKEN]
        return [p for p in managed["PATH"].split(os.pathsep) if p]

    def get_system_path(self) -> list[str]:
        # /etc/paths.d/envedit is the canonical source for system PATH on
        # macOS — path_helper(8) merges it into the default shell PATH at
        # /etc/profile time, and the LaunchDaemon's PATH key feeds GUI apps.
        # Read from /etc/paths.d so the ordering the user sees in the UI
        # matches the ordering path_helper actually applies.
        entries = _read_paths_d()
        if entries:
            return entries
        # Fall back to the plist's PATH key if /etc/paths.d/envedit is absent
        # (e.g. legacy state where only the daemon plist was written).
        sys_vars = _read_plist_env_vars(_SYSTEM_DAEMON_PLIST)
        path_str = sys_vars.get("PATH", "")
        return [p for p in path_str.split(os.pathsep) if p]

    # ---- writes -----------------------------------------------------------

    def apply_user_vars(self, changes: dict[str, str | None]) -> None:
        # Step 1: env.sh + profile-source line (Terminal coverage).
        super().apply_user_vars(changes)
        # Step 2: rebuild the LaunchAgent plist from the current full set of
        # managed vars (env.sh's parser is the source of truth for which
        # keys we own). Including PATH is fine — launchd's setenv overrides
        # any inherited value, and we re-emit it whether or not it changed.
        full = _read_envedit_vars()
        _write_user_plist(full)
        # Step 3: live launchd session — GUI apps launched from now on see
        # the new values without a logout.
        _launchctl_setenv_live(changes)
        # Step 4: in-process os.environ so EnvEdit's own subprocesses pick
        # up the change immediately.
        _update_environ(changes)

    def apply_user_path(self, entries: list[str]) -> None:
        if not entries:
            entries = [_PATH_INHERIT_TOKEN]
        new_path = os.pathsep.join(entries)
        self.apply_user_vars({"PATH": new_path})

    def apply_system_vars(
        self, changes: dict[str, str | None], on_complete=None
    ) -> bool:
        # Merge changes against the existing daemon plist's EnvironmentVariables.
        existing = _read_plist_env_vars(_SYSTEM_DAEMON_PLIST)
        merged: dict[str, str] = dict(existing)
        for key, val in changes.items():
            if val is None:
                merged.pop(key, None)
            else:
                merged[key] = val
        # PATH lives in /etc/paths.d/envedit; the daemon plist tracks it too
        # for symmetry with read paths.
        paths_d_entries = self.get_system_path()
        plist_bytes = _render_plist(_SYSTEM_DAEMON_LABEL, merged)
        return _apply_system_files(
            plist_path=_SYSTEM_DAEMON_PLIST,
            plist_content=plist_bytes,
            paths_d_path=_SYSTEM_PATHS_D,
            paths_d_content=_render_paths_d(paths_d_entries),
            live_changes=changes,
            on_complete=on_complete,
        )

    def apply_system_path(
        self, entries: list[str], on_complete=None
    ) -> bool:
        # Update both /etc/paths.d/envedit and the daemon plist's PATH key.
        existing = _read_plist_env_vars(_SYSTEM_DAEMON_PLIST)
        new_path = os.pathsep.join(entries)
        merged = dict(existing)
        if entries:
            merged["PATH"] = new_path
        else:
            merged.pop("PATH", None)
        plist_bytes = _render_plist(_SYSTEM_DAEMON_LABEL, merged)
        return _apply_system_files(
            plist_path=_SYSTEM_DAEMON_PLIST,
            plist_content=plist_bytes,
            paths_d_path=_SYSTEM_PATHS_D,
            paths_d_content=_render_paths_d(entries),
            live_changes={"PATH": new_path} if entries else {"PATH": None},
            on_complete=on_complete,
        )


def _write_user_plist(env_vars: dict[str, str]) -> None:
    """Atomically write the LaunchAgent plist. Creates ~/Library/LaunchAgents
    if missing — fresh macOS user accounts don't ship with it."""
    _USER_AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USER_AGENT_PLIST.with_suffix(_USER_AGENT_PLIST.suffix + ".tmp")
    tmp.write_bytes(_render_plist(_USER_AGENT_LABEL, env_vars))
    os.replace(tmp, _USER_AGENT_PLIST)


def _apply_system_files(
    *,
    plist_path: Path,
    plist_content: bytes,
    paths_d_path: Path,
    paths_d_content: str,
    live_changes: dict[str, str | None],
    on_complete=None,
) -> bool:
    """Write the system plist, /etc/paths.d/envedit, AND apply live changes to
    the system launchd domain — all behind a single osascript password prompt.

    Returns True if applied synchronously (already root), False if dispatched
    to a worker thread that prompts via osascript.
    """
    import base64
    import json
    import threading

    plist_b64 = base64.b64encode(plist_content).decode("ascii")
    paths_b64 = base64.b64encode(paths_d_content.encode("utf-8")).decode("ascii")

    plist_dest = shlex.quote(str(plist_path))
    plist_new = shlex.quote(str(plist_path) + ".new")
    plist_dir = shlex.quote(str(plist_path.parent))
    paths_dest = shlex.quote(str(paths_d_path))
    paths_new = shlex.quote(str(paths_d_path) + ".new")
    paths_dir = shlex.quote(str(paths_d_path.parent))

    # Live system-launchd updates are mirrored inside the same elevated shell
    # so the user pays exactly one password prompt per Apply.
    live_cmds: list[str] = []
    for name, val in live_changes.items():
        if val is None:
            live_cmds.append(f"launchctl unsetenv {shlex.quote(name)} || true")
        else:
            live_cmds.append(
                f"launchctl setenv {shlex.quote(name)} {shlex.quote(val)} || true"
            )

    shell_cmd = (
        "set -e; "
        "umask 022; "
        f"mkdir -p {plist_dir}; "
        f"mkdir -p {paths_dir}; "
        f"printf %s {shlex.quote(plist_b64)} | base64 -d > {plist_new}; "
        f"chmod 644 {plist_new}; "
        f"mv {plist_new} {plist_dest}; "
        f"printf %s {shlex.quote(paths_b64)} | base64 -d > {paths_new}; "
        f"chmod 644 {paths_new}; "
        f"mv {paths_new} {paths_dest}; "
        + "; ".join(live_cmds)
    )

    if is_elevated():
        subprocess.run(["sh", "-c", shell_cmd], check=True)
        _update_environ(live_changes)
        return True

    if on_complete is None:
        # Synchronous elevation prompt — used by tests / non-GUI callers.
        script = (
            f"do shell script {json.dumps(shell_cmd)} "
            f"with administrator privileges"
        )
        subprocess.run(["osascript", "-e", script], check=True)
        _update_environ(live_changes)
        return True

    def _run():
        try:
            script = (
                f"do shell script {json.dumps(shell_cmd)} "
                f"with administrator privileges"
            )
            subprocess.run(["osascript", "-e", script], check=True)
            _update_environ(live_changes)
            on_complete(timed_out=False)
        except Exception:
            on_complete(timed_out=True)

    threading.Thread(target=_run, daemon=True).start()
    return False
