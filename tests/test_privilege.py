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
    def test_root_is_elevated(self):
        with patch("os.getuid", return_value=0):
            assert is_elevated() is True

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
    def test_linux_uses_pkexec_when_available(self):
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch.object(sys, "platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/pkexec"), \
             patch("subprocess.run", mock_run) as mock_run:
            result = request_elevation_and_apply({"system_vars": {"FOO": "bar"}})
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "pkexec"

    def test_linux_falls_back_to_sudo_when_no_pkexec(self):
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch.object(sys, "platform", "linux"), \
             patch("shutil.which", return_value=None), \
             patch("subprocess.run", mock_run):
            result = request_elevation_and_apply({"system_vars": {"FOO": "bar"}})
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "sudo"

    def test_linux_returns_false_on_cancelled(self):
        import subprocess
        with patch.object(sys, "platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/pkexec"), \
             patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "pkexec")):
            result = request_elevation_and_apply({"system_vars": {}})
        assert result is False

    def test_passes_json_payload_via_temp_file(self, tmp_path):
        import json
        captured_cmd = []
        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return MagicMock(returncode=0)

        with patch.object(sys, "platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/pkexec"), \
             patch("subprocess.run", side_effect=fake_run):
            request_elevation_and_apply({"system_vars": {"KEY": "val"}})

        # The CLI should pass a path argument after --apply-system-file
        assert "--apply-system-file" in captured_cmd
        path_arg = captured_cmd[captured_cmd.index("--apply-system-file") + 1]
        # File still exists at this point (the elevated child is responsible
        # for unlinking it; the fake never ran the child).
        with open(path_arg) as f:
            payload = json.load(f)
        assert payload["system_vars"]["KEY"] == "val"
        os.unlink(path_arg)
