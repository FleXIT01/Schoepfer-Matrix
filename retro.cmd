@echo off
REM ============================================================
REM  Schoepfer-Matrix Wochen-Retro (N9)
REM  Liest Traces + Eval-Fails (7 Tage), generiert Top-3-Vorschlaege
REM  via lokalem LLM, sendet Zusammenfassung per Telegram.
REM  Geplant: Sonntags 20:00 via SchoepferMatrix-Retro Task
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"
REM UTF-8 erzwingen: retro.py druckt Emojis -> ohne das crasht print() unter
REM cp1252 (versteckter Task = umgeleitete Ausgabe). Gleiche Lehre wie run_eval V18.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if exist "%MATRIX_ROOT%\secrets.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%MATRIX_ROOT%\secrets.env") do (
        if "%%A"=="TELEGRAM_BOT_TOKEN"    set "TELEGRAM_BOT_TOKEN=%%B"
        if "%%A"=="TELEGRAM_DEFAULT_CHAT_ID" set "TELEGRAM_DEFAULT_CHAT_ID=%%B"
    )
)

set "OPENCLAW_STATE_DIR=%MATRIX_ROOT%/openclaw-workspace/state"
REM Standard-Hirn nutzen statt gpt-oss:20b (waere ein ZWEITES 13-GB-Modell im VRAM).
set "RETRO_MODEL=gpt-oss-32k"

REM Wache: Ollama aus -> Retro ueberspringen statt leerer Vorschlaege (kein Aufwecken).
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [retro] Ollama aus - Retro uebersprungen ^(laeuft nach, wenn der Stack an ist^).
    endlocal
    exit /b 0
)

echo [retro] Starte Wochen-Retro ...
%PYTHON_EXE% %MATRIX_ROOT%\retro.py
echo [retro] Ergebnis: %ERRORLEVEL%
endlocal
