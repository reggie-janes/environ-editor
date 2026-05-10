from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from typing import Callable


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


def request_elevation_and_apply(changes: dict, on_complete: Callable[[], None] | None = None) -> bool:
    """
    Relaunch the process with elevated privileges, passing changes via a temp
    JSON file. Returns True if the elevated process was launched, False on cancel.

    If on_complete is provided, it is called from a background thread once the
    elevated child process exits (Windows only; Unix applies synchronously).
    """
    payload_path = _write_payload_file(changes)

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        import threading

        params = subprocess.list2cmdline(
            [sys.argv[0], "--apply-system-file", payload_path]
        )

        SEE_MASK_NOCLOSEPROCESS = 0x00000040

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize",         wintypes.DWORD),
                ("fMask",          wintypes.ULONG),
                ("hwnd",           wintypes.HWND),
                ("lpVerb",         wintypes.LPCWSTR),
                ("lpFile",         wintypes.LPCWSTR),
                ("lpParameters",   wintypes.LPCWSTR),
                ("lpDirectory",    wintypes.LPCWSTR),
                ("nShow",          ctypes.c_int),
                ("hInstApp",       wintypes.HINSTANCE),
                ("lpIDList",       ctypes.c_void_p),
                ("lpClass",        wintypes.LPCWSTR),
                ("hkeyClass",      wintypes.HKEY),
                ("dwHotKey",       wintypes.DWORD),
                ("hIconOrMonitor", wintypes.HANDLE),
                ("hProcess",       wintypes.HANDLE),
            ]

        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.lpVerb = "runas"
        sei.lpFile = sys.executable
        sei.lpParameters = params
        sei.nShow = 0  # SW_HIDE

        ShellExecuteExW = ctypes.windll.shell32.ShellExecuteExW
        ShellExecuteExW.restype = wintypes.BOOL

        if not ShellExecuteExW(ctypes.byref(sei)):
            try:
                os.unlink(payload_path)
            except OSError:
                pass
            return False

        hProcess = sei.hProcess
        if on_complete and hProcess:
            WAIT_TIMEOUT = 0x102
            def _wait_and_notify():
                ret = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 30000)
                ctypes.windll.kernel32.CloseHandle(hProcess)
                # Call on_complete regardless of timeout so isBusy always clears.
                # If timed out, the reload may show stale data, but that's better
                # than a stuck spinner — the elevated child likely hung.
                on_complete(timed_out=(ret == WAIT_TIMEOUT))
            threading.Thread(target=_wait_and_notify, daemon=True).start()
        elif hProcess:
            ctypes.windll.kernel32.CloseHandle(hProcess)

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
