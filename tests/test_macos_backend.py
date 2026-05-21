"""Tests for the macOS backend (LaunchAgent / LaunchDaemon / launchctl).

These tests deliberately use only mocked subprocess calls and tmp-path file
I/O so they run on every CI platform (the `test` workflow job is Linux-only;
the matrix `build` job on `macos-latest` also runs the suite).
"""
import os
import plistlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from envedit.core.platform_macos import (
    MacOSBackend,
    _USER_AGENT_LABEL,
    _SYSTEM_DAEMON_LABEL,
    _build_setenv_script,
    _render_plist,
    _read_plist_env_vars,
    _render_paths_d,
    _read_paths_d,
    _launchctl_setenv_live,
    _update_environ,
    _apply_system_files,
)


# ---------------------------------------------------------------------------
# _build_setenv_script
# ---------------------------------------------------------------------------

class TestBuildSetenvScript:
    def test_empty_vars_returns_noop(self):
        # launchd disables agents whose ProgramArguments script crashes; an
        # empty argv would do exactly that. `true` is a safe no-op.
        assert _build_setenv_script({}) == "true"

    def test_single_var(self):
        result = _build_setenv_script({"FOO": "bar"})
        assert result == "launchctl setenv FOO bar"

    def test_quotes_value_with_spaces(self):
        result = _build_setenv_script({"FOO": "hello world"})
        assert "launchctl setenv FOO 'hello world'" in result

    def test_quotes_value_with_dollar(self):
        # Critical: an unquoted `$HOME` would be expanded by /bin/sh at agent
        # load time, defeating the point of EnvEdit storing literal values.
        result = _build_setenv_script({"FOO": "$HOME/bin"})
        assert "'$HOME/bin'" in result

    def test_quotes_value_with_single_quote(self):
        result = _build_setenv_script({"FOO": "it's"})
        # shlex.quote uses the standard `'\''` escape sequence.
        assert "launchctl setenv FOO 'it'\"'\"'s'" in result

    def test_sorts_keys(self):
        result = _build_setenv_script({"ZZZ": "1", "AAA": "2"})
        assert result.index("AAA") < result.index("ZZZ")

    def test_multiple_vars_joined_by_semicolon(self):
        result = _build_setenv_script({"A": "1", "B": "2"})
        assert "launchctl setenv A 1; launchctl setenv B 2" == result


# ---------------------------------------------------------------------------
# _render_plist / _read_plist_env_vars
# ---------------------------------------------------------------------------

class TestRenderPlist:
    def test_roundtrip_env_vars(self):
        data = _render_plist("test.label", {"FOO": "bar", "BAZ": "qux"})
        parsed = plistlib.loads(data)
        assert parsed["Label"] == "test.label"
        assert parsed["EnvironmentVariables"] == {"FOO": "bar", "BAZ": "qux"}
        assert parsed["RunAtLoad"] is True

    def test_program_arguments_contains_setenv(self):
        data = _render_plist("x", {"FOO": "bar"})
        parsed = plistlib.loads(data)
        assert parsed["ProgramArguments"][0] == "/bin/sh"
        assert parsed["ProgramArguments"][1] == "-c"
        assert "launchctl setenv FOO bar" in parsed["ProgramArguments"][2]

    def test_empty_vars_still_valid_plist(self):
        data = _render_plist("x", {})
        parsed = plistlib.loads(data)
        assert parsed["EnvironmentVariables"] == {}
        assert parsed["ProgramArguments"][2] == "true"

    def test_special_chars_in_value_xml_escaped(self):
        # plistlib handles XML escaping. <, >, & in values must survive.
        data = _render_plist("x", {"FOO": "<a> & <b>"})
        parsed = plistlib.loads(data)
        assert parsed["EnvironmentVariables"]["FOO"] == "<a> & <b>"

    def test_read_returns_empty_when_file_missing(self, tmp_path):
        assert _read_plist_env_vars(tmp_path / "nope.plist") == {}

    def test_read_returns_empty_when_invalid_xml(self, tmp_path):
        p = tmp_path / "bad.plist"
        p.write_text("not a plist")
        assert _read_plist_env_vars(p) == {}

    def test_read_roundtrips_written_plist(self, tmp_path):
        p = tmp_path / "agent.plist"
        p.write_bytes(_render_plist("x", {"FOO": "bar", "BAZ": "qux"}))
        assert _read_plist_env_vars(p) == {"FOO": "bar", "BAZ": "qux"}

    def test_read_handles_missing_environment_variables_key(self, tmp_path):
        p = tmp_path / "a.plist"
        p.write_bytes(plistlib.dumps({"Label": "x", "RunAtLoad": True}))
        assert _read_plist_env_vars(p) == {}


