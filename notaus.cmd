@echo off
REM ============================================================
REM  NOT-AUS — friert alle Agent-Aktionen sofort ein.
REM  Entsperren: notaus_clear.cmd
REM  Hotkey:     Ctrl+Alt+N  (wenn notaus.ahk laeuft)
REM ============================================================
set "FLAG=n:\allinall\openclaw-workspace\state\freeze.flag"
echo %date% %time%: NOT-AUS gesetzt via notaus.cmd > "%FLAG%"
echo.
echo  [NOT-AUS] AKTIV
echo  Freeze-Flag gesetzt: %FLAG%
echo.
echo  Alle Langlaeufer (jobs_mcp, mail_mcp) pruefen dieses
echo  Flag vor dem naechsten Schritt und stoppen sofort.
echo.
echo  Zum Entsperren:  notaus_clear.cmd  oder  Ctrl+Alt+M
echo.
pause
