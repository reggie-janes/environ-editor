from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from envedit.core.env_backend import EnvBackend
from envedit.core.privilege import is_elevated

_ENVEDIT_SH = Path.home() / ".config" / "envedit" / "env.sh"
_SYSTEM_ENV = Path("/etc/environment")
_SYSTEM_PROFILE_D = Path("/etc/profile.d/envedit.sh")
_MANAGED_HEADER = "# Managed by EnvEdit — do not edit manually"
_MANAGED_HEADER_PREFIX = "# Managed by EnvEdit"
# Marker that introduces the passthrough block in the rewritten file. Lines
# emitted after this marker are content the parser didn't recognise on the
# previous read and that we want to preserve across round-trips.
_PASSTHROUGH_HEADER = "# --- preserved (not managed by EnvEdit) ---"
# When a User-tab PATH apply would otherwise replace the inherited PATH, the
# writer prefixes the managed entries with a sentinel that survives the
# round-trip: on parse we recognise it and don't surface it as an editable
# path entry.
_PATH_INHERIT_TOKEN = "$PATH"

# Variables we never expose in the user-vars table (shown in PATH tab instead)
_PATH_KEYS = {"PATH"}

# Runtime-only env vars set by the shell, display manager, or session bus.
# These leak into os.environ at every login but are not user-managed — if the
# user "edits" them, the edit gets persisted to env.sh and silently overrides
# the session-local value forever after. Hide them from the User tab unless
# the user has already chosen to manage them via env.sh.
_RUNTIME_VAR_NAMES = frozenset({
    "_",
    "OLDPWD", "PWD", "SHLVL",
    "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
    "SSH_AGENT_PID", "SSH_AUTH_SOCK", "SSH_CLIENT", "SSH_CONNECTION", "SSH_TTY",
    "DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_BUS_TYPE",
    "GNOME_TERMINAL_SCREEN", "GNOME_TERMINAL_SERVICE", "TERM_PROGRAM",
    "VTE_VERSION", "WINDOWID", "COLORTERM",
    "LS_COLORS", "LESSOPEN", "LESSCLOSE", "TERM",
    "MAIL", "LOGNAME", "USER", "HOME", "SHELL",
})
_RUNTIME_VAR_PREFIXES = ("XDG_", "DBUS_", "GDM_", "GNOME_", "KDE_", "QT_AUTO_")


def _parse_shell_assigns(text: str) -> dict[str, str]:
    """Extract VAR=value / export VAR=value lines from shell-script text."""
    result, _ = _parse_shell_assigns_with_passthrough(text)
    return result


def _parse_shell_assigns_with_passthrough(text: str) -> tuple[dict[str, str], list[str]]:
    """Like `_parse_shell_assigns` but also returns the verbatim lines that did
    not match the writer's `(export )?NAME='value'` format. Callers that want
    to preserve hand-edited content (comments, conditionals, foreign exports)
    re-emit those lines after writing the managed assignments.

    The header comment and the passthrough-block marker are filtered out —
    `_format_env_sh` re-emits both. Blank lines are not preserved.
    """
    parsed: dict[str, str] = {}
    extras: list[str] = []
    in_passthrough = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(_MANAGED_HEADER_PREFIX) or stripped == _PASSTHROUGH_HEADER:
            in_passthrough = stripped == _PASSTHROUGH_HEADER
            continue
        if in_passthrough:
            extras.append(raw)
            continue
        body = re.sub(r"^export\s+", "", stripped)
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", body)
        if m:
            name, val = m.group(1), m.group(2)
            decoded = _decode_shell_value(val)
            if decoded is not None:
                parsed[name] = decoded
                continue
        extras.append(raw)
    return parsed, extras


