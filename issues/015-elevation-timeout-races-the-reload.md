# 015 — On Windows elevation timeout, the reload fires before the elevated child has finished writing

**Category:** Race condition
**Severity:** Low (Windows-only, only on the timeout edge case)

## Location

- `envedit/core/privilege.py`, `request_elevation_and_apply` lines 132-140
- `envedit/controllers/app_controller.py`, `_onElevatedApplyDone`
  lines 210-215

```python
ret = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 30000)
ctypes.windll.kernel32.CloseHandle(hProcess)
# Call on_complete regardless of timeout so isBusy always clears.
# If timed out, the reload may show stale data, but that's better
# than a stuck spinner — the elevated child likely hung.
on_complete(timed_out=(ret == WAIT_TIMEOUT))
```

```python
@Slot(int, bool)
def _onElevatedApplyDone(self, idx, timed_out):
    self._is_busy = False
    self.isBusyChanged.emit()
    if timed_out:
        self.errorOccurred.emit("Elevated apply timed out — the process may have hung.")
    self._reload(idx)
```

## Problem

The comment is honest: on timeout, we surface the error and reload
anyway. Two things to flag:

1. **The handle is closed while the child may still be running.**
   `CloseHandle` releases the wait reference, not the process. The
   elevated child keeps running, will eventually finish, and will write
   to HKLM — *after* the reload has already happened. The user sees
   "timed out" and a tab that looks unchanged, then a few seconds later
   the registry has the new values. Closing the EnvEdit window during
   that window leaves a still-running elevated process the user has no
   handle to.

2. **The 30-second timeout is essentially arbitrary.** UAC consent
   dialogs are dismissed by user input — a user looking up their
   password from a manager might genuinely take >30s. The wait should
   either be unbounded (with a "cancel" button on the busy indicator)
   or much longer.

## Suggested fix

- Bump the wait to something less likely to fire on slow consent
  (e.g. 120s), or drop the timeout entirely and add a Cancel control on
  the busy indicator that uses `TerminateProcess` on the elevated child.
- On timeout, do **not** call `_reload(idx)`; instead leave the busy
  indicator on with a note ("still waiting for the elevated process…")
  and either keep waiting on a slower poll, or surface a Cancel button.
- Don't `CloseHandle` until the child has actually exited (or until we
  decide to abort, in which case `TerminateProcess` first).

Bonus: today `errorOccurred` and `_reload` both fire on timeout, so the
user sees an error toast *and* a re-read of stale data. Pick one.
