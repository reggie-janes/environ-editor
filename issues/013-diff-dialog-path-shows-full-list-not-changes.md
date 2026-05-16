# 013 — The PATH Diff dialog shows the entire post-apply list, not the changes

**Category:** UX / misleading affordance
**Severity:** Low

## Location

`envedit/controllers/app_controller.py`, `_path_diff` lines 234-236

```python
@staticmethod
def _path_diff(model: PathModel) -> str:
    return "\n".join(f"  {i+1}.  {e}" for i, e in enumerate(model.getEntries()))
```

## Problem

For the variable tabs, `_var_diff` correctly emits per-change lines:

```
  SET    FOO = bar
  DELETE BAZ
```

For the PATH tabs, the "diff" is just `getEntries()` — i.e. the entire
final list. The dialog is titled **"Pending Changes"** and says "the
following changes will be applied", but the user sees a flat numbered
list of every path entry with no indication of what is being added,
removed, or moved.

If the user has a 40-entry PATH and they reordered the top two, the
dialog shows 40 unchanged-looking rows. They have no way to confirm what
they're about to commit. They can't tell from the dialog whether the
operation is a small edit or a complete wipe (which would matter if
issue 003 ever bites).

## Suggested fix

Diff the model's current state against `model._original` and emit a
proper +/-/move listing. The `PathModel` already tracks
`original` per entry and `_dirty`; the controller has direct access to
the snapshot:

```
  ADD    /opt/new/bin                 (was new at position 3)
  REMOVE /opt/old/bin                 (was at position 7)
  MOVE   /usr/local/bin  : 12 → 1
  EDIT   /home/me/bin → /home/me/bin2 (position 4)
```

The two helpers — diff for vars and diff for paths — should live next to
the corresponding model and produce structured output (`list[Change]`)
that the QML side renders, instead of the current ad-hoc strings.
