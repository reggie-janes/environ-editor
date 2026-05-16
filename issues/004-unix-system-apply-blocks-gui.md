# 004 — Applying System tabs on Unix freezes the GUI for the duration of the password prompt

**Category:** UX / threading
**Severity:** Medium

## Location

- `envedit/core/platform_unix.py`, `UnixBackend.apply_system_vars`
  (lines 119-135) and `_write_as_root` (lines 192-238)
- `envedit/controllers/app_controller.py`, `AppController.applyTab`
  (lines 157-176)

## Problem

On Windows the controller has a deliberate async path: `apply_system_vars`
returns `False` to signal "elevated child launched", the controller flips
`_is_busy = True`, the QML toolbar shows a `BusyIndicator`, and the
`_elevatedApplyDone` signal flips it back when the child exits.

On Unix the same code path is **synchronous**:

```python
def apply_system_vars(self, changes, on_complete=None) -> bool:
    ...
    _write_as_root(_SYSTEM_PROFILE_D, content)   # blocks until pkexec returns
    return True
```

`_write_as_root` calls `subprocess.run([...], check=True)` which blocks the
Qt event loop until `pkexec`/`sudo`/`osascript` returns. During that window
(seconds, possibly tens of seconds while the user reads the password
prompt) the entire UI is frozen:

- the window can't be moved or resized
- the busy indicator never appears (the controller sees `applied == True`
  and skips the `_is_busy = True` branch)
- the OS shows the spinning-beachball / "Not Responding" badge

This is also wired contradictorily: `apply_system_vars` accepts an
`on_complete` callback but never uses it on Unix.

## Suggested fix

Make Unix system applies behave like Windows:

1. Spawn `_write_as_root` on a worker thread (e.g. `threading.Thread`
   like `request_elevation_and_apply` already does on Windows).
2. Return `False` so the controller flips `isBusy`.
3. Call `on_complete(timed_out=…)` from the worker thread when
   `subprocess.run` returns.
4. Have the controller's existing `_elevatedApplyDone` slot reload the tab
   on completion.

This also gives a place to surface "user cancelled the password prompt" as
a recoverable error rather than a `CalledProcessError` bubbling up through
`applyTab`'s blanket `except Exception` and showing the raw stderr.
