"""Tests for UnixBackend and related helpers in platform_unix.py."""
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from envedit.core.platform_unix import (
    UnixBackend,
    _write_env_sh,
    _write_as_root,
    _ensure_sourced_in_profile,
    _parse_shell_assigns,
    _ENVEDIT_SH,
)


# ---------------------------------------------------------------------------
# _write_env_sh
# ---------------------------------------------------------------------------

class TestWriteEnvSh:
    def test_creates_file(self, tmp_path):
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "bar"})
        assert dest.exists()

    def test_exports_all_vars(self, tmp_path):
        # Issue 002: values are single-quoted so `$`, backticks, and `$(...)`
        # round-trip literally.
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "bar", "BAZ": "qux"})
        content = dest.read_text()
        assert "export FOO='bar'" in content
        assert "export BAZ='qux'" in content

    def test_sorts_vars_alphabetically(self, tmp_path):
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"ZZZ": "last", "AAA": "first"})
        content = dest.read_text()
        assert content.index("AAA") < content.index("ZZZ")

    def test_double_quotes_in_value_are_literal(self, tmp_path):
        # Single-quoted POSIX strings have no escape processing, so " is
        # emitted verbatim with no backslash.
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": 'say "hello"'})
        content = dest.read_text()
        assert "export FOO='say \"hello\"'" in content

    def test_dollar_in_value_is_literal(self, tmp_path):
        # Regression test for issue 002 — a literal `$(uname)` must not be
        # interpreted by the shell on source. Single-quoting guarantees that.
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "$(uname)"})
        content = dest.read_text()
        assert "export FOO='$(uname)'" in content

    def test_single_quote_in_value_is_escaped(self, tmp_path):
        # The only character a POSIX single-quoted string cannot contain is
        # `'`. The writer emits it as `'\''` (close, escaped, reopen).
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "it's"})
        content = dest.read_text()
        assert "export FOO='it'\\''s'" in content

    def test_backslash_in_value_is_literal(self, tmp_path):
        # Single quotes mean a backslash is just a backslash — no escaping.
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "a\\b"})
        content = dest.read_text()
        assert "export FOO='a\\b'" in content

    def test_roundtrip(self, tmp_path):
        dest = tmp_path / "env.sh"
        original = {"FOO": "bar", "PATH2": "/usr/bin:/bin"}
        _write_env_sh(dest, original)
        result = _parse_shell_assigns(dest.read_text())
        assert result == original

    def test_empty_vars_writes_header_only(self, tmp_path):
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {})
        content = dest.read_text()
        assert "Managed by EnvEdit" in content
        # No export lines
        assert "export" not in content


# ---------------------------------------------------------------------------
# _write_as_root
# ---------------------------------------------------------------------------

class TestWriteAsRoot:
    def test_elevated_writes_directly_without_subprocess(self, tmp_path):
        dest = tmp_path / "envedit.sh"
        with patch("envedit.core.platform_unix.is_elevated", return_value=True), \
             patch("envedit.core.platform_unix.subprocess.run") as run:
            _write_as_root(dest, "payload\n")
        assert dest.read_text() == "payload\n"
        run.assert_not_called()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits don't apply to Windows ACLs")
    def test_elevated_sets_mode_644(self, tmp_path):
        dest = tmp_path / "envedit.sh"
        with patch("envedit.core.platform_unix.is_elevated", return_value=True):
            _write_as_root(dest, "payload\n")
        # Lower 9 mode bits should be rw-r--r-- regardless of umask.
        assert (dest.stat().st_mode & 0o777) == 0o644

    def test_elevated_overwrites_existing(self, tmp_path):
        dest = tmp_path / "envedit.sh"
        dest.write_text("old\n")
        with patch("envedit.core.platform_unix.is_elevated", return_value=True):
            _write_as_root(dest, "new\n")
        assert dest.read_text() == "new\n"

    def test_unelevated_linux_uses_pkexec_with_sh(self, tmp_path):
        dest = tmp_path / "envedit.sh"
        with patch("envedit.core.platform_unix.is_elevated", return_value=False), \
             patch("envedit.core.platform_unix.sys.platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/pkexec"), \
             patch("envedit.core.platform_unix.subprocess.run") as run:
            _write_as_root(dest, "payload\n")
        run.assert_called_once()
        argv = run.call_args.args[0]
        assert argv[0] == "pkexec"
        assert argv[1] == "sh"
        assert argv[2] == "-c"

    def test_unelevated_falls_back_to_sudo(self, tmp_path):
        dest = tmp_path / "envedit.sh"
        with patch("envedit.core.platform_unix.is_elevated", return_value=False), \
             patch("envedit.core.platform_unix.sys.platform", "linux"), \
             patch("shutil.which", return_value=None), \
             patch("envedit.core.platform_unix.subprocess.run") as run:
            _write_as_root(dest, "payload\n")
        assert run.call_args.args[0][0] == "sudo"

    def test_unelevated_embeds_content_as_base64(self, tmp_path):
        # Regression test for the temp-file TOCTOU (issue 006). The content
        # must be embedded in the shell command itself — base64 inside argv —
        # not passed through a user-writable file path that the elevated
        # tool then reads.
        import base64
        dest = tmp_path / "envedit.sh"
        content = 'export FOO="hello\nworld"\n'
        with patch("envedit.core.platform_unix.is_elevated", return_value=False), \
             patch("envedit.core.platform_unix.sys.platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/pkexec"), \
             patch("envedit.core.platform_unix.subprocess.run") as run:
            _write_as_root(dest, content)
        shell_cmd = run.call_args.args[0][3]  # pkexec sh -c <THIS>
        expected_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        assert expected_b64 in shell_cmd
        # Plaintext content must not appear — it is supposed to live only
        # inside the base64 blob.
        assert content not in shell_cmd
        # No envedit-prefixed mktemp/NamedTemporaryFile path should be
        # referenced as the source (that was the old TOCTOU pattern).
        assert "envedit-" not in shell_cmd
        # subprocess.run must not be called with `input=` (would imply
        # piping content; the fix uses base64-in-argv instead).
        assert run.call_args.kwargs.get("input") is None

    def test_unelevated_macos_uses_osascript(self, tmp_path):
        dest = tmp_path / "envedit.sh"
        with patch("envedit.core.platform_unix.is_elevated", return_value=False), \
             patch("envedit.core.platform_unix.sys.platform", "darwin"), \
             patch("envedit.core.platform_unix.subprocess.run") as run:
            _write_as_root(dest, "payload\n")
        argv = run.call_args.args[0]
        assert argv[0] == "osascript"
        assert argv[1] == "-e"
        assert "administrator privileges" in argv[2]


