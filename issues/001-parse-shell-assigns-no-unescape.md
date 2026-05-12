# Bug: `_parse_shell_assigns` doesn't unescape quoted values

**Severity:** High  
**File:** `envedit/core/platform_unix.py`  
**Functions:** `_parse_shell_assigns`, `_format_env_sh`

## Summary

`_format_env_sh` escapes `"` as `\"` and `\` as `\\` when writing values.
`_parse_shell_assigns` strips the outer quotes but **never unescapes** the contents.
The roundtrip is broken for any value containing `"` or `\`.

## Reproduction

```python
from envedit.core.platform_unix import _write_env_sh, _parse_shell_assigns
import tempfile, pathlib

tmp = pathlib.Path(tempfile.mktemp())
original = {"FOO": 'hello "world"', "WIN": r"C:\Users\test"}
_write_env_sh(tmp, original)
result = _parse_shell_assigns(tmp.read_text())
assert result == original   # FAILS
# result == {'FOO': 'hello \\"world\\"', 'WIN': 'C:\\\\Users\\\\test'}
```

## Root cause

`_format_env_sh` (line ~139–143):
```python
escaped = v.replace("\\", "\\\\").replace('"', '\\"')
lines.append(f'export {k}="{escaped}"\n')
```

`_parse_shell_assigns` (line ~30–33) only strips outer quotes:
```python
if (val.startswith('"') and val.endswith('"')) or \
   (val.startswith("'") and val.endswith("'")):
    val = val[1:-1]   # strips delimiters but NOT escape sequences inside
```

Missing unescape step:
```python
val = val[1:-1]
val = val.replace('\\"', '"').replace("\\\\", "\\")   # needed but absent
```

## Impact

- Affects variables set via EnvEdit that contain `"` or `\` in their values.
- On Unix, `apply_user_vars` reads the file before writing, so a second apply
  would see the already-corrupted escaped value and double-escape it again on
  each subsequent write cycle.
- Masked for variables already present in `os.environ` at reload time, because
  `get_user_vars()` merges `os.environ` over the file (process env wins).
  Only newly-added variables or those not yet sourced into the session are
  affected.

## Missing test coverage

`test_parse_shell_assigns.py` has no test for values with escaped quotes or
backslashes. `test_unix_backend.py`'s roundtrip test only uses plain ASCII
values without special characters.
