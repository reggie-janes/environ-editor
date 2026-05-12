# Bug: `request_elevation_and_apply` doesn't call `on_complete` on macOS/Linux

**Severity:** Medium (latent — function currently only called from Windows backend)  
**File:** `envedit/core/privilege.py`

## Summary

`request_elevation_and_apply` accepts an `on_complete` callback that `AppController`
uses to clear `isBusy` after the elevated child exits. Only the **Windows** path
spawns a background thread that calls `on_complete`. The **macOS** and **Linux**
paths run `subprocess.run(...)` (blocking) and then return `True` — they never
call `on_complete`.

## Affected code

macOS path (line ~115–122):
```python
elif sys.platform == "darwin":
    ...
    subprocess.run(["osascript", "-e", script], check=True)
    return True        # ← on_complete is silently ignored
```

Linux path (line ~124–139):
```python
else:
    subprocess.run([tool, sys.executable, ...], check=True)
    return True        # ← same
```

Windows path (line ~93–106) correctly does:
```python
if on_complete and hProcess:
    threading.Thread(target=_wait_and_notify, daemon=True).start()
```

## Why it doesn't bite today

`platform_unix.py`'s `apply_system_vars` / `apply_system_path` use `_write_as_root`
directly rather than `request_elevation_and_apply`, so the macOS/Linux paths in
`privilege.py` are dead code for the current callers. `app_controller.py` only
sets `isBusy = True` when `apply_system_vars` returns `False`, which only happens
on Windows.

## Risk

If `platform_unix.py` is ever changed to use `request_elevation_and_apply` for a
cleaner macOS experience (the osascript path shows a proper password dialog),
`isBusy` would be set to `True` and never cleared, leaving the UI permanently
showing a busy spinner with the Apply button disabled.

## Fix sketch

macOS and Linux paths should call `on_complete(timed_out=False)` before returning
`True`, or just not set `isBusy` at all for paths that complete synchronously
(caller can check the return value).