# ---------------------------------------------------------------------------
# _ensure_sourced_in_profile
# ---------------------------------------------------------------------------

class TestEnsureSourcedInProfile:
    def test_appends_source_line_when_absent(self, tmp_path):
        profile = tmp_path / ".profile"
        profile.write_text("# existing content\n")
        envedit_sh = tmp_path / "env.sh"
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix.Path.home", return_value=tmp_path):
            _ensure_sourced_in_profile()
        content = profile.read_text()
        assert str(envedit_sh) in content

    def test_does_not_duplicate_source_line(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        profile = tmp_path / ".profile"
        # The source line contains the path twice ([ -f "..." ] && . "..."),
        # so we count occurrences of the guard prefix '[ -f' instead.
        profile.write_text(f'[ -f "{envedit_sh}" ] && . "{envedit_sh}"\n')
        original_content = profile.read_text()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix.Path.home", return_value=tmp_path):
            _ensure_sourced_in_profile()
        # Content should be identical — no line was appended
        assert profile.read_text() == original_content

    def test_creates_profile_if_missing(self, tmp_path):
        profile = tmp_path / ".profile"
        envedit_sh = tmp_path / "env.sh"
        assert not profile.exists()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix.Path.home", return_value=tmp_path):
            _ensure_sourced_in_profile()
        assert profile.exists()
        assert str(envedit_sh) in profile.read_text()


# ---------------------------------------------------------------------------
# UnixBackend.get_user_path / get_system_path
# ---------------------------------------------------------------------------

class TestUnixBackendPath:
    @pytest.mark.skipif(sys.platform == "win32", reason="os.pathsep differs on Windows")
    def test_get_user_path_splits_on_pathsep(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"PATH": "/usr/bin:/bin:/usr/local/bin"})
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh):
            result = backend.get_user_path()
        assert "/usr/bin" in result
        assert "/bin" in result

    def test_get_user_path_empty_segments_removed(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"PATH": "/usr/bin::/bin"})
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh):
            result = backend.get_user_path()
        assert "" not in result

    def test_get_user_path_surfaces_inherit_sentinel_when_no_file(self, tmp_path):
        # Issue 003: when env.sh has no PATH, get_user_path surfaces a
        # `$PATH` sentinel row so the user's first add appends to, rather
        # than replaces, the inherited PATH on the next login.
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", tmp_path / "missing.sh"):
            result = backend.get_user_path()
        assert result == ["$PATH"]

    def test_get_user_path_does_not_clone_session_PATH(self, tmp_path):
        # When env.sh has no PATH, get_user_path returns just the sentinel
        # even if os.environ['PATH'] is rich. Otherwise the first apply
        # would clone the entire merged session PATH into our managed file.
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"FOO": "bar"})  # no PATH key
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=False):
            result = backend.get_user_path()
        assert result == ["$PATH"]

    @pytest.mark.skipif(sys.platform == "win32", reason="os.pathsep differs on Windows")
    def test_get_system_path_parses_env_file(self, tmp_path):
        env_file = tmp_path / "environment"
        env_file.write_text('PATH="/sysbin:/syslocal"\n')
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._SYSTEM_ENV", env_file), \
             patch("envedit.core.platform_unix._SYSTEM_PROFILE_D", tmp_path / "nonexistent.sh"):
            result = backend.get_system_path()
        assert "/sysbin" in result
        assert "/syslocal" in result


