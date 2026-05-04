Set WshShell = CreateObject("WScript.Shell")
' Launching uv run sentinel.py hidden
WshShell.Run "uv run sentinel.py", 0, False
