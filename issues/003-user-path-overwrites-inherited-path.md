# 003 — Saving the User PATH tab nukes every inherited PATH entry

**Category:** Correctness / UX
**Severity:** High (foot-gun — user wipes their PATH with no warning)

## Location

- `envedit/core/platform_unix.py`, `UnixBackend.get_user_path` (lines 91-99)
- `envedit/core/platform_unix.py`, `_format_env_sh` (line 151) — emits
  `export PATH="…"` literally
- `tests/test_unix_backend.py::test_get_user_path_does_not_clone_session_PATH`
  — codifies the current behaviour

## Problem

On Unix the User PATH tab shows only what `~/.config/envedit/env.sh`
contributes — it deliberately does not merge the session PATH. The comment
in `get_user_path` explains why (cloning the merged PATH would silently
revert user edits on reload and balloon the managed file on first apply).

But the *writer* doesn't account for that. When the user adds a single entry
on a fresh install:

1. Before save, `~/.config/envedit/env.sh` has no PATH at all.
2. User clicks "+ Add", enters `/opt/mybin`, clicks Apply.
3. `apply_user_path(["/opt/mybin"])` calls
   `apply_user_vars({"PATH": "/opt/mybin"})`.
4. The file now contains `export PATH="/opt/mybin"`.
5. On the next login: `~/.profile` sources the file, which runs
   `export PATH="/opt/mybin"`. This **replaces** PATH wholesale — the
   `/usr/bin:/bin:…` the shell inherited from `/etc/environment` /
   `/etc/profile` is gone.

The user adding one PATH entry has effectively unset their entire PATH for
all future login sessions. There is no warning in the UI and the failure
mode (broken `ls`, broken `sudo`, etc.) only shows up after the next login.

The Diff dialog before Apply doesn't help either — it just lists the
entries the user sees in the UI, which currently contain only `/opt/mybin`.
There's no indication that this list is about to **replace** rather than
augment.

## Suggested fix

Two options, not mutually exclusive:

1. **Write `export PATH="$PATH:…"`** when the file did not previously hold a
   PATH key. `_format_env_sh` could special-case PATH so that the first
   write prefixes `$PATH:` and subsequent writes preserve the existing
   prefix. (Requires deciding once-and-for-all whether new entries are
   appended or prepended; convention is append for user-added PATH bins.)

2. **Warn the user in the Diff dialog** when the User PATH tab is about to
   be applied and the resulting file does not contain `$PATH` somewhere in
   the value — i.e. "this will replace your inherited PATH" — and make the
   "+ Add" flow on an empty tab pre-populate the table with a sentinel
   row representing the inherited PATH, surfaced as `$PATH` literal.

Either fix needs round-trip handling: when reading back, recognise an
unsplit `$PATH` token in the PATH value rather than splitting it as a path
entry.
