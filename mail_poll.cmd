@echo off
REM Schöpfer-Matrix Mail-Eingang (N5) — läuft alle 5 Minuten via Scheduled Task
setlocal
call "%~dp0env.cmd"
REM UTF-8 fuer Python erzwingen (cp1252 crasht bei Emojis in umgeleiteter Ausgabe)
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

REM Secrets aus secrets.env laden
for /f "usebackq tokens=1,* delims==" %%A in ("%MATRIX_ROOT%\secrets.env") do (
    if /i "%%A"=="TELEGRAM_BOT_TOKEN"       set TELEGRAM_BOT_TOKEN=%%B
    if /i "%%A"=="TELEGRAM_DEFAULT_CHAT_ID"  set TELEGRAM_DEFAULT_CHAT_ID=%%B
)

%PYTHON_EXE% %MATRIX_ROOT%\mail_poll.py %*

endlocal
