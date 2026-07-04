@echo off
REM Schoepfer-Matrix Watchdog (V4)
REM Einmalige Pruef- und Heilrunde ??? vom Task Scheduler alle 5 Min aufgerufen.
REM Prueft: Ollama (11434), Gateway (18789), WeKnora (8080), Reranker (8011)
setlocal EnableExtensions
call "%~dp0env.cmd"

set "WK=%MATRIX_ROOT%\WeKnora-main"
set "LOG=%MATRIX_ROOT%\openclaw-workspace\output\watchdog.log"
set "TGTOKEN=%TELEGRAM_BOT_TOKEN%"
set "TGCHAT=%TELEGRAM_DEFAULT_CHAT_ID%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd_HHmm\""') do set "TS=%%i"

echo [%TS%] Watchdog-Check ... >> "%LOG%"

REM --- 00) BACKUP-ALTERS-WAECHTER (laeuft VOR dem Gateway-Riegel!) ---
REM  Haette die 19-Tage-Backup-Luecke (Juni/Juli 2026) sofort gemeldet.
REM  Prueft 1x taeglich (Semaphor): juengstes Backup aelter als 3 Tage -> Telegram-Alarm.
set "BK_SEM=%TEMP%\wdg_backupage.tmp"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyyMMdd\""') do set "BK_TODAY=%%i"
set "BK_PREV="
if exist "%BK_SEM%" set /p BK_PREV=<"%BK_SEM%"
if "%BK_PREV%"=="%BK_TODAY%" goto backup_age_ok
echo %BK_TODAY%>"%BK_SEM%"
powershell -NoProfile -Command "$r='%BACKUP_DEST%'; if(-not (Test-Path $r)){ exit 2 }; $l=Get-ChildItem $r -Directory | Sort-Object Name -Descending | Select-Object -First 1; if(-not $l){ exit 3 }; $dt=[datetime]::ParseExact($l.Name,'yyyy-MM-dd_HHmmss',$null); if(((Get-Date)-$dt).TotalDays -gt 3){ exit 4 } else { exit 0 }" >nul 2>&1
set "BK_RC=%ERRORLEVEL%"
if "%BK_RC%"=="0" goto backup_age_ok
if "%BK_RC%"=="2" (
    echo [%TS%] WARNUNG: Backup-Laufwerk I: nicht erreichbar. >> "%LOG%"
    call :tg_alarm "WATCHDOG: Backup-Laufwerk I: nicht erreichbar - Backups laufen ins Leere! [%TS%]"
    goto backup_age_ok
)
if "%BK_RC%"=="3" (
    echo [%TS%] WARNUNG: Kein Backup vorhanden. >> "%LOG%"
    call :tg_alarm "WATCHDOG: KEIN Backup in %BACKUP_DEST% vorhanden! [%TS%]"
    goto backup_age_ok
)
echo [%TS%] WARNUNG: Juengstes Backup aelter als 3 Tage. >> "%LOG%"
call :tg_alarm "WATCHDOG: Backup aelter als 3 Tage - Backup-Task pruefen (status.cmd)! [%TS%]"
:backup_age_ok

REM --- 0) GLOBALER RIEGEL: Gateway aus = Watchdog macht NICHTS ---
REM  Wenn der Nutzer alles gestoppt hat (Strg+C / stop.cmd), darf der Watchdog
REM  nichts wiederbeleben - sonst kaemen Ollama/WeKnora/SearXNG/Reranker zurueck.
REM  Der Watchdog haelt also NUR den LAUFENDEN Stack gesund, weckt ihn aber nie auf.
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',18789); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [%TS%] INFO: Gateway aus - Watchdog macht nichts ^(alles bleibt gestoppt, spart Strom^). >> "%LOG%"
    goto end
)

REM --- 1) OLLAMA (11434) - NUR neu starten wenn das Gateway laeuft ---
REM  WICHTIG: Ollama soll Strom/VRAM nur verbrauchen, wenn das Gateway es braucht.
REM  Frueher startete der Watchdog Ollama bedingungslos -> nach Strg+C kam Ollama
REM  alle 5 Min wieder ("spannt dauernd wieder"). Jetzt: Gateway aus = Ollama bleibt aus.
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',18789); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [%TS%] INFO: Gateway aus - Ollama wird NICHT gestartet ^(gewollt, spart Strom^). >> "%LOG%"
    goto ollama_ok
)
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto ollama_ok
echo [%TS%] ALARM: Ollama (11434) ausgefallen obwohl Gateway laeuft - Neustart ... >> "%LOG%"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    start "Watchdog-Ollama" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
) else (
    start "Watchdog-Ollama" /min ollama serve
)
call :tg_alarm "WATCHDOG: Ollama (11434) ausgefallen - Neustart [%TS%]"
:ollama_ok

