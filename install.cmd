@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - INSTALLATION (fuer neue Systeme)
REM  Prueft Voraussetzungen, richtet Konfiguration ein, macht
REM  das System startklar. Idempotent - mehrfach ausfuehrbar.
REM  Reihenfolge:
REM    1) Voraussetzungen (Python, Node, Ollama)
REM    2) Python-Pakete + truststore/sitecustomize (Antivirus-MITM-Fix)
REM    3) matrix.env + secrets.env aus Vorlagen
REM    4) openclaw.json aus Template (Pfade auf DIESEN Ordner umgeschrieben)
REM    5) Ollama-Modell gpt-oss-32k (num_ctx 49152)
REM    6) Hintergrund-Tasks registrieren
REM  WICHTIG: CRLF-Zeilenenden (Windows).
REM ============================================================
setlocal EnableExtensions
set "MATRIX_ROOT=%~dp0"
if "%MATRIX_ROOT:~-1%"=="\" set "MATRIX_ROOT=%MATRIX_ROOT:~0,-1%"
title Schoepfer-Matrix Installation
set "ERRS=0"

echo ============================================================
echo   SCHOEPFER-MATRIX INSTALLATION
echo   Zielordner: %MATRIX_ROOT%
echo ============================================================
echo.

REM ---------- 1) VORAUSSETZUNGEN ----------
echo [1/6] Voraussetzungen pruefen ...

REM Python finden: matrix.env-Wert, sonst py/python
set "PYTHON_EXE="
if exist "%MATRIX_ROOT%\matrix.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%MATRIX_ROOT%\matrix.env") do (
        if "%%A"=="PYTHON_EXE" set "PYTHON_EXE=%%B"
    )
)
if not defined PYTHON_EXE set "PYTHON_EXE=python"
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo   [FEHLER] Python nicht gefunden. Python 3.12+ installieren: https://www.python.org/downloads/
    echo            Danach ggf. PYTHON_EXE in matrix.env setzen.
    set /a ERRS+=1
) else (
    for /f "tokens=2" %%v in ('%PYTHON_EXE% --version 2^>^&1') do echo   [ok] Python %%v  (%PYTHON_EXE%)
)

node --version >nul 2>&1
if errorlevel 1 (
    echo   [FEHLER] Node.js nicht gefunden. Node 22+ installieren: https://nodejs.org/
    set /a ERRS+=1
) else (
    for /f %%v in ('node --version') do echo   [ok] Node %%v
)

ollama --version >nul 2>&1
if errorlevel 1 (
    echo   [FEHLER] Ollama nicht gefunden. Installieren: https://ollama.com/download
    set /a ERRS+=1
) else (
    echo   [ok] Ollama installiert.
)

docker --version >nul 2>&1
if errorlevel 1 (
    echo   [i]  Docker nicht gefunden - RAG/WeKnora/SearXNG bleiben aus. Bot laeuft trotzdem.
) else (
    echo   [ok] Docker vorhanden.
)

if not exist "%MATRIX_ROOT%\openclaw-main\openclaw.mjs" (
    echo   [FEHLER] OpenClaw fehlt: openclaw-main\openclaw.mjs nicht gefunden.
    echo            OpenClaw-Release nach %MATRIX_ROOT%\openclaw-main\ entpacken ^(siehe INSTALL.md^).
    set /a ERRS+=1
) else (
    echo   [ok] OpenClaw vorhanden.
)

if %ERRS% GTR 0 (
    echo.
    echo [!] %ERRS% Voraussetzung^(en^) fehlen - bitte beheben und install.cmd erneut ausfuehren.
    pause
    goto end
)
echo.

REM ---------- 2) PYTHON-PAKETE + TRUSTSTORE ----------
echo [2/6] Python-Pakete installieren ...
%PYTHON_EXE% -m pip install -r "%MATRIX_ROOT%\requirements.txt" --quiet
%PYTHON_EXE% -m pip install truststore mcp httpx pyyaml --quiet
echo   [ok] pip-Pakete installiert.
REM Antivirus-HTTPS-Inspektion (Avast & Co.): truststore laesst Python die
REM WINDOWS-Zertifikatpruefung nutzen, sonst scheitern alle HTTPS-Calls.
REM Lazy-Variante aus dem Repo (pip>=25 injiziert selbst -> RecursionError);
REM ersetzt auch die alte Direkt-Inject-Version, fremde Dateien bleiben unangetastet.
%PYTHON_EXE% -c "import site, pathlib, shutil; src = pathlib.Path(r'%MATRIX_ROOT%') / 'sitecustomize.py'; sc = pathlib.Path(site.getusersitepackages()) / 'sitecustomize.py'; sc.parent.mkdir(parents=True, exist_ok=True); cur = sc.read_text(encoding='utf-8') if sc.exists() else ''; (not cur or ('inject_into_ssl' in cur and 'LazyTruststore' not in cur)) and shutil.copyfile(src, sc); print('  [ok] sitecustomize:', sc)"
echo.