def _decode_shell_value(s: str) -> str | None:
    """Decode a shell-style RHS supporting concatenated quoted/unquoted runs.

    Recognises:
      * single-quoted strings (literal contents — POSIX has no escapes inside)
      * double-quoted strings (legacy writer output; reverses `\\"`/`\\\\`)
      * unquoted runs: barewords, `$NAME`, and backslash-escaped chars
    The writer emits an embedded `'` in single-quoted form using the standard
    `'\\''` sequence (close, escaped quote, reopen). Treating `\\'` as a
    literal `'` in the unquoted branch handles that sequence as a side effect.
    Returns the decoded value, or None if the input doesn't fit those forms.
    """
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                return None
            out.append(s[i + 1:j])
            i = j + 1
        elif c == '"':
            j = i + 1
            # Walk past escaped quotes (\") and escaped backslashes (\\)
            while j < n:
                if s[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if s[j] == '"':
                    break
                j += 1
            if j >= n:
                return None
            segment = s[i + 1:j].replace('\\"', '"').replace("\\\\", "\\")
            out.append(segment)
            i = j + 1
        elif c == "\\":
            # Outside quotes, `\X` is a literal X. The writer relies on this
            # for `'\''` → embedded single quote.
            if i + 1 >= n:
                return None
            out.append(s[i + 1])
            i += 2
        else:
            # Unquoted run — reject whitespace and shell metacharacters so
            # we don't silently accept content the shell would interpret.
            # '$' is rejected so that hand-edited `export FOO=$HOME/bin` is
            # treated as passthrough rather than parsed as the literal string
            # "$HOME/bin" and then re-emitted as `export FOO='$HOME/bin'`
            # (which prevents shell expansion on next login).
            j = i
            while j < n and s[j] not in "'\"\\":
                if s[j] in " \t$":
                    return None
                j += 1
            out.append(s[i:j])
            i = j
    return "".join(out)


def _is_runtime_var(name: str) -> bool:
    if name in _RUNTIME_VAR_NAMES:
        return True
    return any(name.startswith(p) for p in _RUNTIME_VAR_PREFIXES)


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
        # The managed env.sh holds the variables the user has chosen to
        # persist. os.environ also holds the runtime session state — DISPLAY,
        # PWD, SSH_AUTH_SOCK, XDG_*, etc. — which we deliberately *do not*
        # surface unless the user has already opted to manage that name
        # (i.e. it's in env.sh). Surfacing them was a foot-gun: editing
        # `DISPLAY=:0` to `:1` would write a permanent override to env.sh.
        managed = _read_envedit_vars()
        result: dict[str, str] = {}
        for k, v in managed.items():
            if k in _PATH_KEYS:
                continue
            # Managed keys always show, prefer the live session value when
            # available (post-apply reloads see the new value immediately).
            result[k] = os.environ.get(k, v)
        for k, v in os.environ.items():
            if k in _PATH_KEYS or k in result:
                continue
            if _is_runtime_var(k):
                continue
            result[k] = v
        return result

    def get_system_vars(self) -> dict[str, str]:
        raw = _read_system_env_file()
        return {k: v for k, v in raw.items() if k not in _PATH_KEYS}

    def get_user_path(self) -> list[str]:
        # Return only what EnvEdit's managed file contributes — never the
        # merged session PATH. Reading the merged PATH would (a) clone the
        # entire system PATH on first apply, and (b) silently revert the
        # user's edits on the post-apply reload (since os.environ won't
        # change until the next login).
        #
        # When the file has no PATH key yet, surface the `$PATH` sentinel
        # row so that the first user-added entry doesn't replace the
        # inherited PATH wholesale on the next login.
        envedit_vars = _read_envedit_vars()
        if "PATH" not in envedit_vars:
            return [_PATH_INHERIT_TOKEN]
        return [p for p in envedit_vars["PATH"].split(os.pathsep) if p]

    def get_system_path(self) -> list[str]:
        sys_vars = _read_system_env_file()
        path_str = sys_vars.get("PATH", "")
        return [p for p in path_str.split(os.pathsep) if p]

    def apply_user_vars(self, changes: dict[str, str | None]) -> None:
        _ENVEDIT_SH.parent.mkdir(parents=True, exist_ok=True)
        with _user_lock():
            existing, extras = ({}, [])
            if _ENVEDIT_SH.is_file():
                existing, extras = _parse_shell_assigns_with_passthrough(
                    _ENVEDIT_SH.read_text(errors="replace")
                )
            for key, val in changes.items():
                if val is None:
                    existing.pop(key, None)
                else:
                    existing[key] = val
            _write_env_sh(_ENVEDIT_SH, existing, extras)
        _ensure_sourced_in_profile()

    def apply_system_vars(self, changes: dict[str, str | None], on_complete=None) -> bool:
        # Write to /etc/profile.d/envedit.sh rather than /etc/environment.
        # /etc/environment is co-managed (cloud-init, distro packages, PAM
        # comments) and parsing/rewriting it loses foreign content. The
        # profile.d file is something we own end-to-end and can safely
        # rewrite using the same escape-aware writer used for user vars.
        existing, extras = ({}, [])
        if _SYSTEM_PROFILE_D.is_file():
            existing, extras = _parse_shell_assigns_with_passthrough(
                _SYSTEM_PROFILE_D.read_text(errors="replace")
            )
        for key, val in changes.items():
            if val is None:
                existing.pop(key, None)
            else:
                existing[key] = val
        content = _format_env_sh(existing, extras)
        if on_complete is None or is_elevated():
            _write_as_root(_SYSTEM_PROFILE_D, content)
            return True
        # Dispatch the privilege-escalation prompt to a worker thread so the
        # Qt event loop stays responsive while pkexec/sudo waits for the user.
        import threading
        def _run():
            try:
                _write_as_root(_SYSTEM_PROFILE_D, content)
                on_complete(timed_out=False)
            except Exception:
                # CalledProcessError: user cancelled pkexec/sudo prompt or
                # the write was denied. Signal failure so the controller shows
                # an error snackbar and keeps pending state intact for retry.
                on_complete(timed_out=True)
        threading.Thread(target=_run, daemon=True).start()
        return False

    def apply_user_path(self, entries: list[str]) -> None:
        # Never write an empty PATH — that would lock the user out of every
        # command-line tool on the next shell start. If all user-managed rows
        # are removed, preserve the inherit sentinel so the inherited system
        # PATH still applies at login.
        if not entries:
            entries = [_PATH_INHERIT_TOKEN]
        self.apply_user_vars({"PATH": os.pathsep.join(entries)})

    def apply_system_path(self, entries: list[str], on_complete=None) -> bool:
        return self.apply_system_vars(
            {"PATH": os.pathsep.join(entries)},
            on_complete=on_complete,
        )

    def expand_value(self, value: str) -> str:
        return os.path.expandvars(value)


def _format_env_sh(vars_: dict[str, str], extras: list[str] | None = None) -> str:
    # Single-quote values: inside POSIX single quotes nothing is interpreted,
    # so `$`, backticks, and `$(...)` round-trip literally. The only character
    # a single-quoted string cannot contain is `'` itself, which we emit as
    # `'\''` (close, escaped, reopen).
    lines = [_MANAGED_HEADER + "\n"]
    for k, v in sorted(vars_.items()):
        lines.append(f"export {k}={_shell_single_quote(k, v)}\n")
    if extras:
        lines.append("\n" + _PASSTHROUGH_HEADER + "\n")
        for line in extras:
            lines.append(line.rstrip("\n") + "\n")
    return "".join(lines)


def _shell_single_quote(name: str, value: str) -> str:
    # PATH gets special treatment so a first-time write doesn't replace the
    # inherited PATH wholesale. We keep `$PATH` outside the quotes so the
    # shell still expands it; everything else is single-quoted.
    if name == "PATH" and _PATH_INHERIT_TOKEN in value:
        parts: list[str] = []
        for idx, segment in enumerate(value.split(_PATH_INHERIT_TOKEN)):
            if idx > 0:
                parts.append('"' + _PATH_INHERIT_TOKEN + '"')
            if segment:
                parts.append("'" + segment.replace("'", "'\\''") + "'")
        return "".join(parts) if parts else "''"
    return "'" + value.replace("'", "'\\''") + "'"


def _write_env_sh(path: Path, vars_: dict[str, str], extras: list[str] | None = None) -> None:
    # Write to a sibling temp file then os.replace() — a single rename(2)
    # syscall is atomic on POSIX, so a kill/OOM mid-write can't leave the
    # active env.sh truncated. Same-directory temp guarantees same filesystem.
    content = _format_env_sh(vars_, extras)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


@contextlib.contextmanager
def _user_lock():
    """Advisory exclusive lock around the user env.sh read-modify-write block.

    Two EnvEdit instances applying at once would otherwise each read the file,
    apply their own pending changes, and the later writer would clobber the
    earlier one's edits silently. `fcntl.flock` is per-fd and best-effort but
    is sufficient to serialize EnvEdit-against-EnvEdit on the same machine.
    Falls back to a no-op when fcntl is unavailable (e.g. WASI shims).
    """
    try:
        import fcntl  # noqa: PLC0415 — optional on some platforms
    except ImportError:
        yield
        return
    _ENVEDIT_SH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _ENVEDIT_SH.with_suffix(_ENVEDIT_SH.suffix + ".lock")
    with open(lock_path, "w") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


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
    # Login shells read the profile file selected by _login_profile(). But on
    # Linux desktops virtually no terminal starts a login shell — GNOME
    # Terminal, Konsole, etc. start interactive *non-login* shells, which
    # read ~/.bashrc / ~/.zshrc instead of ~/.profile. Patching only the
    # login profile means changes don't take effect for terminal sessions
    # until the next reboot or display-manager login. Seed the guard into
    # both flavours of init file so a fresh terminal picks it up.
    guard = f'[ -f "{_ENVEDIT_SH}" ] && . "{_ENVEDIT_SH}"'
    source_line = f"\n{guard}\n"
    home = Path.home()
    targets: list[Path] = [_login_profile()]
    for name in (".bashrc", ".zshrc"):
        p = home / name
        if p.exists() and p not in targets:
            targets.append(p)
    for profile in targets:
        if not profile.is_file():
            profile.write_text(source_line)
            continue
        content = profile.read_text(errors="replace")
        # Match the full functional guard — a commented-out source line
        # should not suppress re-insertion.
        if guard not in content:
            with profile.open("a") as f:
                f.write(source_line)


def _write_as_root(path: Path, content: str) -> None:
    import base64, shutil

    if is_elevated():
        # Already root — write directly. Skipping pkexec/sudo/osascript also
        # avoids the spurious GUI password prompt on macOS, where osascript
        # asks for a password even when uid is already 0.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        return

    # Embed the content as base64 inside the shell command rather than
    # writing it to a user-owned temp file first. A user-writable
    # intermediate is a TOCTOU vector: between our write and the elevated
    # tool's read, a same-uid hostile process could rewrite the file (or
    # symlink-swap it to /etc/shadow — GNU `install` follows symlinks on
    # its source). With the content baked into the shell-command string,
    # there is no intermediate to race; the elevated shell creates the
    # `.new` file inside the destination directory (root-owned), where a
    # non-root attacker cannot interpose.
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    dest = shlex.quote(str(path))
    dest_new = shlex.quote(str(path) + ".new")
    dest_dir = shlex.quote(str(path.parent))
    shell_cmd = (
        f"set -e; "
        f"umask 022; "
        f"mkdir -p {dest_dir}; "
        f"printf %s {shlex.quote(b64)} | base64 -d > {dest_new}; "
        f"chmod 644 {dest_new}; "
        f"mv {dest_new} {dest}"
    )

    if sys.platform == "darwin":
        # pkexec doesn't exist on macOS; sudo without a controlling terminal
        # fails in a GUI app. osascript with "administrator privileges"
        # shows the native macOS password sheet.
        script = (
            f"do shell script {json.dumps(shell_cmd)} "
            f"with administrator privileges"
        )
        subprocess.run(["osascript", "-e", script], check=True)
    else:
        tool = "pkexec" if shutil.which("pkexec") else "sudo"
        subprocess.run([tool, "sh", "-c", shell_cmd], check=True)
