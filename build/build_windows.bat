@echo off
python -m nuitka ^
  --standalone ^
  --onefile ^
  --plugin-enable=pyside6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\environ-editor.ico ^
  --include-data-dir=assets=assets ^
  --include-data-dir=envedit/qml=qml ^
  --output-filename=EnvEdit.exe ^
  main.py
