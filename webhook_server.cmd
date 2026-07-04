@echo off
REM ============================================================
REM  Schoepfer-Matrix Webhook-Server (N4)
REM  Startet FastAPI-Server auf Port 7890.
REM  Eingehende Anfragen starten Agent-Turns via matrix.cmd.
REM
REM  Token:   MATRIX_WEBHOOK_TOKEN in secrets.env
REM  Default: schoepfer-matrix-webhook-2026
REM  Test:    curl -X POST http://127.0.0.1:7890/run
REM           -H "Authorization: Bearer <token>"
REM           -H "Content-Type: application/json"
REM           -d "{\"prompt\": \"system_status\"}"
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"

if exist "%MATRIX_ROOT%\secrets.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%MATRIX_ROOT%\secrets.env") do (
        if "%%A"=="MATRIX_WEBHOOK_TOKEN" set "MATRIX_WEBHOOK_TOKEN=%%B"
    )
)

set "OPENCLAW_STATE_DIR=%MATRIX_ROOT%/openclaw-workspace/state"
set "MATRIX_CMD=%MATRIX_ROOT%\matrix.cmd"

echo [webhook_server] Port 7890 - Token aus secrets.env oder Default
%PYTHON_EXE% %MATRIX_ROOT%\webhook_server.py
endlocal
