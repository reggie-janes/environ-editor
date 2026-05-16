# 007 — After renaming A → B, renaming B back to A is refused as "already exists"

**Category:** Bug / UX
**Severity:** Low (recoverable via Reload)

## Location

`envedit/models/env_var_model.py`, `editVariable` lines 91-126

## Problem

When the user renames an existing (non-new) variable `A` to `B`,
`editVariable` does this:

```python
self._pending[orig_name] = None        # stage deletion of A
new_row = {"name": name, "value": ""}  # add B as a new pending row
self._rows.append(new_row)
self._by_name[name] = new_row
self._pending[name] = value
self._new_names.add(name)
```

`A` is still in `self._rows` and `self._by_name` — its `_pending[A] = None`
marks it as a soft-delete. The row stays visible (greyed out / red).

Now the user changes their mind and tries to rename `B` back to `A` in the
table. `editVariable` checks at line 101:

```python
if name in self._by_name:
    self.errorOccurred.emit(f"A variable named '{name}' already exists.")
    return
```

`A` is still in `_by_name`, so the rename is refused — even though `A` is
pending-deleted and the user's clear intent is to undo the rename.

Workarounds: click Reload (loses *all* pending edits), or click Restore on
the `A` row and then delete the `B` row. Neither is obvious.

## Suggested fix

Allow rename-to-pending-deleted: if `name in self._by_name` *and*
`self._pending.get(name) is None`, treat it like a restore — i.e.:

1. Clear `_pending[name]` (undelete A).
2. Stage a value edit on A if `value != original_A`.
3. Remove the pending-add of B (since `B` is just being abandoned).

This is symmetric with the existing `restoreVariable` slot.

Same issue applies in `addVariable` (line 80) — adding a variable whose
name collides with a pending-deleted slot currently falls through to
`_stage` on the soft-deleted row, leaving the deletion in place but
overwriting the value. That probably isn't what the user wants either.
