@echo off
REM ============================================================
REM  NOT-AUS AUFHEBEN — gibt Agent-Aktionen wieder frei.
REM  Hotkey:  Ctrl+Alt+M  (wenn notaus.ahk laeuft)
REM ============================================================
set "FLAG=n:\allinall\openclaw-workspace\state\freeze.flag"
if exist "%FLAG%" (
    del "%FLAG%"
    echo.
    echo  [NOT-AUS] AUFGEHOBEN
    echo  Agent-Aktionen wieder erlaubt.
) else (
    echo.
    echo  [i] Kein Freeze-Flag gefunden — war bereits entsperrt.
)
echo.
pause
