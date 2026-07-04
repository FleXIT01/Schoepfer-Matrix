@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - FULL-MODUS (V1: Tool-Profil "full")
REM  ALLE Tools freigegeben (Science, Factory, Review, Wiki,
REM  Molviz, GitHub, Jobs...). Fuer Supervisor-Laeufe, drug-
REM  discovery, deep-research mit voller Tool-Palette.
REM
REM  UNTERSCHIED zu gateway.cmd:
REM  - openclaw-full.json statt openclaw.json
REM  - Kein deny-Liste (ausser git force-push)
REM  - Mehr VRAM-Druck wegen mehr MCP-Server gleichzeitig
REM ============================================================
setlocal EnableExtensions
set "ROOT=n:/allinall"
title Schoepfer-Matrix (FULL-MODUS)

set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_KV_CACHE_TYPE=q8_0

if exist "n:\allinall\secrets.env" (
    C:\Python314\python.exe n:\allinall\sync_secrets.py
)

echo ============================================================
echo   SCHOEPFER-MATRIX  --  FULL-MODUS  (alle Tools aktiv)
echo   Configs: openclaw-full.json
echo   Beenden: Fenster schliessen oder N beim Neustart-Prompt.
echo ============================================================
echo.

:gwloop
echo [%date% %time%] --- Full-Gateway-Start ---
node "%ROOT%/openclaw-main/openclaw.mjs" gateway run --config "n:/allinall/openclaw-full.json"
set "RC=%ERRORLEVEL%"
echo.
echo [!] Full-Gateway beendet (ExitCode %RC%).
choice /c SN /t 8 /d S /m "Neu starten? S=ja [Default 8s]  N=beenden"
if errorlevel 2 goto stopped
goto gwloop

:stopped
echo [x] Full-Gateway gestoppt.
pause
endlocal
