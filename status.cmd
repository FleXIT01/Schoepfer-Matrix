@echo off
call "%~dp0env.cmd"
REM ============================================================
REM  SCHOEPFER-MATRIX - STATUS (Doppelklick-Gesamtueberblick)
REM  Zeigt: Dienste, geladene Modelle, GPU, Task-Ergebnisse,
REM  Backup-Alter, letzten Golden-Eval, Autostart, Docker.
REM  Nur LESEND - aendert nichts. Logik: health.ps1
REM  WICHTIG: CRLF-Zeilenenden (Windows).
REM ============================================================
title Schoepfer-Matrix Status
powershell -NoProfile -ExecutionPolicy Bypass -File "%MATRIX_ROOT%\health.ps1"
echo.
pause
