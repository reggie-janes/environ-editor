# 011 — `UnixBackend.apply_system_path` quietly drops its `on_complete` argument

**Category:** API inconsistency / latent bug
**Severity:** Low today, footgun for later

## Location

`envedit/core/platform_unix.py` lines 140-141:

```python
def apply_system_path(self, entries: list[str], on_complete=None) -> bool:
    return self.apply_system_vars({"PATH": os.pathsep.join(entries)})
```

Compare with the Windows version (`envedit/core/platform_windows.py`
lines 73-74):

```python
def apply_system_path(self, entries: list[str], on_complete=None) -> bool:
    return self.apply_system_vars({"PATH": os.pathsep.join(entries)}, on_complete=on_complete)
```

## Problem

The Unix path accepts an `on_complete` callback (as required by the
`EnvBackend` ABC) but never passes it through to `apply_system_vars`.
Today this is harmless because `UnixBackend.apply_system_vars` also
ignores `on_complete` and runs synchronously — see issue 004. But the
moment issue 004 is fixed (making system applies async to unblock the
GUI), this becomes a real bug: the controller's `_elevatedApplyDone`
signal will fire for system *variable* applies but not for system *PATH*
applies, leaving the spinner stuck and the tab un-reloaded.

This is the kind of paper-cut that's easy to spot in isolation but
disappears under review noise.

## Suggested fix

```python
def apply_system_path(self, entries, on_complete=None) -> bool:
    return self.apply_system_vars(
        {"PATH": os.pathsep.join(entries)},
        on_complete=on_complete,
    )
```

— same as Windows. Even though it's currently a no-op, plug the leak now
so the future async fix doesn't have to remember.