# ---------------------------------------------------------------------------
# UnixBackend.get_user_vars / get_system_vars
# ---------------------------------------------------------------------------

class TestUnixBackendVars:
    def test_get_user_vars_excludes_PATH(self):
        backend = UnixBackend()
        with patch.dict(os.environ, {"PATH": "/usr/bin", "MYVAR": "hello"}, clear=False):
            with patch("envedit.core.platform_unix._read_envedit_vars", return_value={}):
                result = backend.get_user_vars()
        assert "PATH" not in result
        assert "MYVAR" in result

    def test_get_user_vars_environ_wins_over_file(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"COLLIDE": "from_file"})
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch.dict(os.environ, {"COLLIDE": "from_environ"}, clear=False):
            result = backend.get_user_vars()
        assert result["COLLIDE"] == "from_environ"

    def test_get_user_vars_merges_shell_file(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"CUSTOM_VAR": "from_file"})
        backend = UnixBackend()
        # Patch only the candidates to include our tmp file
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh):
            result = backend.get_user_vars()
        assert "CUSTOM_VAR" in result
        assert result["CUSTOM_VAR"] == "from_file"

    def test_get_system_vars_excludes_PATH(self, tmp_path):
        env_file = tmp_path / "environment"
        env_file.write_text('PATH="/usr/bin"\nSYS_VAR="sysval"\n')
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._SYSTEM_ENV", env_file), \
             patch("envedit.core.platform_unix._SYSTEM_PROFILE_D", tmp_path / "nope.sh"):
            result = backend.get_system_vars()
        assert "PATH" not in result
        assert result.get("SYS_VAR") == "sysval"

    def test_get_system_vars_empty_when_no_file(self, tmp_path):
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._SYSTEM_ENV", tmp_path / "nope"), \
             patch("envedit.core.platform_unix._SYSTEM_PROFILE_D", tmp_path / "nope2"):
            result = backend.get_system_vars()
        assert result == {}


# ---------------------------------------------------------------------------
# UnixBackend.apply_user_vars
# ---------------------------------------------------------------------------

class TestUnixBackendApplyUserVars:
    def test_writes_new_var(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_vars({"NEWVAR": "newval"})
        result = _parse_shell_assigns(envedit_sh.read_text())
        assert result["NEWVAR"] == "newval"

    def test_updates_existing_var(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"FOO": "old"})
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_vars({"FOO": "new"})
        result = _parse_shell_assigns(envedit_sh.read_text())
        assert result["FOO"] == "new"

    def test_deletes_var_with_none(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"FOO": "bar", "BAZ": "keep"})
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_vars({"FOO": None})
        result = _parse_shell_assigns(envedit_sh.read_text())
        assert "FOO" not in result
        assert result["BAZ"] == "keep"

    def test_creates_parent_dir_if_missing(self, tmp_path):
        envedit_sh = tmp_path / "deep" / "dir" / "env.sh"
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_vars({"X": "1"})
        assert envedit_sh.exists()

    def test_delete_nonexistent_var_is_noop(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        _write_env_sh(envedit_sh, {"FOO": "bar"})
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_vars({"NONEXISTENT": None})
        result = _parse_shell_assigns(envedit_sh.read_text())
        assert result == {"FOO": "bar"}


# ---------------------------------------------------------------------------
# UnixBackend.apply_user_path
# ---------------------------------------------------------------------------

class TestUnixBackendApplyUserPath:
    @pytest.mark.skipif(sys.platform == "win32", reason="os.pathsep differs on Windows")
    def test_writes_path_joined_by_pathsep(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_path(["/usr/bin", "/bin", "/usr/local/bin"])
        result = _parse_shell_assigns(envedit_sh.read_text())
        assert result["PATH"] == "/usr/bin:/bin:/usr/local/bin"

    def test_empty_list_writes_empty_PATH(self, tmp_path):
        envedit_sh = tmp_path / "env.sh"
        backend = UnixBackend()
        with patch("envedit.core.platform_unix._ENVEDIT_SH", envedit_sh), \
             patch("envedit.core.platform_unix._ensure_sourced_in_profile"):
            backend.apply_user_path([])
        result = _parse_shell_assigns(envedit_sh.read_text())
        assert result["PATH"] == ""


# ---------------------------------------------------------------------------
# UnixBackend.expand_value
# ---------------------------------------------------------------------------

class TestUnixBackendExpandValue:
    def test_expands_env_variable(self):
        backend = UnixBackend()
        with patch.dict(os.environ, {"TESTVAR": "expanded_value"}):
            result = backend.expand_value("$TESTVAR/bin")
        assert result == "expanded_value/bin"

    def test_no_expansion_needed(self):
        backend = UnixBackend()
        result = backend.expand_value("/usr/bin")
        assert result == "/usr/bin"

    def test_unknown_var_left_as_is(self):
        backend = UnixBackend()
        with patch.dict(os.environ, {}, clear=True):
            result = backend.expand_value("$DEFINITELY_NOT_SET_XYZ123")
        # os.path.expandvars leaves unknown vars unexpanded
        assert "$DEFINITELY_NOT_SET_XYZ123" in result