# ---------------------------------------------------------------------------
# _render_paths_d / _read_paths_d
# ---------------------------------------------------------------------------

class TestPathsD:
    def test_render_one_path_per_line(self):
        assert _render_paths_d(["/usr/local/bin", "/opt/bin"]) == "/usr/local/bin\n/opt/bin\n"

    def test_render_empty_list(self):
        assert _render_paths_d([]) == ""

    def test_render_skips_blank_entries(self):
        assert _render_paths_d(["/a", "", "/b"]) == "/a\n/b\n"

    def test_read_skips_blank_lines(self, tmp_path):
        p = tmp_path / "envedit"
        p.write_text("/a\n\n/b\n")
        with patch("envedit.core.platform_macos._SYSTEM_PATHS_D", p):
            assert _read_paths_d() == ["/a", "/b"]

    def test_read_returns_empty_when_missing(self, tmp_path):
        with patch("envedit.core.platform_macos._SYSTEM_PATHS_D", tmp_path / "nope"):
            assert _read_paths_d() == []


# ---------------------------------------------------------------------------
# _launchctl_setenv_live
# ---------------------------------------------------------------------------

class TestLaunchctlSetenvLive:
    def test_setenv_for_value(self):
        with patch("envedit.core.platform_macos.subprocess.run") as run:
            _launchctl_setenv_live({"FOO": "bar"})
        run.assert_called_once_with(
            ["launchctl", "setenv", "FOO", "bar"],
            check=False,
            capture_output=True,
        )

    def test_unsetenv_for_none(self):
        with patch("envedit.core.platform_macos.subprocess.run") as run:
            _launchctl_setenv_live({"FOO": None})
        run.assert_called_once_with(
            ["launchctl", "unsetenv", "FOO"],
            check=False,
            capture_output=True,
        )

    def test_handles_multiple_changes(self):
        with patch("envedit.core.platform_macos.subprocess.run") as run:
            _launchctl_setenv_live({"A": "1", "B": None})
        assert run.call_count == 2

    def test_swallows_oserror(self):
        # If launchctl isn't on PATH for some reason, don't crash the apply.
        with patch(
            "envedit.core.platform_macos.subprocess.run",
            side_effect=OSError,
        ):
            _launchctl_setenv_live({"FOO": "bar"})  # must not raise


# ---------------------------------------------------------------------------
# _update_environ
# ---------------------------------------------------------------------------

