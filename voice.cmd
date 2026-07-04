@echo off
REM voice.cmd — Freihaendige Sprachsteuerung (Push-to-Talk, Standard F8).
REM Voraussetzung: gateway.cmd laeuft bereits.
setlocal
call "%~dp0env.cmd"
title Matrix Voice-PTT
%PYTHON_EXE% "%MATRIX_ROOT%\voice_ptt.py" %*
endlocal
