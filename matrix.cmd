@echo off
REM ============================================================
REM  Universelle Schoepfer-Matrix — Launcher
REM  Faehrt einen Agent-Turn ueber OpenClaw (Hirn) mit allen
REM  MCP-Tools (science, factory, review, planner, knowledge).
REM
REM  Nutzung:
REM    matrix "Hol mir die ChEMBL-Daten zu Aspirin"
REM    matrix "Finde Inhibitoren fuer EGFR"
REM    matrix --probe                (listet alle MCP-Tools)
REM    matrix --test                 (testet alle MCP-Server)
REM ============================================================
setlocal
set "OPENCLAW_STATE_DIR=n:/allinall/openclaw-workspace/state"
set "ROOT=n:/allinall"

if "%~1"=="--probe" (
  node "%ROOT%/openclaw-main/openclaw.mjs" mcp probe
  goto :eof
)
if "%~1"=="--test" (
  python "%ROOT%/mcp-servers/test_mcp.py" all
  goto :eof
)
if "%~1"=="" (
  echo Nutzung: matrix "deine Anfrage"
  echo         matrix --probe    ^| --test
  goto :eof
)

REM Eindeutige Session pro Aufruf (Zeitstempel)
set "SID=matrix-%RANDOM%"
node "%ROOT%/openclaw-main/openclaw.mjs" agent --local --session-id "%SID%" -m "%~1"
endlocal
