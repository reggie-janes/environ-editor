# 010 — Runtime-only env vars (`DISPLAY`, `PWD`, `SSH_AUTH_SOCK`, …) appear as editable user vars

**Category:** UX / data integrity
**Severity:** Medium

## Location

`envedit/core/platform_unix.py`, `UnixBackend.get_user_vars` lines 79-85

```python
def get_user_vars(self) -> dict[str, str]:
    raw = _read_envedit_vars()
    raw.update(os.environ)            # everything in os.environ
    return {k: v for k, v in raw.items() if k not in _PATH_KEYS}
```

## Problem

`get_user_vars` merges `os.environ` over the managed file's contents. The
intent (per the comment) is to surface keys that were applied but not yet
re-sourced. The side effect is that *every* runtime variable bleeds into
the User Variables tab:

- `DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY` — set by the display manager
- `PWD`, `OLDPWD`, `SHLVL`, `_` — set by the shell on every command
- `SSH_AUTH_SOCK`, `SSH_AGENT_PID` — set by ssh-agent for this session
- `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS` — set by the desktop
- `LS_COLORS`, `LESSOPEN`, `TERM` — set by /etc/profile / shell init
- `_JAVA_OPTIONS`, `GTK_*`, `QT_*` — set by various wrappers

The user sees ~40 rows of stuff they didn't put there. If they edit one
of them — e.g. they "fix" `DISPLAY=:0` to `DISPLAY=:1` — it gets staged,
then on Apply it gets persisted to `~/.config/envedit/env.sh`. From now
on, every login overrides the display manager's `DISPLAY`. This is
almost never what the user wants and there's no warning.

Same shape on Windows: `get_user_vars` returns whatever HKCU\Environment
holds, which is the right answer there because HKCU is exactly the set
of user-managed persistent vars. The bug is Unix-only.

## Suggested fix

Distinguish "what's persisted" (env.sh) from "what's in the live session"
(os.environ). Two UI options:

1. **Show only managed vars by default**, with an "Inherited (read-only)"
   collapsible section listing the others. Editing an inherited var
   prompts: "This will create a persistent override of a session
   variable. Continue?"

2. **Hard-blacklist the well-known runtime vars** (`DISPLAY`, `PWD`,
   `OLDPWD`, `SHLVL`, `_`, `SSH_*`, `XDG_*`, `DBUS_*`, `TERM`,
   `LS_COLORS`, …) from the User tab. Simpler, but the list is open-ended.

Option 1 is the right long-term answer. It also makes the post-apply
reload not look weird: today, after Apply, `os.environ` doesn't change
(the new login hasn't happened), so the User tab can appear to "lose"
just-applied edits unless `get_user_vars` overlays the file. Distinguish
"value in file" from "value in environ" instead of merging them.
