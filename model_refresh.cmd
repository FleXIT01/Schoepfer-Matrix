@echo off
REM ============================================================
REM  Schoepfer-Matrix Modell-Refresh-Ritual (V11)
REM  Quartalsweise: Kandidaten gegen Eval-Suite fahren,
REM  nur bei Sieg (>= aktuellem Score) tauschen.
REM
REM  Aufruf: model_refresh.cmd <neues_modell>
REM  z.B.:   model_refresh.cmd qwen3:14b
REM          model_refresh.cmd llama3.3:70b
REM ============================================================
setlocal EnableExtensions

set "CANDIDATE=%~1"
set "CURRENT_MODEL=gpt-oss:20b"
set "EVAL_DIR=n:\allinall\eval"
set "RESULTS=n:\allinall\openclaw-workspace\output\model_refresh_result.txt"

if "%CANDIDATE%"=="" (
    echo Aufruf: model_refresh.cmd ^<neues_modell^>
    echo Beispiel: model_refresh.cmd qwen3:14b
    echo.
    echo Verfuegbare Ollama-Modelle:
    ollama list
    goto end
)

echo ============================================================
echo  MODELL-REFRESH-RITUAL (V11)
echo  Kandidat: %CANDIDATE%
echo  Aktuell:  %CURRENT_MODEL%
echo ============================================================
echo.

REM Kandidat pullen falls noch nicht vorhanden
echo [1/4] Pulling %CANDIDATE% ..
ollama pull %CANDIDATE%
if errorlevel 1 (
    echo [!] Fehler beim Pull. Modell-Name pruefen: ollama list
    goto end
)
echo       [ok] Modell verfuegbar.
echo.

REM Eval mit aktuellem Modell (Baseline)
echo [2/4] Eval-Baseline mit %CURRENT_MODEL% ..
set "MATRIX_MODEL=%CURRENT_MODEL%"
C:\Python314\python.exe "%EVAL_DIR%\runner.py" --quiet > "%RESULTS%.baseline.txt" 2>&1
type "%RESULTS%.baseline.txt"
echo.

REM Eval mit Kandidat
echo [3/4] Eval-Test mit %CANDIDATE% ..
set "MATRIX_MODEL=%CANDIDATE%"
C:\Python314\python.exe "%EVAL_DIR%\runner.py" --quiet > "%RESULTS%.candidate.txt" 2>&1
type "%RESULTS%.candidate.txt"
echo.

REM Vergleich ausgeben
echo [4/4] Vergleich:
echo   Baseline (%CURRENT_MODEL%):
type "%RESULTS%.baseline.txt"
echo   Kandidat (%CANDIDATE%):
type "%RESULTS%.candidate.txt"
echo.
echo ENTSCHEIDUNG: Nur tauschen wenn Kandidat >= Baseline-Score!
echo Wenn ja: CURRENT_MODEL in matrix.cmd und openclaw.json aendern.
echo.
echo Ergebnisse gespeichert:
echo   %RESULTS%.baseline.txt
echo   %RESULTS%.candidate.txt

:end
endlocal
