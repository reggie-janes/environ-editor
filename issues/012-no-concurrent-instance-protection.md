# 012 — Two EnvEdit instances can clobber each other's writes

**Category:** Race condition
**Severity:** Low (rare scenario, but data loss is silent)

## Location

`envedit/core/platform_unix.py`, `apply_user_vars` (lines 106-117) and
`_write_env_sh` (lines 155-162)

## Problem

`_write_env_sh` is atomic in the sense that the rename can't leave a
half-written file (POSIX `rename(2)`). But there is no lock around the
*read-modify-write* sequence in `apply_user_vars`:

```python
existing = {}
if _ENVEDIT_SH.is_file():
    existing = _parse_shell_assigns(_ENVEDIT_SH.read_text(...))
for key, val in changes.items():
    if val is None:
        existing.pop(key, None)
    else:
        existing[key] = val
_write_env_sh(_ENVEDIT_SH, existing)
```

If two EnvEdit instances are open at once and both click Apply at roughly
the same time:

1. Both read the file's current contents.
2. Each applies its own pending changes to its in-memory copy.
3. Both call `_write_env_sh`. The later writer wins, and the earlier
   writer's changes (the ones it just told the user it had saved) are
   silently lost.

Same shape on Windows: two `winreg.SetValueEx` calls happen one after the
other; neither sees the other's writes since each EnvEdit's UI was
populated from `_read_hkcu()` minutes ago.

The Diff dialog showing "what will be applied" reflects the in-memory
delta, not what's actually different from the file *right now*, so the
user is not warned about the conflict.

## Reproduction

1. Open EnvEdit. Add `A=1`. Don't Apply yet.
2. In a second terminal: `gsettings set ... ` — no wait, just open a
   second EnvEdit. Add `B=2`. Click Apply in instance 2.
3. Click Apply in instance 1.
4. Read `~/.config/envedit/env.sh` — it contains `A=1` but not `B=2`.

## Suggested fix

Two levels of fix, pick one:

1. **Advisory locking on the read-modify-write.** Use `fcntl.flock` on
   `~/.config/envedit/env.sh.lock` around the read+write block in
   `apply_user_vars`. On Windows, use `msvcrt.locking` on a sentinel file
   under `%LOCALAPPDATA%`. Mismatched locking models cross-platform but
   straightforward each side.

2. **Single-instance enforcement.** On startup, take a process-wide lock
   (`QtSingleApplication`-style — `QLockFile` ships with Qt). If another
   instance is already running, raise it instead of starting a new one.
   This sidesteps the whole class of conflicts at the cost of being
   user-visible.

For an env-var editor specifically, #2 is the simpler answer and matches
how regedit / "Edit environment variables" behave.
