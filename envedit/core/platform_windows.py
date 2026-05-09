from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

from envedit.core.env_backend import EnvBackend

_PATH_KEYS = {"PATH"}
_HKCU_ENV = r"Environment"


def _iget(d: dict[str, str], key: str, default: str = "") -> str:
    """Case-insensitive dict get — registry key names are not case-sensitive."""
    key_upper = key.upper()
    return next((v for k, v in d.items() if k.upper() == key_upper), default)
_HKLM_ENV = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


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
                            winreg.KEY_SET_VALUE) as key:
            for name, val in changes.items():
                if val is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, val)
        self._broadcast_change()

    def apply_system_vars(self, changes: dict[str, str | None]) -> None:
        from envedit.core.privilege import is_elevated, request_elevation_and_apply
        if not is_elevated():
            request_elevation_and_apply({"system_vars": changes})
            return
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _HKLM_ENV, 0,
                            winreg.KEY_SET_VALUE) as key:
            for name, val in changes.items():
                if val is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, val)
        self._broadcast_change()

    def apply_user_path(self, entries: list[str]) -> None:
        self.apply_user_vars({"PATH": os.pathsep.join(entries)})

    def apply_system_path(self, entries: list[str]) -> None:
        self.apply_system_vars({"PATH": os.pathsep.join(entries)})

    def expand_value(self, value: str) -> str:
        import ctypes
        buf = ctypes.create_unicode_buffer(32767)
        ctypes.windll.kernel32.ExpandEnvironmentStringsW(value, buf, 32767)
        return buf.value

    def _read_hkcu(self) -> dict[str, str]:
        return self._read_registry_env(r"HKEY_CURRENT_USER", _HKCU_ENV)

    def _read_hklm(self) -> dict[str, str]:
        return self._read_registry_env(r"HKEY_LOCAL_MACHINE", _HKLM_ENV)

    @staticmethod
    def _read_registry_env(hive_name: str, subkey: str) -> dict[str, str]:
        import winreg
        hive = getattr(winreg, hive_name)
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
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, ctypes.byref(result),
        )
