@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX — BOOTSTRAP (V14: Setup als Code)
REM  Alles was gebraucht wird, auf einem frischen Windows-System.
REM  Stand: 2026-06-12  Basis: n:\allinall
REM
REM  AUSFUEHREN: Als normaler User (KEIN Admin noetig ausser winget).
REM  VORBEDINGUNG: Windows 10/11, Netzwerkzugang.
REM ============================================================
setlocal EnableExtensions
set "ROOT=n:\allinall"
set "PYTHON=C:\Python314\python.exe"
set "NODE=node"

echo ============================================================
echo   SCHOEPFER-MATRIX BOOTSTRAP
echo   Richtet alle Abhaengigkeiten auf einem frischen System ein.
echo ============================================================
echo.

REM -------- 0) Paketmanager pruefen ----------------------------
echo [0] Pruefe Voraussetzungen ...
where winget >nul 2>&1
if errorlevel 1 (
    echo [!] winget nicht gefunden. Windows-Version >= 10 1809 und
    echo     App Installer aus dem Microsoft Store installieren.
    pause & exit /b 1
)
echo     [ok] winget gefunden.
echo.

REM -------- 1) Kern-Tools via winget ---------------------------
echo [1] Installiere Kern-Tools (winget) ...

echo     Node.js LTS ...
winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements
echo     Python 3.14 ...
winget install --id Python.Python.3.14 -e --silent --accept-package-agreements --accept-source-agreements
echo     Git ...
winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
echo     Ollama ...
winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
echo     Docker Desktop ...
winget install --id Docker.DockerDesktop -e --silent --accept-package-agreements --accept-source-agreements
echo     FFmpeg (fuer Voice/Whisper) ...
winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements
echo     AutoHotkey v2 (NOT-AUS Hotkey Ctrl+Alt+N/M) ...
winget install --id AutoHotkey.AutoHotkey -e --silent --accept-package-agreements --accept-source-agreements
echo.
echo     [ok] Kern-Tools installiert. NEUSTART evtl. erforderlich!
echo.

REM -------- 2) Python-Pakete -----------------------------------
echo [2] Installiere Python-Pakete ...
%PYTHON% -m pip install --upgrade pip --quiet
%PYTHON% -m pip install --quiet ^
    mcp httpx fastmcp ^
    requests ^
    python-docx python-pptx openpyxl ^
    pypdf ^
    faster-whisper ^
    piper-tts ^
    rdkit-pypi ^
    py3Dmol ^
    jinja2 ^
    python-dotenv ^
    playwright ^
    pyotp ^
    mss
echo     Playwright-Browser (Chromium) installieren ...
%PYTHON% -m playwright install chromium
echo     [ok] Python-Pakete installiert.
echo.

REM -------- 3) Node-Pakete (OpenClaw) --------------------------
echo [3] Installiere Node-Abhaengigkeiten (OpenClaw) ...
if exist "%ROOT%\openclaw-main\package.json" (
    pushd "%ROOT%\openclaw-main"
    npm install --silent
    popd
    echo     [ok] OpenClaw npm install fertig.
) else (
    echo     [!] openclaw-main nicht gefunden unter %ROOT%\openclaw-main
    echo         Bitte Repo klonen/kopieren und dann erneut ausfuehren.
)
echo.

REM -------- 4) Ollama-Modelle ----------------------------------
echo [4] Lade Ollama-Modelle (kann lange dauern) ...
echo     gpt-oss-32k (Hauptmodell, ~14 GB) ...
ollama pull hf.co/mradermacher/gpt-oss-Q4_K_M-GGUF:Q4_K_M 2>nul
echo     codestral (Code, ~12 GB) ...
ollama pull codestral:latest 2>nul
echo     qwen2.5:7b (schnell/routing) ...
ollama pull qwen2.5:7b 2>nul
echo.
echo     OPTIONAL (brauchen ~16 GB VRAM — separat):
echo       ollama pull qwen3-vl:32b   (Vision/OCR)
echo       ollama pull qwen3:32b      (Reasoning-Alternative)
echo.

REM -------- 5) Env-Variablen -----------------------------------
echo [5] Setze VRAM-Optimierungs-Variablen ...
setx OLLAMA_FLASH_ATTENTION 1 >nul
setx OLLAMA_KV_CACHE_TYPE q8_0 >nul
echo     [ok] OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0

