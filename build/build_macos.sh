#!/usr/bin/env bash
set -euo pipefail
python -m nuitka \
  --standalone \
  --macos-create-app-bundle \
  --plugin-enable=pyside6 \
  --include-data-dir=assets=assets \
  --include-data-dir=envedit/qml=qml \
  --output-filename=EnvEdit \
  main.py

# Nuitka names the bundle directory after the entry script (main.app);
# --output-filename only renames the inner binary. Rename for distribution.
rm -rf EnvEdit.app
mv main.app EnvEdit.app
