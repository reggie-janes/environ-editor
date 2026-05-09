"""Tests for UnixBackend and related helpers in platform_unix.py."""
import os
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from envedit.core.platform_unix import (
    UnixBackend,
    _write_env_sh,
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
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "bar", "BAZ": "qux"})
        content = dest.read_text()
        assert 'export FOO="bar"' in content
        assert 'export BAZ="qux"' in content

    def test_sorts_vars_alphabetically(self, tmp_path):
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"ZZZ": "last", "AAA": "first"})
        content = dest.read_text()
        assert content.index("AAA") < content.index("ZZZ")

    def test_escapes_double_quotes_in_value(self, tmp_path):
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": 'say "hello"'})
        content = dest.read_text()
        assert r'export FOO="say \"hello\""' in content

    def test_escapes_backslash_in_value(self, tmp_path):
        dest = tmp_path / "env.sh"
        _write_env_sh(dest, {"FOO": "a\\b"})
        content = dest.read_text()
        assert 'export FOO="a\\\\b"' in content

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
    def test_get_user_path_splits_on_pathsep(self):
        backend = UnixBackend()
        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin:/usr/local/bin"}, clear=False):
            result = backend.get_user_path()
        assert "/usr/bin" in result
        assert "/bin" in result

    def test_get_user_path_empty_segments_removed(self):
        backend = UnixBackend()
        with patch.dict(os.environ, {"PATH": "/usr/bin::/bin"}, clear=False):
            result = backend.get_user_path()
        assert "" not in result

    def test_get_user_path_empty_PATH(self):
        backend = UnixBackend()
        with patch.dict(os.environ, {"PATH": ""}, clear=False):
            result = backend.get_user_path()
        assert result == []

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
            with patch("envedit.core.platform_unix._read_user_shell_vars", return_value={}):
                result = backend.get_user_vars()
        assert "PATH" not in result
        assert "MYVAR" in result

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
