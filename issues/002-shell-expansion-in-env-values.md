# 002 — Values in `env.sh` are double-quoted, so `$`, backticks and `$(…)` are interpreted on source

**Category:** Correctness (data integrity), low-grade security
**Severity:** High (silent data loss / arbitrary command execution at next login)

## Location

`envedit/core/platform_unix.py`, `_format_env_sh` (lines 147-152):

```python
def _format_env_sh(vars_: dict[str, str]) -> str:
    lines = ["# Managed by EnvEdit — do not edit manually\n"]
    for k, v in sorted(vars_.items()):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'export {k}="{escaped}"\n')
    return "".join(lines)
```

## Problem

The writer escapes backslashes and double-quotes, but not `$` or backticks.
Inside a double-quoted shell string, those are still active:

| User-entered value | Written to env.sh | What shell sees on source |
|---|---|---|
| `$(uname)` | `export FOO="$(uname)"` | `FOO=Linux` (command runs) |
| `` `id` `` | `` export FOO="`id`" `` | `FOO=uid=1000(...)` (command runs) |
| `$HOME/bin` | `export FOO="$HOME/bin"` | `FOO=/home/user/bin` |
| `100%` | `export FOO="100%"` | `FOO=100%` (fine) |

Concrete consequences:

1. **Silent value mutation.** A user typing the literal `$(uname)` into the
   value column sees it saved correctly once. On the next login the shell
   evaluates it, `os.environ` now holds `Linux`, the EnvEdit UI loads
   `os.environ` (which wins over the file per `get_user_vars`), and on the
   next Apply the file is rewritten with `export FOO="Linux"`. The original
   intent is lost permanently, with no warning.

2. **Code execution on login.** Any value containing `$(…)` or `` `…` `` is
   executed by the user's login shell every time. If EnvEdit is used on the
   System tab (via `pkexec`/`sudo`), the payload is written to
   `/etc/profile.d/envedit.sh` and runs as **every user** on the system at
   login — an admin who carelessly pastes a value with `$(…)` (e.g. from a
   shell command they were tinkering with) leaks/executes for every user.

3. **Round-trip inconsistency.** `_parse_shell_assigns` already treats the
   value as a literal — it reverses only the `\"` and `\\` escapes. So
   write→read→write is *not* a fixed point when `$` is present.

## Suggested fix

Single-quote the value instead of double-quoting. POSIX single-quoted strings
have no escape processing at all — the only character you cannot include is
`'` itself, which can be emitted as `'\''` (close, escaped, reopen):

```python
escaped = v.replace("'", "'\\''")
lines.append(f"export {k}='{escaped}'\n")
```

`_parse_shell_assigns` already handles the single-quoted branch (line 39-41
of `platform_unix.py`); it would just need to apply the inverse `'\''` →
`'` substitution. Update the round-trip tests in `test_unix_backend.py`
accordingly.
