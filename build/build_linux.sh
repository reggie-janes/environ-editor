#!/usr/bin/env bash
set -euo pipefail
python -m nuitka \
  --standalone \
  --onefile \
  --plugin-enable=pyside6 \
  --linux-icon=assets/environ-editor.ico \
  --include-data-dir=assets=assets \
  --include-data-dir=envedit/qml=envedit/qml \
  --output-filename=EnvEdit \
  main.py
