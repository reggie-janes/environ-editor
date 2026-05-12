# Bug: System writes on macOS use `sudo` without a GUI elevation prompt

**Severity:** Medium (macOS-only, system tabs)  
**File:** `envedit/core/platform_unix.py`  
**Function:** `_write_as_root`

## Summary

`_write_as_root` selects `pkexec` if available, falling back to `sudo`.
On macOS, `pkexec` (a Linux polkit tool) is not available, so `sudo` is used.
`sudo` requires an interactive terminal for the password prompt; running it from
a GUI application without a TTY raises a `subprocess.CalledProcessError` and
surfaces a generic error message to the user with no way to authenticate.

The macOS-appropriate elevation mechanism — `osascript "do shell script ... with
administrator privileges"` — already exists in `privilege.py` but is only wired
up to the `--apply-system-file` child-process flow, not to `_write_as_root`.

## Affected code

```python
def _write_as_root(path: Path, content: str) -> None:
    import tempfile, shutil
    with tempfile.NamedTemporaryFile(...) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        tool = "pkexec" if shutil.which("pkexec") else "sudo"  # pkexec absent on macOS
        subprocess.run(
            [tool, "install", "-m", "644", tmp_path, str(path)],
            check=True,      # raises CalledProcessError on sudo auth failure
        )
```

## Expected behaviour

On macOS, the app should show the OS password sheet (via `osascript` or the
`--apply-system-file` / `request_elevation_and_apply` path) before writing
to `/etc/profile.d/envedit.sh`.

## Fix sketch

Add a macOS branch to `_write_as_root` that uses `osascript`, or — cleaner —
route macOS system writes through `request_elevation_and_apply` (fixing issue
#002 first so `on_complete` is called correctly).
