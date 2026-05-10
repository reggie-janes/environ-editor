#!/bin/bash
# Runs inside the container once, after it's first created.
# Cwd is the workspace folder when devcontainer lifecycle scripts run.
set -euxo pipefail

echo "post-create.sh"

# Named-volume mounts come up owned by root — including the parent dirs Docker
# auto-creates above each mount point. Hand them all to the vscode user so uv
# and the Claude Code installer can write into them (the installer also needs
# to create siblings like ~/.local/state and ~/.local/bin).
sudo chown vscode:vscode .venv ~/.claude ~/.local ~/.local/share ~/.local/share/claude

# Persist ~/.claude.json (Claude Code's onboarding/trust/account state) on the
# named volume by symlinking it into ~/.claude/. This file lives at $HOME, not
# inside ~/.claude/, so without this symlink each rebuild loses
# hasCompletedOnboarding, hasIdeOnboardingBeenShown, project-trust, and
# triggers the theme/trust/auth wizard on next launch.
PERSIST="$HOME/.claude/_claude-root.json"
LINK="$HOME/.claude.json"
if [ -f "$LINK" ] && [ ! -L "$LINK" ]; then
    mv "$LINK" "$PERSIST"
fi
if [ ! -e "$PERSIST" ]; then
    touch "$PERSIST"
fi
ln -sfn "$PERSIST" "$LINK"

git config --global --add safe.directory "$PWD"

# Install project dependencies (including test extras)
uv sync --extra test

echo "post-create.sh done"

