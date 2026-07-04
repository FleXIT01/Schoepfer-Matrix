@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - ZENTRALE UMGEBUNG (von allen .cmd geladen)
REM  Aufruf am Skriptanfang:  call "%~dp0env.cmd"
REM  Setzt: MATRIX_ROOT (= Ordner dieser Datei), laedt matrix.env
REM  und secrets.env (KEY=VALUE, # = Kommentar), Defaults fuer
REM  PYTHON_EXE und BACKUP_DEST.
REM  KEINE Secrets in Skripten - alles kommt aus secrets.env!
REM  WICHTIG: CRLF-Zeilenenden (Windows).
REM ============================================================
set "MATRIX_ROOT=%~dp0"
if "%MATRIX_ROOT:~-1%"=="\" set "MATRIX_ROOT=%MATRIX_ROOT:~0,-1%"

if exist "%MATRIX_ROOT%\matrix.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%MATRIX_ROOT%\matrix.env") do set "%%A=%%B"
)
if exist "%MATRIX_ROOT%\secrets.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%MATRIX_ROOT%\secrets.env") do set "%%A=%%B"
)

REM ---- Defaults (nur wenn nicht in matrix.env gesetzt) ----
if not defined PYTHON_EXE (
    if exist "C:\Python314\python.exe" (
        set "PYTHON_EXE=C:\Python314\python.exe"
    ) else (
        set "PYTHON_EXE=python"
    )
)
if not defined BACKUP_DEST set "BACKUP_DEST=%MATRIX_ROOT%\_backups"
