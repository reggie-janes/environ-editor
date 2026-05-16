# 008 — Manually-added content in `~/.config/envedit/env.sh` is silently dropped on next Apply

**Category:** Data loss
**Severity:** Low (file is documented as managed, but the wording is mild)

## Location

`envedit/core/platform_unix.py`, `apply_user_vars` lines 106-117

## Problem

`apply_user_vars` reads the existing file, parses with
`_parse_shell_assigns`, merges with the user's pending changes, and writes
back via `_format_env_sh`. The merge round-trip preserves only what the
regex parser understands: `(export )?NAME="value"` and
`(export )?NAME='value'` on a single line.

Anything else — comments, conditionals, line continuations, function
definitions, `unset` lines, `alias` lines, the user's own additions — is
silently discarded on the next save.

The header at the top of the file says:

```
# Managed by EnvEdit — do not edit manually
```

…which is a warning, but a quiet one. A user who edits the file (e.g. to
add a conditional `[ -d /opt/foo/bin ] && export PATH=…`) will lose that
content the next time they click Apply on the User tab, with no diff and
no error.

This also interacts with issue 002 (shell-injection) — if anyone fixes
the quoting to single-quote, they should consider whether to detect and
preserve unparseable lines verbatim, or detect them and prompt the user.

## Suggested fix

Two reasonable approaches:

1. **Preserve unparseable lines.** Change `_parse_shell_assigns` (or add a
   sibling `_parse_with_passthrough`) to return *both* the parsed assigns
   *and* the list of unrecognised lines. `_format_env_sh` re-emits the
   passthrough lines at the bottom of the rewrite. This costs nothing if
   the file follows EnvEdit's format, and preserves user additions.

2. **Detect and refuse.** On reading, if any non-comment line fails to
   parse, raise instead of silently dropping. The controller surfaces it
   as "env.sh has been hand-edited; reload?" and refuses to overwrite
   until the user confirms.

Option 1 is friendlier; option 2 is safer.