REM ---------- 3) KONFIG-DATEIEN AUS VORLAGEN ----------
echo [3/6] Konfiguration einrichten ...
if not exist "%MATRIX_ROOT%\matrix.env" (
    copy /Y "%MATRIX_ROOT%\matrix.env.template" "%MATRIX_ROOT%\matrix.env" >nul
    echo   [!] matrix.env angelegt - bitte PYTHON_EXE/BACKUP_DEST pruefen.
) else (
    echo   [ok] matrix.env vorhanden.
)
if not exist "%MATRIX_ROOT%\secrets.env" (
    copy /Y "%MATRIX_ROOT%\secrets.env.template" "%MATRIX_ROOT%\secrets.env" >nul
    echo   [!] secrets.env angelegt - JETZT Telegram-Token + Chat-ID eintragen!
) else (
    echo   [ok] secrets.env vorhanden.
)
echo.

REM ---------- 4) OPENCLAW.JSON ----------
echo [4/6] openclaw.json einrichten ...
if not exist "%MATRIX_ROOT%\openclaw-workspace\state" mkdir "%MATRIX_ROOT%\openclaw-workspace\state" 2>nul
if not exist "%MATRIX_ROOT%\openclaw-workspace\output" mkdir "%MATRIX_ROOT%\openclaw-workspace\output" 2>nul
if exist "%MATRIX_ROOT%\openclaw-workspace\state\openclaw.json" (
    echo   [ok] openclaw.json existiert - bleibt unangetastet.
) else (
    %PYTHON_EXE% -c "import re,sys; root=r'%MATRIX_ROOT%'; t=open(root+r'\openclaw.json.template',encoding='utf-8').read(); t=re.sub(r'(?i)n:[\\\\/]+allinall', root.replace(chr(92),'/'), t); t=re.sub(r'(?i)C:/+Python314/python.exe|C:\\\\Python314\\\\python.exe', 'python', t); open(root+r'\openclaw-workspace\state\openclaw.json','w',encoding='utf-8').write(t); print('  [ok] openclaw.json aus Template erzeugt (Pfade angepasst).')"
)
REM Secrets aus secrets.env einspielen (Platzhalter ersetzen)
%PYTHON_EXE% "%MATRIX_ROOT%\sync_secrets.py"
echo.

REM ---------- 5) OLLAMA-MODELL ----------
echo [5/6] Ollama-Modell gpt-oss-32k (49k-Kontext) ...
ollama list 2>nul | findstr /i "gpt-oss-32k" >nul
if not errorlevel 1 (
    echo   [ok] gpt-oss-32k vorhanden.
    goto model_ok
)
echo   [..] lade Basismodell gpt-oss:20b (~13 GB, dauert je nach Leitung) ...
ollama pull gpt-oss:20b
if errorlevel 1 (
    echo   [FEHLER] ollama pull fehlgeschlagen - Internet/Ollama pruefen.
    set /a ERRS+=1
    goto model_ok
)
echo   [..] erzeuge gpt-oss-32k mit num_ctx 49152 ...
> "%TEMP%\Modelfile.matrix" echo FROM gpt-oss:20b
>>"%TEMP%\Modelfile.matrix" echo PARAMETER num_ctx 49152
ollama create gpt-oss-32k -f "%TEMP%\Modelfile.matrix"
del "%TEMP%\Modelfile.matrix" 2>nul
echo   [ok] gpt-oss-32k erzeugt.
:model_ok
echo.

REM ---------- 6) HINTERGRUND-TASKS ----------
echo [6/6] Hintergrund-Tasks registrieren (Backup/Watchdog/Briefing/Eval/...) ...
call "%MATRIX_ROOT%\register_tasks.cmd" >nul 2>&1
echo   [ok] Tasks registriert.
echo.

echo ============================================================
echo   INSTALLATION ABGESCHLOSSEN.
echo   NAECHSTE SCHRITTE:
echo     1) secrets.env ausfuellen (Telegram-Token + Chat-ID minimum)
echo     2) matrix.env pruefen (PYTHON_EXE, BACKUP_DEST)
echo     3) START:  gateway.cmd     STOPP: Strg+C oder stop.cmd
echo     4) STATUS: status.cmd
echo ============================================================
pause

:end
endlocal
