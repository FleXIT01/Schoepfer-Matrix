@echo off
REM ============================================================
REM  ClawHub Handy-Pairing: frischen QR-Code erzeugen + oeffnen.
REM  Doppelklick -> QR geht auf -> mit OpenClaw-App scannen -> approve.
REM  WICHTIG: Der Code gilt nur 10 MINUTEN. Bei Ablauf einfach
REM  diese Datei erneut doppelklicken (erzeugt neuen Code).
REM  Setzt dieselben Pfade wie gateway.cmd, damit der Token in
REM  DEM State-Dir landet, das das laufende Gateway liest.
REM  WICHTIG: Diese Datei MUSS CRLF-Zeilenenden haben (Windows).
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"
set "OPENCLAW_STATE_DIR=%MATRIX_ROOT%/openclaw-workspace/state"
set "OPENCLAW_AGENT_DIR=C:\Users\Farnberger\.openclaw\agents\main\agent"
set "OUT=%MATRIX_ROOT%\openclaw-workspace\output"
title ClawHub - Handy-Pairing QR

echo ============================================================
echo   ClawHub - Handy verbinden (QR erzeugen)
echo ============================================================
echo.
echo [..] Erzeuge frischen Pairing-Code (gilt nur 10 Minuten) ...
node "%MATRIX_ROOT%/openclaw-main/openclaw.mjs" qr --json > "%TEMP%\ocqr.json" 2>nul
%PYTHON_EXE% %MATRIX_ROOT%\make_qr.py "%TEMP%\ocqr.json"
if errorlevel 1 (
    echo.
    echo [FEHLER] Konnte keinen QR erzeugen.
    echo          Laeuft das Gateway? Starte zuerst gateway.cmd.
    echo.
    pause
    exit /b 1
)
start "" "%OUT%\clawhub_pairing_qr.png"
echo [ok] QR ist offen.
echo.
echo ============================================================
echo   JETZT mit der OpenClaw-App scannen (Onboarding - QR scannen).
echo   Handy muss im SELBEN WLAN sein. Code gilt 10 Minuten!
echo.
echo   Danach am PC freigeben:
echo     cd %MATRIX_ROOT%\openclaw-main
echo     node openclaw.mjs devices list
echo     node openclaw.mjs devices approve ^<id^>
echo ============================================================
echo.
echo Setup-Code zum Abtippen (falls Scannen nicht geht):
type "%OUT%\clawhub_setupcode.txt"
echo.
echo.
pause
endlocal
