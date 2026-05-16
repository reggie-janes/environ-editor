# 009 — Changes don't take effect in normal terminal sessions (non-login shells skip `~/.profile`)

**Category:** UX / discoverability
**Severity:** Medium

## Location

`envedit/core/platform_unix.py`, `_ensure_sourced_in_profile` (lines 177-189)
and `_login_profile` (lines 165-174)

## Problem

EnvEdit only patches the user's *login* profile:
`~/.bash_profile` → `~/.bash_login` → `~/.profile` (first existing).

On Linux, almost no one runs a login shell day-to-day. GNOME Terminal,
Konsole, xfce4-terminal, iTerm2's default profile on macOS — all start an
**interactive non-login** shell, which:

- bash: reads `~/.bashrc`, not `~/.profile`.
- zsh: reads `~/.zshrc`, not `~/.zprofile`.
- fish: reads `~/.config/fish/config.fish`, not any of the above.

Net effect: the user opens EnvEdit, adds `MY_VAR=hello`, clicks Apply, and
then opens a terminal — `echo $MY_VAR` prints nothing. The change took,
but only for the next *login* (next reboot, next GDM/SDDM session start,
next `bash -l`). The UI gives no hint of this.

This is also why issue 003 (PATH replacement) is less catastrophic than it
sounds: most users never notice the env.sh sourcing at all, because their
terminals don't read login files.

## Suggested fix

Source the managed file from both login and interactive-non-login init
files. For bash users the canonical pattern is to put the guard in
`~/.bashrc`; for zsh, `~/.zshrc`. Detect the user's shell from `$SHELL` or
fall back to seeding the guard into multiple files:

```
~/.bashrc
~/.zshrc
~/.profile           (covers /bin/sh login shells and POSIX-only users)
```

…each gated on `[ -f "$ENVEDIT_SH" ]`. The guard is idempotent (the
existing `_ensure_sourced_in_profile` already checks for the literal
string), so re-running it is safe.

fish has a different syntax and a different file — defer that to a
follow-up.

Also: surface the "you'll need to open a new terminal" detail somewhere
in the UI after a successful User-tab Apply.
