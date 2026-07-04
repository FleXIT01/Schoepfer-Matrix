@echo off
REM Schöpfer-Matrix Telegram Callback-Poller (G1) — läuft jede Minute via Scheduled Task
setlocal

REM Secrets aus secrets.env laden
for /f "usebackq tokens=1,* delims==" %%A in ("n:\allinall\secrets.env") do (
    if /i "%%A"=="TELEGRAM_BOT_TOKEN"       set TELEGRAM_BOT_TOKEN=%%B
    if /i "%%A"=="TELEGRAM_DEFAULT_CHAT_ID"  set TELEGRAM_DEFAULT_CHAT_ID=%%B
)

C:\Python314\python.exe n:\allinall\tg_callback_poll.py %*

endlocal
