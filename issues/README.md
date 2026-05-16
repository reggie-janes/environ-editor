# Issues

Code-audit findings, one file per issue. Numbered in discovery order,
not by severity. The **Severity** field inside each file is the thing to
sort by when triaging.

| #   | Title                                                                    | Area          | Severity |
| --- | ------------------------------------------------------------------------ | ------------- | -------- |
| 001 | ConfirmDialog references undefined `Theme.colorNegativeText`             | QML / theme   | Low      |
| 002 | env.sh double-quoting interprets `$`, backticks and `$(…)` on source     | Unix backend  | **High** |
| 003 | Saving User PATH tab nukes inherited PATH                                | Unix backend  | **High** |
| 004 | Unix system apply blocks the GUI thread on `pkexec`/`sudo`               | Unix backend  | Medium   |
| 005 | No variable-name validation; invalid identifiers silently disappear      | Models / UI   | Medium   |
| 006 | Add-PATH dialog accepts `:`-separated input; one row fans out into many  | Models / UI   | Medium   |
| 007 | Rename A→B then B→A is refused because A is still in `_by_name`          | EnvVarModel   | Low      |
| 008 | `apply_user_vars` round-trip strips comments / unparsed content silently | Unix backend  | Low      |
| 009 | Non-login shells (most terminals) don't source env.sh                    | Unix backend  | Medium   |
| 010 | `get_user_vars` exposes runtime-only vars (DISPLAY, PWD, …) as editable  | Unix backend  | Medium   |
| 011 | `UnixBackend.apply_system_path` drops `on_complete`                      | Unix backend  | Low      |
| 012 | No concurrent-instance protection — two EnvEdits can clobber writes      | Core          | Low      |
| 013 | PATH Diff dialog shows the full list instead of changes                  | Controller/UI | Low      |
| 014 | Adding a duplicate-name variable silently overwrites or no-ops           | EnvVarModel   | Low      |
| 015 | Elevation timeout reloads while the elevated child may still be writing  | Win backend   | Low      |
| 016 | Windows always writes `REG_EXPAND_SZ`, never `REG_SZ`                    | Win backend   | Low      |

## High-severity summary

- **002** is the worst. Anyone who pastes a literal `$(…)` or backtick
  expression into a value loses the literal silently on the next login, or
  worse, executes it. Single-quote the values when writing env.sh.
- **003** is the easiest to demonstrate. On a clean install, adding one
  PATH entry replaces the inherited PATH wholesale on the next login. Most
  users won't notice because of issue 009 (their terminals don't source
  env.sh), but the moment they reboot or log in via display manager, they
  inherit a broken PATH.

These two share a fix surface — both are about how the User-tab Apply
materialises into a sourceable shell file — and should probably be
addressed together.
