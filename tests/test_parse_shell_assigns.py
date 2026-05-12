"""Tests for _parse_shell_assigns() in platform_unix.py."""
import pytest
from envedit.core.platform_unix import _parse_shell_assigns


def test_simple_assignment():
    assert _parse_shell_assigns("FOO=bar") == {"FOO": "bar"}


def test_export_prefix():
    assert _parse_shell_assigns("export FOO=bar") == {"FOO": "bar"}


def test_double_quoted_value():
    assert _parse_shell_assigns('export FOO="hello world"') == {"FOO": "hello world"}


def test_single_quoted_value():
    assert _parse_shell_assigns("export FOO='hello world'") == {"FOO": "hello world"}


def test_empty_value():
    assert _parse_shell_assigns("FOO=") == {"FOO": ""}


def test_empty_double_quoted_value():
    assert _parse_shell_assigns('FOO=""') == {"FOO": ""}


def test_comment_lines_ignored():
    text = "# This is a comment\nFOO=bar"
    assert _parse_shell_assigns(text) == {"FOO": "bar"}


def test_blank_lines_ignored():
    text = "\n\nFOO=bar\n\n"
    assert _parse_shell_assigns(text) == {"FOO": "bar"}


def test_multiple_assignments():
    text = "FOO=bar\nexport BAZ=qux"
    result = _parse_shell_assigns(text)
    assert result == {"FOO": "bar", "BAZ": "qux"}


def test_value_with_equals_sign():
    # Value contains an = character
    result = _parse_shell_assigns("FOO=a=b")
    assert result == {"FOO": "a=b"}


def test_value_with_equals_sign_quoted():
    result = _parse_shell_assigns('FOO="a=b"')
    assert result == {"FOO": "a=b"}


def test_underscore_in_name():
    assert _parse_shell_assigns("MY_VAR=value") == {"MY_VAR": "value"}


def test_name_starting_with_underscore():
    assert _parse_shell_assigns("_VAR=value") == {"_VAR": "value"}


def test_numeric_suffix_in_name():
    assert _parse_shell_assigns("VAR2=value") == {"VAR2": "value"}


def test_name_starting_with_digit_ignored():
    # Variable names cannot start with a digit
    result = _parse_shell_assigns("2BAD=value")
    assert result == {}


def test_path_style_value():
    result = _parse_shell_assigns('export PATH="/usr/bin:/bin"')
    assert result == {"PATH": "/usr/bin:/bin"}


def test_last_assignment_wins():
    text = "FOO=first\nFOO=second"
    assert _parse_shell_assigns(text) == {"FOO": "second"}


def test_empty_string():
    assert _parse_shell_assigns("") == {}


def test_only_comments():
    assert _parse_shell_assigns("# comment\n# another") == {}


def test_export_with_extra_spaces():
    # "export  FOO=bar" — double space, regex uses \s+ so this should work
    result = _parse_shell_assigns("export  FOO=bar")
    assert result == {"FOO": "bar"}


def test_value_with_dollar():
    result = _parse_shell_assigns("FOO=$HOME/bin")
    assert result == {"FOO": "$HOME/bin"}


def test_quoted_value_with_dollar():
    result = _parse_shell_assigns('FOO="$HOME/bin"')
    assert result == {"FOO": "$HOME/bin"}


def test_double_quoted_unescapes_escaped_quote():
    # _format_env_sh writes:   export FOO="say \"hi\""
    # which represents the value:   say "hi"
    assert _parse_shell_assigns(r'FOO="say \"hi\""') == {"FOO": 'say "hi"'}


def test_double_quoted_unescapes_escaped_backslash():
    # _format_env_sh writes:   export WIN="C:\\Users"
    # which represents the value:   C:\Users
    assert _parse_shell_assigns(r'WIN="C:\\Users"') == {"WIN": r"C:\Users"}


def test_double_quoted_roundtrip_with_specials():
    from envedit.core.platform_unix import _format_env_sh
    original = {"FOO": 'say "hi"', "WIN": r"C:\Users\test", "MIX": r'a\"b'}
    text = _format_env_sh(original)
    assert _parse_shell_assigns(text) == original


def test_single_quoted_does_not_unescape():
    # Single-quoted shell strings are literal — \" is two characters, not one.
    assert _parse_shell_assigns(r"FOO='a\"b'") == {"FOO": r'a\"b'}
