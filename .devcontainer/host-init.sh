#!/bin/bash
# Runs on the HOST before the container builds.
# Reserved as a hook point for team-wide host prep (creating shared dirs,
# validating required host tools, etc.). Personal host setup belongs in
# each developer's dotfiles install.sh, not here.

echo "host-init.sh"
