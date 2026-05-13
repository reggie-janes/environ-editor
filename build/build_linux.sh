#!/usr/bin/env bash
set -euo pipefail
python -m nuitka \
  --assume-yes-for-downloads \
  --standalone \
  --onefile \
  --plugin-enable=pyside6 \
  --include-qt-plugins=qml \
  --linux-icon=assets/environ-editor.ico \
  --include-data-dir=assets=assets \
  --include-data-dir=envedit/qml=qml \
  --output-filename=EnvEdit \
  main.py
