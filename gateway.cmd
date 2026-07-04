@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - EIN START FUER ALLES (All-in-One)
REM    1) Ollama   2) Docker+WeKnora-RAG   3) BGE-Reranker
REM    4) ComfyUI  5) Gateway (Telegram-Bot @pc_projekt_Bot)
REM  Schritt 2-4 sind best-effort: fehlt etwas, laeuft der Bot
REM  trotzdem. Gateway ist SELBSTHEILEND (Neustart bei Absturz).
REM  WICHTIG: Diese Datei MUSS CRLF-Zeilenenden haben (Windows).
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"
set "ROOT=%MATRIX_ROOT%"
set "OPENCLAW_STATE_DIR=%MATRIX_ROOT%/openclaw-workspace/state"
REM AGENT_DIR fest auf den (von OpenClaw migrierten) Pfad -> settings.json/Reserve 6144 wird
REM zuverlaessig gelesen (sonst verschiebt die Auto-Migration die Datei weg -> Overflow).
set "OPENCLAW_AGENT_DIR=%USERPROFILE%\.openclaw\agents\main\agent"
REM IPv4 erzwingen: dieser PC loest api.telegram.org zuerst auf IPv6 auf, hat aber
REM keine funktionierende IPv6-Route (viele virtuelle Adapter) -> EHOSTUNREACH ->
REM Gateway-Absturz. ipv4first behebt das.
set "NODE_OPTIONS=--dns-result-order=ipv4first"
set "WK=%MATRIX_ROOT%/WeKnora-main"
set "GWLOG=%MATRIX_ROOT%\openclaw-workspace\output\gateway-exit.log"
title Schoepfer-Matrix (All-in-One)

echo ============================================================
echo   SCHOEPFER-MATRIX  -  startet ALLES  Bot: @pc_projekt_Bot
echo ============================================================
echo.

REM ---------- VRAM-Optimierungen (Flash-Attention + KV-Cache q8_0) ----------
REM  Flash-Attention: ~30% schneller bei langen Kontexten, halber VRAM-Bedarf
REM  KV-Cache q8_0:   halbiert KV-Speicher bei 49k-Kontext, Qualitaet pratisch gleich
set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_KV_CACHE_TYPE=q8_0

REM ---------- SECRETS (secrets.env -> openclaw.json synchronisieren, V8) ----------
if exist "%MATRIX_ROOT%\secrets.env" (
    %PYTHON_EXE% %MATRIX_ROOT%\sync_secrets.py
)

REM ---------- 0) SCHEDULED TASKS (kein Admin noetig seit v2-vbs) ----------
echo [0/5] Pruefe Scheduled Tasks ...
if exist "%MATRIX_ROOT%\openclaw-workspace\state\tasks_v2.txt" goto tasks_ok
echo       [..] Tasks-Marker fehlt - registriere Hintergrund-Tasks ...
call %MATRIX_ROOT%\register_tasks.cmd >nul 2>&1
:tasks_ok
echo       [ok] Scheduled Tasks aktiv.
echo.

REM ---------- 1) OLLAMA (Pflicht) ----------
echo [1/5] Ollama (lokales Hirn) ...
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto ollama_ok
echo       [..] starte Ollama-Server (ollama serve) ...
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" start "Schoepfer-Matrix Ollama" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" start "Schoepfer-Matrix Ollama" /min ollama serve
echo       [..] warte auf Ollama (max 60s) ...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 20;$i++){ try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -UseBasicParsing; $ok=$true; break }catch{ Start-Sleep -Seconds 3 } }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 goto no_ollama
:ollama_ok
echo       [ok] Ollama laeuft.
echo.

REM ---------- 2) DOCKER + WeKnora-RAG (best effort) ----------
echo [2/5] WeKnora-RAG (Docker) ...
docker info >nul 2>&1
if not errorlevel 1 goto weknora_up
echo       [..] Docker nicht aktiv - versuche Docker Desktop zu starten ...
if not exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" goto rag_skip
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo       [..] warte auf Docker (max 150s) ...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 50;$i++){ docker info *> $null; if($LASTEXITCODE -eq 0){$ok=$true;break}; Start-Sleep -Seconds 3 }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 goto rag_skip
:weknora_up
echo       [..] WeKnora-Stack hochfahren (Profil qdrant) ...
docker compose --project-directory "%WK%" -f "%WK%/docker-compose.yml" --env-file "%WK%/.env" --profile qdrant up -d >nul 2>&1
echo       [ok] WeKnora-RAG laeuft. UI http://localhost  API http://localhost:8080
echo       [..] SearXNG-Suche hochfahren (V13, Port 8888) ...
docker compose --project-directory "%MATRIX_ROOT%\searxng" up -d >nul 2>&1
if errorlevel 1 (
    echo       [i] SearXNG nicht gestartet - DDG/Jina bleibt Fallback.
) else (
    echo       [ok] SearXNG laeuft auf http://localhost:8888
)
echo       [..] Webhook-Server (N4, Port 7890) starten ...
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',7890); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo       [ok] Webhook-Server laeuft bereits auf Port 7890.
) else (
    start "Schoepfer-Matrix Webhook" /min cmd /c "%MATRIX_ROOT%\webhook_server.cmd"
    echo       [ok] Webhook-Server gestartet: http://127.0.0.1:7890
)
echo.
echo [3/5] BGE-Reranker (fuer kb_search) ...
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8011); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto rerank_ok
echo       [..] starte Reranker in eigenem Fenster (erster Start laedt ~2.3 GB) ...
start "Schoepfer-Matrix Reranker" cmd /c "%MATRIX_ROOT%\rerank.cmd"
goto rerank_ok
:rag_skip
echo       [i] Kein Docker - RAG/kb_search bleibt aus, Bot laeuft normal weiter.
:rerank_ok
echo.

