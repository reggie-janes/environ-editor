# 005 — Variable names are not validated; invalid shell identifiers silently disappear on reload

**Category:** Correctness / UX
**Severity:** Medium

## Location

- `envedit/qml/components/AddVarDialog.qml` (no name validation)
- `envedit/models/env_var_model.py`, `addVariable` / `editVariable`
  (no name validation)
- `envedit/core/platform_unix.py`, `_parse_shell_assigns` line 30 —
  `^([A-Za-z_][A-Za-z0-9_]*)=` (strict identifier regex)

## Problem

The Add Variable dialog accepts any non-empty name. The model also accepts
anything. On Unix the writer happily emits:

```sh
export MY-VAR="x"
export 123="x"
export FOO BAR="x"
```

…each of which is **invalid shell syntax**. On the next reload,
`_parse_shell_assigns` skips them (its regex requires
`[A-Za-z_][A-Za-z0-9_]*`), so the variables vanish from EnvEdit's view
with no error. The user thinks the save succeeded — it just silently lost
the data.

On Windows the registry tolerates arbitrary characters in value names, but
no shell will be able to read `MY-VAR` either (cmd parses `$MY-VAR` /
`%MY-VAR%` as `%MY%` minus `VAR`). So the data is written but unusable.

## Reproduction

1. User Variables → "+ Add"
2. Name: `MY-VAR`, Value: `hello`, Add.
3. Apply.
4. (Linux) Click Reload — the row is gone. The file on disk contains
   `export MY-VAR="hello"` but `_parse_shell_assigns` skips it.

## Suggested fix

Validate in `AddVarDialog` (gate the "Add" button) and in
`EnvVarModel.addVariable` / `editVariable` (defence in depth, since the
dialog is bypassable via direct rename in the table). The regex matching
the Unix parser is fine on both platforms — `^[A-Za-z_][A-Za-z0-9_]*$` —
plus a max length (Windows registry limit is 32 KB for the value name
itself, but a UI cap around 256 chars is sensible).

Show the rejection reason inline in the dialog ("Name must start with a
letter or underscore and contain only letters, digits, or underscores").
