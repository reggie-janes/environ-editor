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
