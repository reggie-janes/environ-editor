from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

from envedit.core.env_backend import EnvBackend

_PATH_KEYS = {"PATH"}
_HKCU_ENV = r"Environment"
_HKLM_ENV = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _iget(d: dict[str, str], key: str, default: str = "") -> str:
    """Case-insensitive dict get — registry key names are not case-sensitive."""
    key_upper = key.upper()
    return next((v for k, v in d.items() if k.upper() == key_upper), default)


def _stored_name(key, requested: str) -> str:
    """Return the case-preserved value name already in the registry.

    SetValueEx is case-insensitive for matching but case-preserving for
    storage: passing a different case renames the value. Re-using the
    already-stored name avoids silently renaming `Path` to `PATH` (or any
    other mixed-case name written by Windows or third-party tools).
    """
    import winreg
    target = requested.lower()
    i = 0
    while True:
        try:
            name, _data, _kind = winreg.EnumValue(key, i)
        except OSError:
            return requested
        if name.lower() == target:
            return name
        i += 1


class WindowsBackend(EnvBackend):
    def get_user_vars(self) -> dict[str, str]:
        return {k: v for k, v in self._read_hkcu().items() if k.upper() != "PATH"}

    def get_system_vars(self) -> dict[str, str]:
        return {k: v for k, v in self._read_hklm().items() if k.upper() != "PATH"}

    def get_user_path(self) -> list[str]:
        val = _iget(self._read_hkcu(), "PATH")
        return [p for p in val.split(os.pathsep) if p]

    def get_system_path(self) -> list[str]:
        val = _iget(self._read_hklm(), "PATH")
        return [p for p in val.split(os.pathsep) if p]

    def apply_user_vars(self, changes: dict[str, str | None]) -> None:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _HKCU_ENV, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            for name, val in changes.items():
                stored = _stored_name(key, name)
                if val is None:
                    try:
                        winreg.DeleteValue(key, stored)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, stored, 0,
                                      self._reg_type_for(key, stored, val), val)
        self._broadcast_change()

    def apply_system_vars(self, changes: dict[str, str | None], on_complete=None) -> bool:
        from envedit.core.privilege import is_elevated, request_elevation_and_apply
        if not is_elevated():
            if not request_elevation_and_apply({"system_vars": changes}, on_complete=on_complete):
                return None  # user cancelled UAC — not an error
            return False  # elevated child was launched but hasn't written yet
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _HKLM_ENV, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            for name, val in changes.items():
                stored = _stored_name(key, name)
                if val is None:
                    try:
                        winreg.DeleteValue(key, stored)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, stored, 0,
                                      self._reg_type_for(key, stored, val), val)
        self._broadcast_change()
        return True

    @staticmethod
    def _reg_type_for(key, name: str, value: str) -> int:
        """Preserve the existing key's type when overwriting; for new keys,
        pick REG_EXPAND_SZ only when the value actually contains a `%VAR%`
        reference. The previous behaviour of always picking REG_EXPAND_SZ
        silently upgraded REG_SZ values written by other tools and turned
        literal `%` characters in user-typed values into surprise expansions.
        """
        import winreg
        try:
            _, kind = winreg.QueryValueEx(key, name)
            if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                return int(kind)
        except FileNotFoundError:
            pass
        # New value: heuristic — expand-on-read only when there is at least
        # one `%...%` pair. Values containing isolated `%` (e.g. "100%") get
        # REG_SZ so they round-trip literally.
        if "%" in value and value.count("%") >= 2:
            # Cheap regex-free check: a likely %VAR% somewhere.
            first = value.find("%")
            second = value.find("%", first + 1)
            if second > first + 1:
                return winreg.REG_EXPAND_SZ
        return winreg.REG_SZ

    def apply_user_path(self, entries: list[str]) -> None:
        self.apply_user_vars({"PATH": os.pathsep.join(entries)})

    def apply_system_path(self, entries: list[str], on_complete=None) -> bool:
        return self.apply_system_vars({"PATH": os.pathsep.join(entries)}, on_complete=on_complete)

    def expand_value(self, value: str) -> str:
        import ctypes
        buf = ctypes.create_unicode_buffer(32767)
        # ExpandEnvironmentStringsW returns 0 on failure or the required buffer
        # size (incl. NUL) on success. If it would overflow the buffer it
        # returns a value > 32767 — also treat that as a failure rather than
        # show a silently truncated string. In both cases fall back to the raw
        # input so the user sees something meaningful in the Expanded column.
        result = ctypes.windll.kernel32.ExpandEnvironmentStringsW(value, buf, 32767)
        if result == 0 or result > 32767:
            return value
        return buf.value

    def _read_hkcu(self) -> dict[str, str]:
        import winreg
        return self._read_registry_env(winreg.HKEY_CURRENT_USER, _HKCU_ENV)

    def _read_hklm(self) -> dict[str, str]:
        import winreg
        return self._read_registry_env(winreg.HKEY_LOCAL_MACHINE, _HKLM_ENV)

    @staticmethod
    def _read_registry_env(hive: int, subkey: str) -> dict[str, str]:
        import winreg
        result: dict[str, str] = {}
        try:
            with winreg.OpenKey(hive, subkey) as key:
                i = 0
                while True:
                    try:
                        name, data, _ = winreg.EnumValue(key, i)
                        result[name] = str(data)
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
        return result

    @staticmethod
    def _broadcast_change() -> None:
        import ctypes
        from ctypes import wintypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002

        # SendMessageTimeoutW's lpdwResult is PDWORD_PTR — pointer-sized
        # (4 bytes on Win32, 8 bytes on Win64). c_size_t matches that.
        # Without explicit argtypes/restype ctypes assumes 32-bit C int,
        # which corrupts the stack when the kernel writes 8 bytes back
        # into a 4-byte buffer.
        SendMessageTimeoutW = ctypes.windll.user32.SendMessageTimeoutW
        SendMessageTimeoutW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_wchar_p,
            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
        ]
        SendMessageTimeoutW.restype = ctypes.c_ssize_t

        result = ctypes.c_size_t()
        SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, ctypes.byref(result),
        )
