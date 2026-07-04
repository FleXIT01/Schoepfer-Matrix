@echo off
REM ============================================================
REM  ComfyUI starten (On-Demand-Bilddienst der Schoepfer-Matrix)
REM  Die mitgelieferte run_nvidia_gpu.bat zeigt auf ein altes
REM  V:-Laufwerk; dieser Launcher nutzt den korrekten N:-Pfad.
REM
REM  WICHTIG (16 GB VRAM): ComfyUI und das 14-GB-LLM passen NICHT
REM  gleichzeitig komplett in die GPU. Fuer reine Bildgenerierung
REM  ggf. vorher das LLM entladen:  ollama stop gpt-oss-32k
REM  ComfyUI laeuft dann auf http://127.0.0.1:8188
REM ============================================================
setlocal
call "%~dp0env.cmd"
set "CU=%MATRIX_ROOT%\ComfyUI_portable\ComfyUI_windows_portable_nvidia_cu128\ComfyUI_windows_portable"
title Schoepfer-Matrix ComfyUI

REM ---- VRAM freigeben: alle Ollama-Modelle entladen ----
echo [..] Entlade Ollama-Modelle aus dem VRAM (fuer ComfyUI) ...
%PYTHON_EXE% -c "import httpx,sys; r=httpx.get('http://localhost:11434/api/ps',timeout=5); ms=r.json().get('models',[]); [httpx.post('http://localhost:11434/api/generate',json={'model':m['name'],'keep_alive':0},timeout=15) for m in ms]; print(f'  [{len(ms)} Modell(e) entladen]') if ms else print('  [VRAM bereits frei]')" 2>nul || echo   [Ollama nicht aktiv - OK]
echo.

echo Starte ComfyUI auf http://127.0.0.1:8188 ... Fenster offen lassen.
echo (Strg+C zum Beenden.)
echo ------------------------------------------------------------
"%CU%\python_embeded\python.exe" -s "%CU%\ComfyUI\main.py" --windows-standalone-build --port 8188
echo.
echo [!] ComfyUI beendet.
pause
endlocal
