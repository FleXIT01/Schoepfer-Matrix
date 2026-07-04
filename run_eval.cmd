@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - Eval-Suite Runner (V18)
REM  Fuehrt die GOLDEN-Harness aus (eval/golden.py, geseedet,
REM  Diff gegen golden_baseline.json). Die alte runner.py/tests.yaml
REM  nutzte den kaputten 'openclaw agent --local'-Pfad -> ersetzt.
REM
REM  Verhalten (V18):
REM    - Ollama aus?  -> wird TEMPORAER gestartet, Eval laeuft, danach
REM                      wird NUR das selbst gestartete Ollama wieder
REM                      gestoppt (und nur, wenn kein Gateway laeuft).
REM    - Ollama an?   -> mitbenutzen, danach NICHT anfassen (gehoert
REM                      dem Gateway oder dem Nutzer).
REM    - Regression?  -> Telegram-Alarm + Exit 1.
REM  Nutzung:  run_eval.cmd [golden.py-Argumente, z.B. --profile core]
REM  WICHTIG: CRLF-Zeilenenden (Windows).
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"
set "ROOT=%MATRIX_ROOT%"
set "EVAL=%MATRIX_ROOT%\eval"
set "LOG=%EVAL%\results\nightly_golden.log"
REM UTF-8 erzwingen: golden.py druckt Emojis; bei Log-Umleitung nimmt Python sonst
REM cp1252 -> UnicodeEncodeError -> falscher Regression-Alarm.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd_HHmm\""') do set "TS=%%i"

REM -- Telegram-Zugangsdaten aus secrets.env laden --
if exist "%ROOT%\secrets.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%\secrets.env") do (
        if "%%A"=="TELEGRAM_BOT_TOKEN"       set "TGTOKEN=%%B"
        if "%%A"=="TELEGRAM_DEFAULT_CHAT_ID" set "TGCHAT=%%B"
    )
)

echo ============================================================
echo   SCHOEPFER-MATRIX GOLDEN-EVAL  (Baseline-Diff, Seed 42)
echo ============================================================

REM -- Ollama-Lebenszyklus: laeuft es schon, mitbenutzen; sonst temporaer starten --
set "WE_STARTED_OLLAMA="
powershell -NoProfile -Command "try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -UseBasicParsing; exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 goto ollama_ready

echo [i] Ollama aus - starte temporaer fuer den Eval ...
echo [%TS%] Ollama aus - temporaerer Start fuer Eval. >> "%LOG%"
REM Gleiche VRAM-Flags wie gateway.cmd: andere Flags = andere Numerik = das Modell
REM routet bei temperature 0 ANDERS -> Baseline-Vergleich sonst wertlos.
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_KV_CACHE_TYPE=q8_0"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    start "Eval-Ollama" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
) else (
    start "Eval-Ollama" /min ollama serve
)
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 20;$i++){ try{ $null=Invoke-WebRequest 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 -UseBasicParsing; $ok=$true; break }catch{ Start-Sleep -Seconds 3 } }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
    echo [%TS%] SKIP: Ollama liess sich nicht starten - Eval uebersprungen. >> "%LOG%"
    echo [!] Ollama-Start fehlgeschlagen - Eval uebersprungen. Kein Fehler.
    endlocal
    exit /b 0
)
set "WE_STARTED_OLLAMA=1"
:ollama_ready

REM -- Golden-Harness ausfuehren, Ausgabe ins Log --
echo [%TS%] Golden-Eval Start ... >> "%LOG%"
%PYTHON_EXE% "%EVAL%\golden.py" %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [%TS%] Golden-Eval Ende, Exit=%RC% >> "%LOG%"

if "%RC%"=="0" (
    echo [ok] Keine Regression gegen die Baseline.
    goto done
)

echo [!!] REGRESSION erkannt ^(Exit %RC%^) - sende Telegram-Alarm ...
if defined TGTOKEN powershell -NoProfile -Command "try{ Invoke-RestMethod ('https://api.telegram.org/bot'+$env:TGTOKEN+'/sendMessage') -Method Post -Body @{chat_id=$env:TGCHAT;text='EVAL-ALARM: Golden-Suite hat eine REGRESSION gefunden. Details: eval\results\nightly_golden.log'} | Out-Null }catch{}" >nul 2>&1

:done
REM -- Aufraeumen: NUR das selbst gestartete Ollama stoppen, und NUR wenn kein
REM    Gateway laeuft (laeuft eins, gehoert Ollama ihm - Finger weg). Lief Ollama
REM    schon vor dem Eval (Nutzer/Gateway), wird es NIE angefasst.
if not defined WE_STARTED_OLLAMA goto rotate
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',18789); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [%TS%] Ollama bleibt an: Gateway laeuft inzwischen. >> "%LOG%"
    goto rotate
)
powershell -NoProfile -Command "Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'ollama*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
echo [%TS%] Temporaeres Ollama nach Eval wieder gestoppt (VRAM/Strom frei). >> "%LOG%"
echo [ok] Temporaeres Ollama wieder gestoppt.

:rotate
REM Log-Rotation: max 400 Zeilen
powershell -NoProfile -Command "if(Test-Path '%LOG%'){$l=Get-Content '%LOG%';if($l.Count -gt 400){$l[-400..-1]|Set-Content '%LOG%'}}" >nul 2>&1
endlocal & exit /b %RC%
