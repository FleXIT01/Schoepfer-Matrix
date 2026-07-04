@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - STOPP FUER ALLES (Not-Aus per Doppelklick)
REM  Beendet Gateway, Ollama, Reranker, ComfyUI, Webhook und haelt
REM  die Docker-Stacks (WeKnora/SearXNG) an. Port-basiert = robust.
REM  Logik liegt in stop_all.ps1 (gemeinsam mit dem Strg+C-Cleanup).
REM  WICHTIG: CRLF-Zeilenenden (Windows).
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"
title Schoepfer-Matrix STOPP
powershell -NoProfile -ExecutionPolicy Bypass -File "%MATRIX_ROOT%\stop_all.ps1"
echo.
ping -n 5 127.0.0.1 >nul
endlocal
