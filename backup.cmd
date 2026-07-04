@echo off
REM Schoepfer-Matrix Backup (V6)
REM  backup.cmd        = echtes Backup nach %BACKUP_DEST%
REM  backup.cmd TEST   = Trockenlauf
REM  V6 (03.07.2026): + eval/ (Golden-Harness+Baseline), + agent-workspace
REM  (Skills+Memory), + *.ps1/*.yaml/*.ahk, + n8n-Docker-Volumes, Retention
REM  behaelt IMMER die %MIN_KEEP% neuesten Backups (Lehre: 14-Tage-Regel
REM  loeschte das letzte verbliebene Backup).
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0env.cmd"

set "SRC=%MATRIX_ROOT%"
set "DEST=%BACKUP_DEST%"
set "WK=%MATRIX_ROOT%\WeKnora-main"
set "LOG=%MATRIX_ROOT%\openclaw-workspace\output\backup.log"
set "TGTOKEN=%TELEGRAM_BOT_TOKEN%"
set "TGCHAT=%TELEGRAM_DEFAULT_CHAT_ID%"
set "KEEP_DAYS=14"
set "MIN_KEEP=5"
set "DRY=%~1"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd_HHmmss\""') do set "TS=%%i"
set "BDIR=%DEST%\%TS%"

echo ============================================================
echo   Schoepfer-Matrix Backup  [%TS%]
echo   Ziel: %BDIR%
if /i "%DRY%"=="TEST" echo   TROCKENLAUF -- keine Dateien werden veraendert
echo ============================================================
echo.

if not exist "%DEST%" mkdir "%DEST%" 2>nul
if not exist "%DEST%" (
    echo [FEHLER] Backup-Ziel %DEST% nicht erreichbar - ist Laufwerk I: eingebunden?
    call :tg_alarm "Backup FEHLER: Ziel %DEST% nicht erreichbar [%TS%]"
    goto end
)

if /i NOT "%DRY%"=="TEST" mkdir "%BDIR%" 2>nul
set "ERR=0"

echo [1/6] openclaw-workspace\state ...
if /i "%DRY%"=="TEST" (
    robocopy "%SRC%\openclaw-workspace\state" "%BDIR%\state" /E /L /NJH /NJS /BYTES 2>nul
) else (
    robocopy "%SRC%\openclaw-workspace\state" "%BDIR%\state" /E /NJH /NJS /R:1 /W:2 >nul 2>&1
    if errorlevel 8 set "ERR=1"
)
echo       [ok]

echo [2/6] mcp-servers ...
if /i "%DRY%"=="TEST" (
    robocopy "%SRC%\mcp-servers" "%BDIR%\mcp-servers" /E /L /NJH /NJS /BYTES /XD __pycache__ .venv 2>nul
) else (
    robocopy "%SRC%\mcp-servers" "%BDIR%\mcp-servers" /E /NJH /NJS /R:1 /W:2 /XD __pycache__ .venv >nul 2>&1
    if errorlevel 8 set "ERR=1"
)
echo       [ok]

echo [3/6] Startskripte + AGENTS.md + Konfiguration ...
if /i NOT "%DRY%"=="TEST" (
    mkdir "%BDIR%\scripts" 2>nul
    for %%f in ("%SRC%\*.cmd" "%SRC%\*.vbs" "%SRC%\*.py" "%SRC%\*.ps1" "%SRC%\*.yaml" "%SRC%\*.ahk" "%SRC%\requirements.txt" "%SRC%\MASTERPLAN*.md" "%SRC%\MASTERPLAN*.txt" "%SRC%\ADDENDUM*.md") do (
        if exist "%%~f" copy /Y "%%~f" "%BDIR%\scripts\" >nul 2>&1
    )
    if exist "%SRC%\secrets.env" copy /Y "%SRC%\secrets.env" "%BDIR%\scripts\" >nul 2>&1
    if exist "%WK%\.env" copy /Y "%WK%\.env" "%BDIR%\scripts\weknora.env" >nul 2>&1
    if exist "%SRC%\openclaw-workspace\agent-workspace\AGENTS.md" copy /Y "%SRC%\openclaw-workspace\agent-workspace\AGENTS.md" "%BDIR%\scripts\" >nul 2>&1
    if exist "%SRC%\openclaw-workspace\state\openclaw.json" copy /Y "%SRC%\openclaw-workspace\state\openclaw.json" "%BDIR%\scripts\" >nul 2>&1
)
echo       [ok]

echo [4/6] eval (Golden-Harness + Baseline) + agent-workspace (Skills + Memory) ...
if /i "%DRY%"=="TEST" (
    robocopy "%SRC%\eval" "%BDIR%\eval" /E /L /NJH /NJS /BYTES /XD __pycache__ 2>nul
    robocopy "%SRC%\openclaw-workspace\agent-workspace" "%BDIR%\agent-workspace" /E /L /NJH /NJS /BYTES /XD __pycache__ node_modules .openclaw-install-backups 2>nul
) else (
    robocopy "%SRC%\eval" "%BDIR%\eval" /E /NJH /NJS /R:1 /W:2 /XD __pycache__ >nul 2>&1
    if errorlevel 8 set "ERR=1"
    robocopy "%SRC%\openclaw-workspace\agent-workspace" "%BDIR%\agent-workspace" /E /NJH /NJS /R:1 /W:2 /XD __pycache__ node_modules .openclaw-install-backups >nul 2>&1
    if errorlevel 8 set "ERR=1"
)
echo       [ok]

echo [5/6] WeKnora Docker-Volumes ...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo       [i] Docker nicht aktiv - Volume-Dump uebersprungen.
goto docker_done
:docker_ok
if /i NOT "%DRY%"=="TEST" (
    mkdir "%BDIR%\docker-volumes" 2>nul
    for %%v in (weknora-main_qdrant_data weknora-main_postgres-data weknora-main_data-files) do (
        docker run --rm -v %%v:/d -v "%BDIR%\docker-volumes":/b alpine tar czf /b/%%v_%TS%.tgz -C /d . >nul 2>&1
        if errorlevel 1 (
            echo       [!] Volume %%v nicht gefunden oder Fehler.
        ) else (
            echo       [ok] %%v gesichert.
        )
    )
)
:docker_done

echo [6/6] n8n Docker-Volumes (falls vorhanden) ...
docker info >nul 2>&1
if errorlevel 1 (
    echo       [i] Docker nicht aktiv - uebersprungen.
    goto n8n_done
)
if /i "%DRY%"=="TEST" goto n8n_done
for /f %%v in ('docker volume ls -q 2^>nul ^| findstr /i n8n') do (
    docker run --rm -v %%v:/d -v "%BDIR%\docker-volumes":/b alpine tar czf /b/%%v_%TS%.tgz -C /d . >nul 2>&1
    if errorlevel 1 (
        echo       [!] n8n-Volume %%v Fehler.
    ) else (
        echo       [ok] %%v gesichert.
    )
)
:n8n_done
echo.

if /i NOT "%DRY%"=="TEST" (
    echo [i] Bereinige alte Backups: aelter als %KEEP_DAYS% Tage, aber IMMER die %MIN_KEEP% neuesten behalten ...
    powershell -NoProfile -Command "$d='%DEST%'; $k=%KEEP_DAYS%; $m=%MIN_KEEP%; $all=Get-ChildItem $d -Directory | Sort-Object Name -Descending; if($all.Count -gt $m){ $all | Select-Object -Skip $m | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$k) } | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue } }" >nul 2>&1
)

echo.
if "%ERR%"=="0" (
    echo [OK] Backup ERFOLGREICH: %BDIR%
    echo [%TS%] [OK] %BDIR% >> "%LOG%"
    if /i NOT "%DRY%"=="TEST" call :tg_alarm "Backup OK [%TS%]"
) else (
    echo [!] Backup mit Fehlern: %BDIR%
    echo [%TS%] [FEHLER] %BDIR% >> "%LOG%"
    call :tg_alarm "Backup FEHLER [%TS%]"
)
echo.
echo Letzte Backups:
dir /b /o-d "%DEST%" 2>nul
goto end

:tg_alarm
if /i "%DRY%"=="TEST" exit /b 0
powershell -NoProfile -Command "try{ Invoke-RestMethod 'https://api.telegram.org/bot%TGTOKEN%/sendMessage' -Method Post -Body @{chat_id='%TGCHAT%';text='%~1'} | Out-Null }catch{}" >nul 2>&1
exit /b 0

:end
endlocal