echo     OpenClaw-Config-Pfad ...
setx OPENCLAW_CONFIG_PATH "n:\allinall\openclaw-workspace\state\openclaw.json" >nul
echo     [ok] OPENCLAW_CONFIG_PATH gesetzt.
echo.

REM -------- 6) Secrets einrichten ------------------------------
echo [6] Secrets ...
if not exist "%ROOT%\secrets.env" (
    echo     [!] n:\allinall\secrets.env fehlt!
    echo     Vorlage anlegen — bitte folgende Werte selbst eintragen:
    (
        echo OPENROUTER_API_KEY=
        echo TELEGRAM_BOT_TOKEN=
        echo TELEGRAM_DEFAULT_CHAT_ID=
        echo WEKNORA_API_KEY=
        echo WEKNORA_BASE_URL=http://localhost:8080/api/v1
        echo WEKNORA_KB_ID=
        echo OPENCLAW_GATEWAY_TOKEN=
        echo GITHUB_TOKEN=
    ) > "%ROOT%\secrets.env"
    echo     Vorlage erstellt: %ROOT%\secrets.env — Werte eintragen, dann:
    echo       python n:\allinall\sync_secrets.py
) else (
    echo     [ok] secrets.env vorhanden.
    %PYTHON% "%ROOT%\sync_secrets.py"
    echo     [ok] secrets nach openclaw.json synchronisiert.
)
echo.

REM -------- 7) Scheduled Tasks ---------------------------------
echo [7] Registriere Windows Scheduled Tasks ...
call "%ROOT%\register_tasks.cmd" >nul 2>&1
if not errorlevel 1 (
    echo     [ok] Tasks registriert.
) else (
    echo     [!] Tasks-Registrierung fehlgeschlagen (evtl. Admin noetig).
    echo         Manuell: register_tasks.cmd als Admin ausfuehren.
)
echo.

REM -------- 8) Autostart-Verknuepfung -------------------------
echo [8] Autostart (gateway.cmd) ...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%\Schoepfer-Matrix.lnk" (
    powershell -NoProfile -Command ^
        "$WS=New-Object -COM WScript.Shell; $LNK=$WS.CreateShortcut('%STARTUP%\Schoepfer-Matrix.lnk'); $LNK.TargetPath='n:\allinall\gateway.cmd'; $LNK.WorkingDirectory='n:\allinall'; $LNK.Save()"
    echo     [ok] Autostart-Verknuepfung erstellt.
) else (
    echo     [ok] Autostart-Verknuepfung existiert bereits.
)
echo     NOT-AUS Hotkey (notaus.ahk) in Autostart eintragen ...
if not exist "%STARTUP%\Schoepfer-Matrix-NotAus.lnk" (
    powershell -NoProfile -Command ^
        "$WS=New-Object -COM WScript.Shell; $LNK=$WS.CreateShortcut('%STARTUP%\Schoepfer-Matrix-NotAus.lnk'); $LNK.TargetPath='n:\allinall\notaus.ahk'; $LNK.WorkingDirectory='n:\allinall'; $LNK.Save()"
    echo     [ok] NOT-AUS Hotkey (Ctrl+Alt+N/M) im Autostart.
) else (
    echo     [ok] NOT-AUS Autostart existiert bereits.
)
echo.

REM -------- 9) Verzeichnisse -----------------------------------
echo [9] Erstelle fehlende Verzeichnisse ...
for %%D in (
    "n:\allinall\repos"
    "n:\allinall\openclaw-workspace\output"
    "n:\allinall\openclaw-workspace\output\screenshots"
    "n:\allinall\openclaw-workspace\output\browser-sessions"
    "n:\allinall\openclaw-workspace\browser-profile"
    "n:\allinall\openclaw-workspace\state"
    "n:\allinall\searxng\searxng-data"
) do (
    if not exist %%D md %%D 2>nul
)
echo     [ok] Verzeichnisse bereit.
echo.

REM -------- FERTIG --------------------------------------------
echo ============================================================
echo   BOOTSTRAP ABGESCHLOSSEN
echo.
echo   Naechste Schritte:
echo     1. secrets.env pruefen + ausfuellen (falls neu angelegt)
echo     2. python sync_secrets.py ausfuehren
echo     3. mailcfg.cmd ausfuehren (SMTP-Passwort einrichten)
echo     4. Docker starten und einmal WeKnora manuell hochfahren
echo     5. gateway.cmd starten  ->  Bot online!
echo.
echo   Optionale Modelle (separat holen wenn VRAM reicht):
echo     ollama pull qwen3-vl:32b
echo ============================================================
pause
endlocal
