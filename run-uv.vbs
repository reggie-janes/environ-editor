' Silent Windows launcher.
' Double-click to run the app with no console window.
' Equivalent to: cd <this folder> && uv run pythonw main.py

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

shell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

' Check that uv is reachable; show a friendly message if not.
exitCode = shell.Run("cmd /c where uv >nul 2>&1", 0, True)
If exitCode <> 0 Then
    MsgBox "uv was not found on PATH." & vbCrLf & vbCrLf & _
           "Install it from https://docs.astral.sh/uv/ and try again.", _
           vbExclamation, "Application Launcher"
    WScript.Quit 1
End If

' 0 = hidden window, False = don't wait for the app to exit.
shell.Run "uv run pythonw main.py", 0, False
