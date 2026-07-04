@echo off
REM ================================================================
REM  trace.cmd -- Schopfer-Matrix Turn-Protokoll anzeigen
REM  Aufruf:
REM    trace.cmd          --> letzte 20 Turns
REM    trace.cmd 50       --> letzte 50 Turns
REM    trace.cmd stats    --> 7-Tage-Statistiken
REM    trace.cmd stats 30 --> 30-Tage-Statistiken
REM ================================================================
C:\Python314\python.exe n:\allinall\mcp-servers\trace_mcp\view.py %*
