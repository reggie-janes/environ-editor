@echo off
REM --onefile is intentionally still off so the next CI run prints a fresh
REM diagnostic and we can see what these exclusions actually saved. Restore
REM --onefile and re-enable artifact upload once size looks healthy.
REM
REM --nofollow-import-to has no effect on what the PySide6 plugin physically
REM copies, so it's gone. We exclude DLLs by filename/path pattern instead.
REM Patterns are matched against the relative path inside the bundle.
python -m nuitka ^
  --assume-yes-for-downloads ^
  --standalone ^
  --plugin-enable=pyside6 ^
  --include-qt-plugins=qml ^
  --include-windows-runtime-dlls=no ^
  --noinclude-qt-translations ^
  --noinclude-dlls=*Qt6WebEngine* ^
  --noinclude-dlls=*Qt6Pdf* ^
  --noinclude-dlls=*Qt6Charts* ^
  --noinclude-dlls=*Qt6Location* ^
  --noinclude-dlls=*Qt6Multimedia* ^
  --noinclude-dlls=*Qt6SpatialAudio* ^
  --noinclude-dlls=*Qt6DataVisualization* ^
  --noinclude-dlls=*Qt6Graphs* ^
  --noinclude-dlls=*Qt6RemoteObjects* ^
  --noinclude-dlls=*Qt6Quick3D* ^
  --noinclude-dlls=*Qt63D* ^
  --noinclude-dlls=*Qt6Bluetooth* ^
  --noinclude-dlls=*Qt6Nfc* ^
  --noinclude-dlls=*Qt6Positioning* ^
  --noinclude-dlls=*Qt6Sensors* ^
  --noinclude-dlls=*Qt6SerialBus* ^
  --noinclude-dlls=*Qt6SerialPort* ^
  --noinclude-dlls=*Qt6TextToSpeech* ^
  --noinclude-dlls=*Qt6Scxml* ^
  --noinclude-dlls=*Qt6StateMachine* ^
  --noinclude-dlls=*Qt6Sql* ^
  --noinclude-dlls=*Qt6Test* ^
  --noinclude-dlls=*Qt6Help* ^
  --noinclude-dlls=*Qt6Designer* ^
  --noinclude-dlls=*Qt6QuickControls2Imagine* ^
  --noinclude-dlls=*Qt6QuickControls2Fusion* ^
  --noinclude-dlls=*Qt6QuickControls2Universal* ^
  --noinclude-dlls=*FluentWinUI3* ^
  --noinclude-dlls=*VirtualKeyboard* ^
  --noinclude-dlls=*Qt5Compat* ^
  --noinclude-dlls=*NativeStyle* ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\environ-editor.ico ^
  --include-data-dir=assets=assets ^
  --include-data-dir=envedit/qml=qml ^
  --output-filename=EnvEdit.exe ^
  main.py
