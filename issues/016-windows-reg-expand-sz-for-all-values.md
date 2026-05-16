# 016 — Windows writes every value as `REG_EXPAND_SZ`, even when no expansion is wanted

**Category:** Correctness / data fidelity
**Severity:** Low

## Location

`envedit/core/platform_windows.py`, `apply_user_vars` line 47 and
`apply_system_vars` line 66:

```python
winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, val)
```

## Problem

`REG_EXPAND_SZ` tells the OS / shells to expand `%VAR%` references in
the value before returning it. That's the right type for things like
`PATH = %SystemRoot%\system32;…`. It is *not* the right type for a
literal value that happens to contain percent signs — e.g.
`COMPLETION_PERCENT = 100%done`, `URL_TEMPLATE = https://x/%user%`.

When the user types `100%done` into the value column:

- Win-EnvEdit writes it as `REG_EXPAND_SZ`.
- Next read (`get_user_vars`) returns `100%done` literally (because
  `winreg.EnumValue` does not expand).
- But when the shell or any process reads the value via
  `ExpandEnvironmentStringsW`, it tries to expand `%done` — and since
  `done` isn't defined, returns `100%done` unchanged. (You got lucky.)
- For `https://x/%user%`, the OS expands `%user%` → the actual username
  → the value the user sees in `%user%` *contexts* (not in EnvEdit) is
  `https://x/jdoe`. Now the user is confused about why their template
  has their own username baked in.

`reg.exe` and the built-in "Edit the system environment variables" UI
both let you choose `REG_SZ` vs `REG_EXPAND_SZ`. EnvEdit always picks
the latter.

This also matters for round-trip fidelity: a value originally written by
something else as `REG_SZ` will be silently upgraded to `REG_EXPAND_SZ`
on the first EnvEdit save, changing semantics for the next reader.

## Suggested fix

Two practical options:

1. **Preserve the original type on read.** Store the per-key type in the
   model alongside the value; reuse it on write. New values written via
   "+ Add" default to `REG_EXPAND_SZ` if they contain `%…%` and `REG_SZ`
   otherwise. (Heuristic, but matches user intent more often than the
   current always-expand behaviour.)

2. **Add a type toggle to the UI** — a small badge / checkbox per row:
   "Expand %VAR%". Power-user oriented; matches what the Windows native
   UI doesn't expose either.

Option 1 is invisible and correct most of the time. Worth doing.
