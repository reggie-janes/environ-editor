from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile


def is_elevated() -> bool:
    if sys.platform == "win32":
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return os.getuid() == 0


def _write_payload_file(changes: dict) -> str:
    """Serialise the payload to a temp JSON file. The elevated child unlinks it."""
    fd, path = tempfile.mkstemp(prefix="envedit-apply-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(changes, f)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def request_elevation_and_apply(changes: dict) -> bool:
    """
    Relaunch the process with elevated privileges, passing changes via a temp
    JSON file. Returns True if the elevated process was launched (result
    unknown), False on cancel.
    """
    payload_path = _write_payload_file(changes)

    if sys.platform == "win32":
        import ctypes
        # Quote each argv with list2cmdline so spaces / quotes survive.
        params = subprocess.list2cmdline(
            [sys.argv[0], "--apply-system-file", payload_path]
        )
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1,
        )
        if int(result) <= 32:
            try:
                os.unlink(payload_path)
            except OSError:
                pass
            return False
        return True

    elif sys.platform == "darwin":
        shell_cmd = shlex.join(
            [sys.executable, sys.argv[0], "--apply-system-file", payload_path]
        )
        # AppleScript string literals share JSON's double-quote/backslash escaping.
        script = f"do shell script {json.dumps(shell_cmd)} with administrator privileges"
        try:
            subprocess.run(["osascript", "-e", script], check=True)
            return True
        except subprocess.CalledProcessError:
            try:
                os.unlink(payload_path)
            except OSError:
                pass
            return False

    else:
        import shutil
        tool = "pkexec" if shutil.which("pkexec") else "sudo"
        try:
            subprocess.run(
                [tool, sys.executable, sys.argv[0],
                 "--apply-system-file", payload_path],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            try:
                os.unlink(payload_path)
            except OSError:
                pass
            return False
