#!/bin/bash
# Runs inside the container once, after it's first created.
# Cwd is the workspace folder when devcontainer lifecycle scripts run.
set -euo pipefail

echo "post-create.sh"

# Named-volume mounts come up owned by root; hand them to the vscode user
# so uv and Claude Code can write into them.
sudo chown vscode:vscode .venv ~/.claude

git config --global --add safe.directory "$PWD"

# Install project dependencies
uv sync
