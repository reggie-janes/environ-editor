"""Tests for WindowsBackend and helpers in platform_windows.py.

The real `winreg` and `ctypes.windll` modules don't exist on Linux, so the
tests stub `winreg` into `sys.modules` before importing the backend, and
mark anything that needs a real `windll` as Windows-only.
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# winreg stub (autouse — keeps sys.modules clean even if a test bypasses it)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_winreg(monkeypatch):
    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER = 1
    fake.HKEY_LOCAL_MACHINE = 2
    fake.KEY_SET_VALUE = 0x0002
    fake.KEY_READ = 0x20019
    fake.REG_SZ = 1
    fake.REG_EXPAND_SZ = 2
    fake.OpenKey = MagicMock()
    fake.SetValueEx = MagicMock()
    fake.DeleteValue = MagicMock()
    fake.EnumValue = MagicMock(side_effect=OSError)
    # _reg_type_for() queries existing value type with QueryValueEx. Default
    # to "not found" so new writes go through the heuristic branch.
    fake.QueryValueEx = MagicMock(side_effect=FileNotFoundError)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    return fake


# ---------------------------------------------------------------------------
# _iget — case-insensitive dict get
# ---------------------------------------------------------------------------

class TestIget:
    def test_case_insensitive_lookup(self, fake_winreg):
        from envedit.core.platform_windows import _iget
        assert _iget({"PATH": "x"}, "path") == "x"
        assert _iget({"Path": "y"}, "PATH") == "y"
        assert _iget({"path": "z"}, "Path") == "z"

    def test_default_when_missing(self, fake_winreg):
        from envedit.core.platform_windows import _iget
        assert _iget({}, "missing", default="d") == "d"

    def test_empty_default_when_no_default_given(self, fake_winreg):
        from envedit.core.platform_windows import _iget
        assert _iget({}, "missing") == ""


# ---------------------------------------------------------------------------
# WindowsBackend.apply_user_vars — exercises the winreg call shape
# ---------------------------------------------------------------------------

class TestApplyUserVars:
    def test_set_calls_SetValueEx_with_REG_SZ_for_literal_value(self, fake_winreg):
        # Issue 016: values that don't reference %VAR% should be written as
        # REG_SZ so a literal `%` in the value isn't silently expanded.
        with patch(
            "envedit.core.platform_windows.WindowsBackend._broadcast_change"
        ):
            from envedit.core.platform_windows import WindowsBackend
            WindowsBackend().apply_user_vars({"FOO": "bar"})

        fake_winreg.SetValueEx.assert_called_once()
        args = fake_winreg.SetValueEx.call_args[0]
        # signature: SetValueEx(key, name, reserved, type, data)
        assert args[1] == "FOO"
        assert args[3] == fake_winreg.REG_SZ
        assert args[4] == "bar"

    def test_set_calls_SetValueEx_with_REG_EXPAND_SZ_when_value_has_var(self, fake_winreg):
        # Values containing a `%...%` pair get REG_EXPAND_SZ so the OS
        # expands them on read — that's the right type for PATH-like values.
        with patch(
            "envedit.core.platform_windows.WindowsBackend._broadcast_change"
        ):
            from envedit.core.platform_windows import WindowsBackend
            WindowsBackend().apply_user_vars({"FOO": "%SystemRoot%\\bin"})

        args = fake_winreg.SetValueEx.call_args[0]
        assert args[3] == fake_winreg.REG_EXPAND_SZ

    def test_set_preserves_existing_type(self, fake_winreg):
        # An existing REG_EXPAND_SZ key keeps that type even if the new
        # literal value lacks `%...%`. Round-trip fidelity matters here —
        # downgrading to REG_SZ would silently change semantics for any
        # other reader of that key.
        fake_winreg.QueryValueEx = MagicMock(return_value=("old", fake_winreg.REG_EXPAND_SZ))
        with patch(
            "envedit.core.platform_windows.WindowsBackend._broadcast_change"
        ):
            from envedit.core.platform_windows import WindowsBackend
            WindowsBackend().apply_user_vars({"FOO": "literal"})

        args = fake_winreg.SetValueEx.call_args[0]
        assert args[3] == fake_winreg.REG_EXPAND_SZ

    def test_none_value_calls_DeleteValue(self, fake_winreg):
        with patch(
            "envedit.core.platform_windows.WindowsBackend._broadcast_change"
        ):
            from envedit.core.platform_windows import WindowsBackend
            WindowsBackend().apply_user_vars({"GONE": None})

        fake_winreg.DeleteValue.assert_called_once()
        args = fake_winreg.DeleteValue.call_args[0]
        assert args[1] == "GONE"
        # SetValueEx must not be called for a delete
        assert fake_winreg.SetValueEx.call_count == 0

    def test_delete_swallows_FileNotFoundError(self, fake_winreg):
        fake_winreg.DeleteValue.side_effect = FileNotFoundError
        with patch(
            "envedit.core.platform_windows.WindowsBackend._broadcast_change"
        ):
            from envedit.core.platform_windows import WindowsBackend
            # Must not raise.
            WindowsBackend().apply_user_vars({"GONE": None})


# ---------------------------------------------------------------------------
# Read paths — make EnumValue yield a couple of values then OSError
# ---------------------------------------------------------------------------

class TestReadHkcu:
    def test_get_user_vars_excludes_PATH(self, fake_winreg):
        # Sequence: ("PATH", "/x", REG_EXPAND_SZ), ("FOO", "bar", REG_EXPAND_SZ), then stop.
        fake_winreg.EnumValue.side_effect = [
            ("PATH", "/x", 2),
            ("FOO", "bar", 2),
            OSError,
        ]
        from envedit.core.platform_windows import WindowsBackend
        result = WindowsBackend().get_user_vars()
        assert "PATH" not in result
        assert result["FOO"] == "bar"

    def test_get_user_path_splits_on_pathsep(self, fake_winreg):
        # WindowsBackend splits on os.pathsep. To stay portable across
        # CI runners (Linux uses ':', Windows uses ';'), build the input
        # from os.pathsep itself and use sentinel paths that don't
        # contain a drive letter (which would clash with ':' on Linux).
        path_str = os.pathsep.join(["alpha", "beta", "gamma"])
        fake_winreg.EnumValue.side_effect = [
            ("PATH", path_str, 2),
            OSError,
        ]
        from envedit.core.platform_windows import WindowsBackend
        result = WindowsBackend().get_user_path()
        assert result == ["alpha", "beta", "gamma"]

    def test_get_user_path_when_missing_returns_empty(self, fake_winreg):
        fake_winreg.EnumValue.side_effect = OSError
        from envedit.core.platform_windows import WindowsBackend
        assert WindowsBackend().get_user_path() == []
