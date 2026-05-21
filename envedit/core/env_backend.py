from __future__ import annotations

import sys
from abc import ABC, abstractmethod


class EnvBackend(ABC):
    @abstractmethod
    def get_user_vars(self) -> dict[str, str]: ...

    @abstractmethod
    def get_system_vars(self) -> dict[str, str]: ...

    @abstractmethod
    def get_user_path(self) -> list[str]: ...

    @abstractmethod
    def get_system_path(self) -> list[str]: ...

    @abstractmethod
    def apply_user_vars(self, changes: dict[str, str | None]) -> None:
        """Apply changes to user variables. A None value means delete the key."""

    @abstractmethod
    def apply_system_vars(self, changes: dict[str, str | None], on_complete=None) -> bool:
        """Apply changes to system variables. A None value means delete the key.
        Returns True if applied synchronously, False if dispatched to an elevated child.
        on_complete, if provided, is called from a background thread when the child exits."""

    @abstractmethod
    def apply_user_path(self, entries: list[str]) -> None:
        """Replace the full user PATH with the given list."""

    @abstractmethod
    def apply_system_path(self, entries: list[str], on_complete=None) -> bool:
        """Replace the full system PATH with the given list.
        Returns True if applied synchronously, False if dispatched to an elevated child.
        on_complete, if provided, is called from a background thread when the child exits."""

    @abstractmethod
    def expand_value(self, value: str) -> str: ...


def get_backend() -> EnvBackend:
    if sys.platform == "win32":
        from envedit.core.platform_windows import WindowsBackend
        return WindowsBackend()
    if sys.platform == "darwin":
        from envedit.core.platform_macos import MacOSBackend
        return MacOSBackend()
    from envedit.core.platform_unix import UnixBackend
    return UnixBackend()