REM ---------- 4) COMFYUI (best effort) ----------
echo [4/5] ComfyUI (Bild-Generierung) ...
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8188); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto comfy_ok
echo       [..] starte ComfyUI in eigenem Fenster (Start ~30-60s) ...
start "Schoepfer-Matrix ComfyUI" cmd /c "%MATRIX_ROOT%\comfy.cmd"
:comfy_ok
echo.

REM ---------- 5) GATEWAY (Telegram-Bot) ----------
echo [5/5] Gateway (Telegram-Bot) ...
schtasks /end /tn "OpenClaw Gateway" >nul 2>&1
echo       [..] beende evtl. vorige Gateway-Sitzungen ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match 'openclaw.*gateway run' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
REM Auch den Prozess auf Port 18789 killen (falls anderes Kommando)
powershell -NoProfile -Command "$p=Get-NetTCPConnection -LocalPort 18789 -State Listen -ErrorAction SilentlyContinue; if($p){$pid=$p[0].OwningProcess; if($pid -gt 4){Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue; Write-Host \"       [..] Port-18789-Prozess (PID $pid) beendet.\"}}"
REM Stale Lock-Files aufraumen (Prozesse die nicht mehr laufen)
powershell -NoProfile -Command "$lockDir='C:\Users\' + $env:USERNAME + '\AppData\Local\Temp\openclaw'; Get-ChildItem $lockDir -Filter 'gateway.*.lock' -ErrorAction SilentlyContinue | Where-Object { $true } | ForEach-Object { $null = Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }; Write-Host '       [ok] Alte Lock-Files bereinigt.'"
REM Telegram-Filter auf volle Update-Liste setzen (das Gateway-Polling haelt ihn danach;
REM die fruehere TgCallback-Task setzte ihn auf callback_query und blockierte Textnachrichten -> entfernt).
REM HINWEIS: deleteWebhook setzt den Polling-Filter NICHT zurueck; nur ein getUpdates mit voller Liste tut das.
powershell -NoProfile -Command "$f='[\"message\",\"edited_message\",\"channel_post\",\"edited_channel_post\",\"inline_query\",\"chosen_inline_result\",\"callback_query\",\"shipping_query\",\"pre_checkout_query\",\"poll\",\"poll_answer\",\"my_chat_member\",\"chat_member\",\"chat_join_request\",\"message_reaction\"]'; try{ $null=Invoke-WebRequest -Uri ('https://api.telegram.org/bot%TELEGRAM_BOT_TOKEN%/getUpdates?timeout=0&offset=-1&allowed_updates='+[uri]::EscapeDataString($f)) -UseBasicParsing -ErrorAction Stop; Write-Host '       [ok] Telegram-Filter auf voll gesetzt (message erlaubt).' }catch{ Write-Host '       [i] Telegram-Filter-Set nicht moeglich (kein Internet?).' }"
REM Kurz warten bis Port freigegeben
powershell -NoProfile -Command "Start-Sleep -Seconds 2"
echo.
echo ============================================================
echo   ALLES BEREIT. Gateway startet, Bot in ~10s online.
echo   SELBSTHEILEND: bei Absturz Neustart. Beenden: im Countdown N.
echo ============================================================
echo.

REM ---------- GATEWAY-LOOP (PowerShell-Wrapper) ----------
REM Strg+C beendet Gateway UND Ollama. Reines Batch kann Strg+C nicht abfangen
REM (fragt nur "Batch beenden? J/N"), daher laeuft der Loop in PowerShell mit einem
REM finally-Block, der bei Strg+C Ollama mitstoppt. Selbstheilung bei Absturz drin.
powershell -NoProfile -ExecutionPolicy Bypass -File "%MATRIX_ROOT%\gateway_loop.ps1"
echo.
echo [x] Gateway + Ollama beendet. Fenster bleibt offen.
pause
goto end

:no_ollama
echo.
echo [!] Ollama laeuft nicht (Port 11434) und liess sich nicht starten.
echo     Ollama-App starten und gateway.cmd erneut ausfuehren.
pause
goto end

:end
endlocal
