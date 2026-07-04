@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - AUTOSTART-SCHALTER (PC-Boot an/aus)
REM  Legt die Startverknuepfung im Autostart-Ordner an oder
REM  entfernt sie. AN  = Gateway+Ollama starten beim PC-Boot.
REM  AUS = nichts startet automatisch (Strom sparen), du
REM        startest selbst mit gateway.cmd.
REM  Aufruf:  autostart.cmd on  |  autostart.cmd off  |  autostart.cmd
REM  WICHTIG: CRLF-Zeilenenden (Windows).
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"
title Schoepfer-Matrix Autostart-Schalter
set "ARG=%~1"

if /I "%ARG%"=="on"  goto set_on
if /I "%ARG%"=="off" goto set_off

REM ---------- Status anzeigen + Menue ----------
call :show_status
echo.
echo   Was moechtest du?
echo     [1] Autostart EINschalten  (Gateway+Ollama starten beim PC-Boot)
echo     [2] Autostart AUSschalten  (nichts startet automatisch - Strom sparen)
echo     [3] Abbrechen
echo.
choice /c 123 /n /m "  Auswahl (1/2/3): "
if errorlevel 3 goto cancel
if errorlevel 2 goto set_off
if errorlevel 1 goto set_on

:set_on
powershell -NoProfile -Command "$s=[Environment]::GetFolderPath('Startup'); $l=Join-Path $s 'Schoepfer-Matrix Gateway.lnk'; $w=New-Object -ComObject WScript.Shell; $sc=$w.CreateShortcut($l); $sc.TargetPath='%MATRIX_ROOT%\gateway.cmd'; $sc.WorkingDirectory='%MATRIX_ROOT%'; $sc.WindowStyle=7; $sc.Description='Schoepfer-Matrix Gateway (Autostart)'; $sc.Save(); Write-Host '  [ok] Autostart EIN: Gateway+Ollama starten kuenftig beim PC-Boot.'"
goto done

:set_off
powershell -NoProfile -Command "$s=[Environment]::GetFolderPath('Startup'); $l=Join-Path $s 'Schoepfer-Matrix Gateway.lnk'; if(Test-Path $l){ Remove-Item $l -Force; Write-Host '  [ok] Autostart AUS: beim PC-Boot startet nichts mehr.' } else { Write-Host '  [i] Autostart war bereits aus.' }"
goto done

:cancel
echo   Abgebrochen - nichts geaendert.
goto done

:show_status
powershell -NoProfile -Command "$s=[Environment]::GetFolderPath('Startup'); $l=Join-Path $s 'Schoepfer-Matrix Gateway.lnk'; if(Test-Path $l){ Write-Host '  Aktueller Status: AUTOSTART EIN (startet beim PC-Boot).' } else { Write-Host '  Aktueller Status: AUTOSTART AUS (du startest selbst mit gateway.cmd).' }"
exit /b 0

:done
echo.
call :show_status
echo.
ping -n 5 127.0.0.1 >nul
endlocal
