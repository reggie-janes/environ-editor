"""Tests for privilege.py helpers."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from envedit.core.privilege import (
    is_elevated,
    is_elevated_via_wrapper,
    request_elevation_and_apply,
)


class TestIsElevated:
    @pytest.mark.skipif(sys.platform == "win32", reason="os.getuid is Unix-only")
    def test_root_is_elevated(self):
        with patch("os.getuid", return_value=0):
            assert is_elevated() is True

    @pytest.mark.skipif(sys.platform == "win32", reason="os.getuid is Unix-only")
    def test_non_root_is_not_elevated(self):
        with patch("os.getuid", return_value=1000):
            assert is_elevated() is False

    def test_returns_bool(self):
        result = is_elevated()
        assert isinstance(result, bool)


class TestIsElevatedViaWrapper:
    def test_false_when_not_elevated(self):
        with patch("envedit.core.privilege.is_elevated", return_value=False), \
             patch.dict(os.environ, {"SUDO_USER": "alice"}, clear=False):
            assert is_elevated_via_wrapper() is False

    def test_true_when_elevated_and_sudo_user_set(self):
        with patch("envedit.core.privilege.is_elevated", return_value=True), \
             patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {"SUDO_USER": "alice"}, clear=False):
            os.environ.pop("PKEXEC_UID", None)
            assert is_elevated_via_wrapper() is True

    def test_true_when_elevated_and_pkexec_uid_set(self):
        with patch("envedit.core.privilege.is_elevated", return_value=True), \
             patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {"PKEXEC_UID": "1000"}, clear=False):
            os.environ.pop("SUDO_USER", None)
            os.environ.pop("SUDO_UID", None)
            assert is_elevated_via_wrapper() is True

    def test_false_when_elevated_but_no_wrapper_env(self):
        with patch("envedit.core.privilege.is_elevated", return_value=True), \
             patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {}, clear=False):
            for k in ("SUDO_USER", "SUDO_UID", "PKEXEC_UID"):
                os.environ.pop(k, None)
            assert is_elevated_via_wrapper() is False

    def test_false_on_windows(self):
        # Windows UAC doesn't switch user identity, so the wrapper pattern
        # never applies even if env vars somehow contained these keys.
        with patch("envedit.core.privilege.is_elevated", return_value=True), \
             patch.object(sys, "platform", "win32"), \
             patch.dict(os.environ, {"SUDO_USER": "alice"}, clear=False):
            assert is_elevated_via_wrapper() is False


class TestRequestElevationAndApply:
    def test_raises_on_linux(self):
        with patch.object(sys, "platform", "linux"):
            with pytest.raises(NotImplementedError):
                request_elevation_and_apply({"system_vars": {"FOO": "bar"}})

    def test_raises_on_macos(self):
        with patch.object(sys, "platform", "darwin"):
            with pytest.raises(NotImplementedError):
                request_elevation_and_apply({"system_vars": {"FOO": "bar"}})

    def test_rejects_oversized_payload(self):
        # Reject payloads that would risk truncation at Windows' 32767-char
        # CreateProcess command-line limit. Constructing a value whose JSON
        # representation base64s to > 30000 chars verifies the guard fires
        # before any ShellExecuteEx call.
        huge_value = "A" * 25000
        with patch.object(sys, "platform", "win32"):
            with pytest.raises(ValueError, match="too large"):
                request_elevation_and_apply({"system_vars": {"BIG": huge_value}})
