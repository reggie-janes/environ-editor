"""Tests for privilege.py helpers."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from envedit.core.privilege import is_elevated, request_elevation_and_apply


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

    def test_passes_json_payload_as_argument(self):
        import json
        captured_cmd = []
        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return MagicMock(returncode=0)

        with patch.object(sys, "platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/pkexec"), \
             patch("subprocess.run", side_effect=fake_run):
            request_elevation_and_apply({"system_vars": {"KEY": "val"}})

        # The last argument should be a JSON string containing our payload
        payload_str = captured_cmd[-1]
        payload = json.loads(payload_str)
        assert payload["system_vars"]["KEY"] == "val"
