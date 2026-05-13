from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from typing import Callable


def is_elevated() -> bool:
    if sys.platform == "win32":
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return os.getuid() == 0


def is_elevated_via_wrapper() -> bool:
    """True iff the process is running elevated through a privilege-escalation
    wrapper (sudo / pkexec / su), as opposed to being a genuine root session.

    The distinction matters for user-scoped writes: when launched via a
    wrapper, $HOME points to root and any "user" write would corrupt /root
    instead of the invoking user's account. When the process is genuinely
    root (e.g. a root login on a headless server) there is no invoking user
    and /root is the correct destination.

    Detection is via the env vars the wrappers set on the elevated child:
    SUDO_USER / SUDO_UID (sudo) and PKEXEC_UID (pkexec). Returns False on
    Windows — UAC doesn't switch user identity, so the pattern doesn't apply.
    """
    if not is_elevated() or sys.platform == "win32":
        return False
    return bool(
        os.environ.get("SUDO_USER")
        or os.environ.get("SUDO_UID")
        or os.environ.get("PKEXEC_UID")
    )


def request_elevation_and_apply(changes: dict, on_complete: Callable[..., None] | None = None) -> bool:
    """
    Relaunch the process with elevated privileges (Windows only).

    The payload is base64-encoded and embedded directly in the child's
    command line rather than passed through a temp file. A temp file would
    be writable by the invoking user during the UAC consent window — a
    same-user hostile process could swap its contents before the elevated
    child reads it, achieving arbitrary HKLM env-var writes (e.g. PATH
    injection → SYSTEM execution at next service spawn). The command line
    is fixed at `ShellExecuteEx` invocation time and cannot be tampered
    with after.

    Return value:
      * True — the elevated child has been launched. The child may still
        be running; `on_complete(timed_out=<bool>)` fires from a background
        thread when it exits.
      * False — the user cancelled the UAC prompt or the launch failed.

    Unix is intentionally not implemented: `UnixBackend.apply_system_vars`
    performs elevation inline via `_write_as_root` (see platform_unix.py),
    so the relaunch model is unused on those platforms. Raising rather
    than silently returning prevents future callers from accidentally
    reintroducing the temp-file-payload TOCTOU on Unix.
    """
    if sys.platform != "win32":
        raise NotImplementedError(
            "request_elevation_and_apply is Windows-only; Unix uses "
            "UnixBackend._write_as_root for inline elevation."
        )

    import ctypes
    from ctypes import wintypes
    import threading

    payload_b64 = base64.b64encode(
        json.dumps(changes).encode("utf-8")
    ).decode("ascii")

    # CreateProcess limit on Windows is 32767 wide chars including args and
    # the trailing NUL. Even an unusually long HKLM PATH (~8 KB) base64s to
    # ~11 KB, well under the limit, so this is fine in practice. Reject
    # anything large enough to flirt with the cap so we fail loudly rather
    # than silently truncating arguments at the OS boundary.
    if len(payload_b64) > 30000:
        raise ValueError(
            f"Elevation payload too large for command line "
            f"({len(payload_b64)} chars); refusing to apply."
        )

    params = subprocess.list2cmdline(
        [sys.argv[0], "--apply-system-base64", payload_b64]
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
