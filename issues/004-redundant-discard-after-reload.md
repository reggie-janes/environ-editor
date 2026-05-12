# Minor: Redundant `discardChanges()` after `reloadTab()` in QML

**Severity:** Low (harmless no-op, no user-visible effect)  
**Files:** `envedit/qml/components/EnvTable.qml`, `envedit/qml/components/PathTable.qml`

## Summary

Both table components call `discardChanges()` immediately after `reloadTab()`:

```qml
onReloadClicked: { appController.reloadTab(root.tabIndex); root.model.discardChanges() }
```

`reloadTab` calls `model.loadData(new_data)`. Both `EnvVarModel.loadData` and
`PathModel.loadData` already clear all pending state (`_pending`, `_new_names`,
`_dirty`) as part of their contract. The subsequent `discardChanges()` call
operates on an already-clean model, executing a full `_reset()` cycle for no
benefit.

## Evidence

`EnvVarModel.loadData`:
```python
def loadData(self, vars_: dict[str, str]) -> None:
    self._rows = [...]
    self._original_rows = [dict(r) for r in self._rows]
    self._pending.clear()        # ← already cleared
    self._new_names.clear()      # ← already cleared
    self._reset()
```

`PathModel.loadData`:
```python
def loadData(self, entries: list[str]) -> None:
    self._entries = [...]
    self._original = list(entries)
    self._dirty = False           # ← already cleared
    self._refresh_dup_counts()
    self._reset()
```

After `loadData`, `_original_rows` / `_original` holds exactly the newly loaded
data, so `discardChanges()` restores to the same state that just loaded — a
complete no-op.

## Fix

Remove the `root.model.discardChanges()` calls from both table components.
