Set ws = CreateObject("WScript.Shell")
ws.Run Chr(34) & WScript.Arguments(0) & Chr(34), 0, True
