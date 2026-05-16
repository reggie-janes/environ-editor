# 006 — Pasting a `:`-separated string into Add PATH silently fans out into multiple entries

**Category:** Correctness / UX
**Severity:** Medium

## Location

- `envedit/qml/components/AddPathDialog.qml` — no validation
- `envedit/models/path_model.py`, `addEntry` lines 96-102 — stores raw
- `envedit/core/platform_unix.py`, `apply_user_path` line 138 —
  `os.pathsep.join(entries)` then reloads via `split(os.pathsep)`

## Problem

If the user pastes a multi-entry PATH fragment into the "Add PATH" dialog
— e.g. they copy `/opt/a/bin:/opt/b/bin` from a README — `addEntry` stores
it as one row:

```
{"path": "/opt/a/bin:/opt/b/bin", "is_new": True, ...}
```

The table shows it as one row. On Apply, `apply_user_path` joins the list
with `os.pathsep` and writes
`export PATH="/usr/bin:/opt/a/bin:/opt/b/bin"`. So far so good.

But on the next reload (which happens immediately after apply via
`_reload(1)`), `get_user_path` splits the file's PATH value on `os.pathsep`
and now sees **two** entries: `/opt/a/bin` and `/opt/b/bin`. The user
added one row and got two back, with no warning.

Same problem on Windows with `;`.

It also obscures dup detection: the in-memory `_dup_counts` Counter keys
on the raw string `/opt/a/bin:/opt/b/bin`, so a real duplicate of
`/opt/a/bin` further down the list isn't flagged until after the round-trip.

## Suggested fix

In `AddPathDialog._submit` (and `PathModel.addEntry` for defence in depth),
detect `os.pathsep` in the path. Two reasonable behaviours:

1. Reject with an inline error ("Use one path per entry"). Simple.
2. Split on `os.pathsep` and add each piece as a separate row. More
   forgiving but needs to skip empty fragments.

Either is fine — pick one and apply consistently. Also strip surrounding
whitespace and reject empty.

While in that file, also reject path entries that contain newline / NUL
characters; those would corrupt the shell file or registry value.