class TestUpdateEnviron:
    def test_sets_value(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENVEDIT_TEST_VAR", None)
            _update_environ({"ENVEDIT_TEST_VAR": "x"})
            assert os.environ["ENVEDIT_TEST_VAR"] == "x"

    def test_deletes_on_none(self):
        with patch.dict(os.environ, {"ENVEDIT_TEST_VAR": "x"}, clear=False):
            _update_environ({"ENVEDIT_TEST_VAR": None})
            assert "ENVEDIT_TEST_VAR" not in os.environ

    def test_delete_missing_is_noop(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENVEDIT_MISSING_VAR", None)
            _update_environ({"ENVEDIT_MISSING_VAR": None})  # must not raise


# ---------------------------------------------------------------------------
# MacOSBackend.apply_user_vars
# ---------------------------------------------------------------------------

class TestMacOSBackendApplyUserVars:
    def test_writes_env_sh_plist_and_calls_launchctl(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        plist_path = tmp_path / "agent.plist"
        backend = MacOSBackend()
        # patch.dict restores os.environ on exit, so the in-process update
        # assertion has to run INSIDE the with block.
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"), \
             patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch("envedit.core.platform_macos.subprocess.run") as run, \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FOO", None)
            backend.apply_user_vars({"FOO": "bar"})

            assert "export FOO='bar'" in envedit_sh.read_text()
            assert _read_plist_env_vars(plist_path) == {"FOO": "bar"}
            run.assert_any_call(
                ["launchctl", "setenv", "FOO", "bar"],
                check=False,
                capture_output=True,
            )
            assert os.environ.get("FOO") == "bar"

    def test_delete_unsets_in_all_three_places(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        plist_path = tmp_path / "agent.plist"
        from envedit.core.platform_unix import _write_env_sh, _parse_shell_assigns
        _write_env_sh(envedit_sh, {"FOO": "bar", "KEEP": "ok"})
        backend = MacOSBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"), \
             patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch("envedit.core.platform_macos.subprocess.run") as run, \
             patch.dict(os.environ, {"FOO": "bar"}, clear=False):
            backend.apply_user_vars({"FOO": None})

            env_after = _parse_shell_assigns(envedit_sh.read_text())
            assert "FOO" not in env_after
            assert env_after["KEEP"] == "ok"
            assert _read_plist_env_vars(plist_path) == {"KEEP": "ok"}
            run.assert_any_call(
                ["launchctl", "unsetenv", "FOO"],
                check=False,
                capture_output=True,
            )
            assert "FOO" not in os.environ

    def test_apply_user_path_writes_plist_path_key(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        plist_path = tmp_path / "agent.plist"
        backend = MacOSBackend()
        # patch.dict so _update_environ doesn't permanently overwrite the real
        # PATH (which would break subprocess lookups in later tests).
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"), \
             patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch("envedit.core.platform_macos.subprocess.run"), \
             patch.dict(os.environ, {}, clear=False):
            backend.apply_user_path(["/usr/local/bin", "/opt/bin"])

            env = _read_plist_env_vars(plist_path)
            assert env["PATH"] == os.pathsep.join(["/usr/local/bin", "/opt/bin"])


# ---------------------------------------------------------------------------
# MacOSBackend.get_user_vars / get_user_path
# ---------------------------------------------------------------------------

class TestMacOSBackendReads:
    def test_get_user_vars_prefers_plist_over_env_sh(self, tmp_path):
        # Plist is the canonical source of truth on macOS — env.sh is only
        # the fallback for legacy / pre-macOS-backend state.
        envedit_sh = tmp_path / "env.sh"
        plist_path = tmp_path / "agent.plist"
        from envedit.core.platform_unix import _write_env_sh
        _write_env_sh(envedit_sh, {"COLLIDE": "from_envsh"})
        plist_path.write_bytes(_render_plist("x", {"COLLIDE": "from_plist"}))
        backend = MacOSBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch.dict(os.environ, {}, clear=True):
            result = backend.get_user_vars()
        assert result["COLLIDE"] == "from_plist"

    def test_get_user_vars_falls_back_to_env_sh(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        from envedit.core.platform_unix import _write_env_sh
        _write_env_sh(envedit_sh, {"LEGACY": "value"})
        backend = MacOSBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_macos._USER_AGENT_PLIST", tmp_path / "missing.plist"), \
             patch.dict(os.environ, {}, clear=True):
            result = backend.get_user_vars()
        assert result["LEGACY"] == "value"

    def test_get_user_vars_overlays_os_environ(self, tmp_path):
        plist_path = tmp_path / "a.plist"
        plist_path.write_bytes(_render_plist("x", {"FOO": "from_plist"}))
        backend = MacOSBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", tmp_path / "no.sh"), \
             patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch.dict(os.environ, {"FOO": "from_environ"}, clear=False):
            result = backend.get_user_vars()
        assert result["FOO"] == "from_environ"

    def test_get_user_path_reads_plist(self, tmp_path):
        plist_path = tmp_path / "a.plist"
        plist_path.write_bytes(
            _render_plist("x", {"PATH": os.pathsep.join(["/a", "/b"])})
        )
        backend = MacOSBackend()
        with patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch("envedit.core.platform_unix._ENVEDIT_SH", tmp_path / "no.sh"):
            result = backend.get_user_path()
        assert result == ["/a", "/b"]

    def test_get_user_path_inherit_sentinel_when_no_path(self, tmp_path):
        plist_path = tmp_path / "a.plist"
        plist_path.write_bytes(_render_plist("x", {"FOO": "bar"}))
        backend = MacOSBackend()
        with patch("envedit.core.platform_macos._USER_AGENT_PLIST", plist_path), \
             patch("envedit.core.platform_unix._ENVEDIT_SH", tmp_path / "no.sh"):
            result = backend.get_user_path()
        assert result == ["$PATH"]


# ---------------------------------------------------------------------------
# MacOSBackend.apply_system_vars / apply_system_path
# ---------------------------------------------------------------------------

class TestMacOSBackendApplySystem:
    def test_elevated_writes_plist_and_paths_d_directly(self, tmp_path):
        # When already root, _apply_system_files runs the shell command via
        # sh directly (no osascript) and writes both files.
        plist_path = tmp_path / "daemon.plist"
        paths_path = tmp_path / "paths.envedit"
        backend = MacOSBackend()
        with patch("envedit.core.platform_macos._SYSTEM_DAEMON_PLIST", plist_path), \
             patch("envedit.core.platform_macos._SYSTEM_PATHS_D", paths_path), \
             patch("envedit.core.platform_macos.is_elevated", return_value=True), \
             patch("envedit.core.platform_macos._update_environ"):
            applied_sync = backend.apply_system_vars({"FOO": "bar"})

        assert applied_sync is True
        assert _read_plist_env_vars(plist_path) == {"FOO": "bar"}

    def test_unelevated_uses_osascript_with_admin_privileges(self, tmp_path):
        plist_path = tmp_path / "daemon.plist"
        paths_path = tmp_path / "paths.envedit"
        backend = MacOSBackend()
        with patch("envedit.core.platform_macos._SYSTEM_DAEMON_PLIST", plist_path), \
             patch("envedit.core.platform_macos._SYSTEM_PATHS_D", paths_path), \
             patch("envedit.core.platform_macos.is_elevated", return_value=False), \
             patch("envedit.core.platform_macos.subprocess.run") as run:
            applied_sync = backend.apply_system_vars({"FOO": "bar"})

        # No on_complete callback → synchronous osascript call.
        assert applied_sync is True
        run.assert_called_once()
        argv = run.call_args.args[0]
        assert argv[0] == "osascript"
        assert argv[1] == "-e"
        assert "administrator privileges" in argv[2]

    def test_async_path_uses_background_thread(self, tmp_path):
        # When on_complete is provided, the elevation prompt is dispatched to
        # a worker thread so the Qt event loop stays responsive. The function
        # returns False to tell the controller it's pending.
        import threading
        plist_path = tmp_path / "daemon.plist"
        paths_path = tmp_path / "paths.envedit"
        backend = MacOSBackend()
        done = threading.Event()
        results = {}

        def on_complete(timed_out):
            results["timed_out"] = timed_out
            done.set()

        with patch("envedit.core.platform_macos._SYSTEM_DAEMON_PLIST", plist_path), \
             patch("envedit.core.platform_macos._SYSTEM_PATHS_D", paths_path), \
             patch("envedit.core.platform_macos.is_elevated", return_value=False), \
             patch("envedit.core.platform_macos.subprocess.run"):
            ret = backend.apply_system_vars({"FOO": "bar"}, on_complete=on_complete)

        assert ret is False
        # Wait for the background thread to call our callback.
        assert done.wait(timeout=5), "on_complete was not called in time"
        assert results["timed_out"] is False

    def test_async_path_reports_timed_out_on_failure(self, tmp_path):
        import threading
        plist_path = tmp_path / "daemon.plist"
        paths_path = tmp_path / "paths.envedit"
        backend = MacOSBackend()
        done = threading.Event()
        results = {}

        def on_complete(timed_out):
            results["timed_out"] = timed_out
            done.set()

        with patch("envedit.core.platform_macos._SYSTEM_DAEMON_PLIST", plist_path), \
             patch("envedit.core.platform_macos._SYSTEM_PATHS_D", paths_path), \
             patch("envedit.core.platform_macos.is_elevated", return_value=False), \
             patch(
                 "envedit.core.platform_macos.subprocess.run",
                 side_effect=Exception("user cancelled prompt"),
             ):
            backend.apply_system_vars({"FOO": "bar"}, on_complete=on_complete)

        assert done.wait(timeout=5)
        assert results["timed_out"] is True

    def test_apply_system_path_writes_paths_d_content(self, tmp_path):
        plist_path = tmp_path / "daemon.plist"
        paths_path = tmp_path / "paths.envedit"
        backend = MacOSBackend()
        with patch("envedit.core.platform_macos._SYSTEM_DAEMON_PLIST", plist_path), \
             patch("envedit.core.platform_macos._SYSTEM_PATHS_D", paths_path), \
             patch("envedit.core.platform_macos.is_elevated", return_value=True), \
             patch("envedit.core.platform_macos._update_environ"):
            backend.apply_system_path(["/usr/local/bin", "/opt/bin"])
        assert paths_path.read_text() == "/usr/local/bin\n/opt/bin\n"
        # Daemon plist also tracks PATH for parity with reads.
        env = _read_plist_env_vars(plist_path)
        assert env["PATH"] == os.pathsep.join(["/usr/local/bin", "/opt/bin"])

    def test_shell_cmd_embeds_content_as_base64(self, tmp_path):
        # Regression guard mirroring test_unelevated_embeds_content_as_base64
        # in test_unix_backend.py — the plist + paths content must travel
        # inside the elevated argv as base64, never via a user-writable
        # intermediate temp file (TOCTOU vector).
        import base64
        plist_path = tmp_path / "daemon.plist"
        paths_path = tmp_path / "paths.envedit"
        backend = MacOSBackend()
        with patch("envedit.core.platform_macos._SYSTEM_DAEMON_PLIST", plist_path), \
             patch("envedit.core.platform_macos._SYSTEM_PATHS_D", paths_path), \
             patch("envedit.core.platform_macos.is_elevated", return_value=False), \
             patch("envedit.core.platform_macos.subprocess.run") as run:
            backend.apply_system_path(["/usr/local/bin"])

        # osascript -e <script> — the script is a JSON-quoted shell command.
        script_arg = run.call_args.args[0][2]
        # The base64 of "/usr/local/bin\n" must appear in the script.
        expected_b64 = base64.b64encode(b"/usr/local/bin\n").decode("ascii")
        assert expected_b64 in script_arg


# ---------------------------------------------------------------------------
# get_backend dispatch
# ---------------------------------------------------------------------------

class TestGetBackendDispatch:
    def test_darwin_returns_macos_backend(self):
        from envedit.core.env_backend import get_backend
        with patch("envedit.core.env_backend.sys.platform", "darwin"):
            backend = get_backend()
        assert isinstance(backend, MacOSBackend)
