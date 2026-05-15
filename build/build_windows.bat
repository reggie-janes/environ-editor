@echo off
REM --onefile temporarily removed so we can inspect main.dist/ contents
REM in CI to find what's bloating the bundle. Restore once we know.
python -m nuitka ^
  --assume-yes-for-downloads ^
  --standalone ^
  --plugin-enable=pyside6 ^
  --include-qt-plugins=qml ^
  --include-windows-runtime-dlls=no ^
  --nofollow-import-to=PySide6.QtWebEngineCore,PySide6.QtWebEngineWidgets,PySide6.QtWebEngineQuick,PySide6.QtWebChannel,PySide6.QtWebSockets,PySide6.QtWebView,PySide6.Qt3DCore,PySide6.Qt3DRender,PySide6.Qt3DInput,PySide6.Qt3DAnimation,PySide6.Qt3DExtras,PySide6.Qt3DLogic,PySide6.QtCharts,PySide6.QtDataVisualization,PySide6.QtMultimedia,PySide6.QtMultimediaWidgets,PySide6.QtSpatialAudio,PySide6.QtPdf,PySide6.QtPdfWidgets,PySide6.QtBluetooth,PySide6.QtNfc,PySide6.QtPositioning,PySide6.QtLocation,PySide6.QtSensors,PySide6.QtSerialBus,PySide6.QtSerialPort,PySide6.QtTextToSpeech,PySide6.QtVirtualKeyboard,PySide6.QtRemoteObjects,PySide6.QtScxml,PySide6.QtStateMachine,PySide6.QtSql,PySide6.QtTest,PySide6.QtHelp,PySide6.QtDesigner,PySide6.QtUiTools ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\environ-editor.ico ^
  --include-data-dir=assets=assets ^
  --include-data-dir=envedit/qml=qml ^
  --output-filename=EnvEdit.exe ^
  main.py
