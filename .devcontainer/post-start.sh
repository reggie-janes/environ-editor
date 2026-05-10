#!/bin/bash
# Runs inside the container every time it starts.
set -exuo pipefail

echo "post-start.sh"

if [ -n "${GIT_USER_NAME_OVERRIDE:-}" ]; then
    git config --global user.name "$GIT_USER_NAME_OVERRIDE"
    echo "Git user.name set to $GIT_USER_NAME_OVERRIDE"
fi

if [ -n "${GIT_USER_EMAIL_OVERRIDE:-}" ]; then
    git config --global user.email "$GIT_USER_EMAIL_OVERRIDE"
    echo "Git user.email set to $GIT_USER_EMAIL_OVERRIDE"
fi

echo "post-start.sh done"
