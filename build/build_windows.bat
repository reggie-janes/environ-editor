@echo off
python -m nuitka ^
  --assume-yes-for-downloads ^
  --standalone ^
  --onefile ^
  --plugin-enable=pyside6 ^
  --include-qt-plugins=qml ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\environ-editor.ico ^
  --include-data-dir=assets=assets ^
  --include-data-dir=envedit/qml=qml ^
  --output-filename=EnvEdit.exe ^
  main.py
