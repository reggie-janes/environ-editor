from __future__ import annotations

import json
import os
import subprocess
import sys


def is_elevated() -> bool:
    if sys.platform == "win32":
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return os.getuid() == 0


def request_elevation_and_apply(changes: dict) -> bool:
    """
    Relaunch the process with elevated privileges, passing changes as a JSON arg.
    Returns True if the elevated process was launched (result unknown), False on cancel.
    """
    payload = json.dumps(changes)

    if sys.platform == "win32":
        import ctypes
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            f'"{sys.argv[0]}" --apply-system {json.dumps(payload)}',
            None, 1,
        )
        return int(result) > 32

    elif sys.platform == "darwin":
        script = (
            f'do shell script "{sys.executable} {sys.argv[0]} '
            f'--apply-system \\"{payload.replace(chr(34), chr(92)+chr(34))}\\"" '
            f'with administrator privileges'
        )
        try:
            subprocess.run(["osascript", "-e", script], check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    else:
        import shutil
        tool = "pkexec" if shutil.which("pkexec") else "sudo"
        try:
            subprocess.run(
                [tool, sys.executable, sys.argv[0], "--apply-system", payload],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False
