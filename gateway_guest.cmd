@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - GAST-/DEMO-MODUS (N10)
REM  Startet Gateway mit eingeschraenktem Profil (openclaw-guest.json)
REM  NUR Lese-Tools: kb_search, research, science, status, pdf (nur lesen).
REM  GESPERRT: Shell, Mailversand, Datei-Schreiben, Hook, Office, factory.
REM
REM  Fuer Kunden-Demos: Demo-Konto Telegram-ID in openclaw-guest.json
REM  unter channels.telegram.allowFrom ergaenzen.
REM  Demo-Drehbuch: DEMO.md
REM ============================================================
setlocal EnableExtensions
set "ROOT=n:/allinall"
set "OPENCLAW_STATE_DIR=n:/allinall/openclaw-workspace/state"
title Schoepfer-Matrix (GAST-MODUS)

echo ============================================================
echo   SCHOEPFER-MATRIX  --  GAST-/DEMO-MODUS
echo   Nur Lese-Tools. Shell/Mail/Dateischreiben gesperrt.
echo   Demo-Drehbuch: n:\allinall\DEMO.md
echo ============================================================
echo.

REM secrets.env lesen (fuer VRAM-Flags)
if exist "n:\allinall\secrets.env" (
    C:\Python314\python.exe n:\allinall\sync_secrets.py
)

set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_KV_CACHE_TYPE=q8_0

REM Guest-Config als State-Pfad setzen (temporaer in diesem Prozess)
set "OPENCLAW_STATE_DIR=n:/allinall"
set "OPENCLAW_STATE_FILE=openclaw-guest.json"

echo [1] Ollama-Check ...
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [!] Ollama nicht erreichbar - bitte zuerst gateway.cmd starten.
    pause
    goto end
)
echo     [ok] Ollama laeuft.
echo.

echo [2] Starte Gateway im Gast-Modus ...
echo.
echo ============================================================
echo   GAST-MODUS AKTIV - Bot ist jetzt eingeschraenkt online.
echo   Zum Beenden: Fenster schliessen.
echo ============================================================
echo.

:gwloop
echo [%date% %time%] --- Gast-Gateway-Start ---
node "%ROOT%/openclaw-main/openclaw.mjs" gateway run --config "n:/allinall/openclaw-guest.json"
set "RC=%ERRORLEVEL%"
echo.
echo [!] Gast-Gateway beendet (ExitCode %RC%).
choice /c SN /t 8 /d S /m "Neu starten? S=ja [Default 8s]  N=beenden"
if errorlevel 2 goto stopped
goto gwloop

:stopped
echo [x] Gast-Gateway gestoppt.
pause
:end
endlocal
