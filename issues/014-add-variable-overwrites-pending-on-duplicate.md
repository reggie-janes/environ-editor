# 014 — Adding a variable that already exists silently overwrites its pending value with no feedback

**Category:** UX
**Severity:** Low

## Location

`envedit/models/env_var_model.py`, `addVariable` lines 75-89

```python
@Slot(str, str)
def addVariable(self, name: str, value: str) -> None:
    name = name.strip()
    if not name:
        return
    if name in self._by_name:
        self._stage(name, value)   # silently edit the existing row
        return
    ...
```

## Problem

The Add-Variable dialog has no awareness that the name is already in the
model — there is no inline check, no rejection, and no confirmation. If
the user types a name that matches an existing variable and clicks Add:

1. Dialog closes successfully (no error).
2. Existing row's value is replaced with the new value.
3. The user can't see the original anymore (well, until they Reload).
4. If the new value happens to equal the existing one, `_stage` clears
   the pending mark (early-out at line 196: `if value == orig`), so the
   "Add" has *zero observable effect* — the dialog closed, nothing
   changed.

Both branches violate the user's expectation of "adding".

## Suggested fix

In `addVariable`, when `name in self._by_name`:

1. Emit `errorOccurred` with "Variable already exists; edit it in the
   table instead." Don't stage.

— or, more useful —

2. Emit a separate `existingVariableSelected(int rowIndex, str value)`
   signal. The QML side dismisses the Add dialog, scrolls the list view
   to that row, focuses its value cell, and selects all text. The user
   immediately sees what they collided with.

Defence in depth: the `AddVarDialog` could also disable the "Add" button
when `appController.userVarModel.hasVariable(name)` returns true (new
slot), turning the issue into a non-event.