REM --- 2) GATEWAY (18789) - nur Alarm, kein Auto-Restart (max 1x/Stunde) ---
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',18789); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto gw_ok
set "GW_SEM=%TEMP%\wdg_gateway.tmp"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyyMMddHH\""') do set "GWHOUR=%%i"
set "GW_PREV="
if exist "%GW_SEM%" set /p GW_PREV=<"%GW_SEM%"
if not "%GW_PREV%"=="%GWHOUR%" (
    echo [%TS%] ALARM: Gateway ^(18789^) nicht erreichbar. >> "%LOG%"
    echo %GWHOUR%>"%GW_SEM%"
    call :tg_alarm "WATCHDOG: Gateway (18789) nicht erreichbar! Bitte gateway.cmd neu starten. [%TS%]"
) else (
    echo [%TS%] INFO: Gateway ^(18789^) immer noch unten - Alarm bereits gesendet diese Stunde. >> "%LOG%"
)
:gw_ok

REM --- 3) WeKnora (8080) - docker compose up bei Ausfall, 10-Min-Cooldown ---
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:8080/health' -TimeoutSec 3 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto weknora_ok
docker info >nul 2>&1
if errorlevel 1 goto weknora_ok
set "WK_SEM=%TEMP%\wdg_weknora.tmp"
if not exist "%WK_SEM%" goto wk_restart
powershell -NoProfile -Command "if((New-TimeSpan -Start (Get-Item '%WK_SEM%').LastWriteTime -End (Get-Date)).TotalMinutes -lt 10){exit 1}else{exit 0}" >nul 2>&1
if not errorlevel 1 goto wk_restart
echo [%TS%] INFO: WeKnora startet noch - Restart vor weniger als 10 Min. >> "%LOG%"
goto weknora_ok
:wk_restart
echo [%TS%] ALARM: WeKnora (8080) ausgefallen - compose restart ... >> "%LOG%"
docker compose --project-directory "%WK%" -f "%WK%/docker-compose.yml" --profile qdrant up -d >nul 2>&1
echo .>"%WK_SEM%"
call :tg_alarm "WATCHDOG: WeKnora (8080) ausgefallen - Docker-Restart [%TS%]"
:weknora_ok

REM --- 4) SearXNG (8888) - bei Ausfall docker compose up ---
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:8888' -TimeoutSec 3 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto searxng_ok
docker info >nul 2>&1
if errorlevel 1 goto searxng_ok
set "SX_SEM=%TEMP%\wdg_searxng.tmp"
if not exist "%SX_SEM%" goto sx_restart
powershell -NoProfile -Command "if((New-TimeSpan -Start (Get-Item '%SX_SEM%').LastWriteTime -End (Get-Date)).TotalMinutes -lt 10){exit 1}else{exit 0}" >nul 2>&1
if not errorlevel 1 goto sx_restart
echo [%TS%] INFO: SearXNG startet noch. >> "%LOG%"
goto searxng_ok
:sx_restart
echo [%TS%] INFO: SearXNG (8888) nicht erreichbar - compose restart ... >> "%LOG%"
docker compose --project-directory "%MATRIX_ROOT%\searxng" up -d >nul 2>&1
echo .>"%SX_SEM%"
:searxng_ok

REM --- 5) Reranker (8011) - nur einmal pro Stunde loggen ---
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8011); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto rerank_ok
set "SEMAPHORE=%TEMP%\wdg_rerank.tmp"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyyMMddHH\""') do set "HOUR=%%i"
set "PREV="
if exist "%SEMAPHORE%" set /p PREV=<"%SEMAPHORE%"
if not "%PREV%"=="%HOUR%" (
    echo [%TS%] INFO: Reranker ^(8011^) nicht erreichbar. >> "%LOG%"
    echo %HOUR%>"%SEMAPHORE%"
)
:rerank_ok

echo [%TS%] Watchdog-Check abgeschlossen. >> "%LOG%"

REM Log-Rotation: max 500 Zeilen behalten
powershell -NoProfile -Command "if(Test-Path '%LOG%'){$l=Get-Content '%LOG%';if($l.Count -gt 500){$l[-500..-1]|Set-Content '%LOG%'}}" >nul 2>&1

goto end

:tg_alarm
powershell -NoProfile -Command "try{ Invoke-RestMethod 'https://api.telegram.org/bot%TGTOKEN%/sendMessage' -Method Post -Body @{chat_id='%TGCHAT%';text='%~1'} | Out-Null }catch{}" >nul 2>&1
exit /b 0

:end
endlocal
