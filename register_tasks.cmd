@echo off
REM ============================================================
REM  SCHOEPFER-MATRIX - Task-Registrierung
REM  Kein Admin noetig. Keine /ru-Option = laeuft als aktuell
REM  eingeloggter Benutzer (interaktive Session).
REM
REM    1) SchoepferMatrix-Backup          taeglich 02:30
REM    2) SchoepferMatrix-Watchdog        alle 5 Minuten
REM    3) SchoepferMatrix-Eval            taeglich 03:15
REM    4) SchoepferMatrix-Briefing        taeglich 07:00  (N1)
REM    5) SchoepferMatrix-MailPoll        alle 5 Minuten  (N5)
REM    6) SchoepferMatrix-Retro           Sonntags 20:00  (N9)
REM  (ENTFERNT) SchoepferMatrix-TgCallback - war ZWEITER Telegram-Poller,
REM  setzte allowed_updates=callback_query und BLOCKIERTE alle Textnachrichten.
REM ============================================================
setlocal EnableExtensions
call "%~dp0env.cmd"

set "ROOT=%MATRIX_ROOT%"
set "VBS=%MATRIX_ROOT%\run_hidden.vbs"
set "MARKER=%MATRIX_ROOT%\openclaw-workspace\state\tasks_v2.txt"

echo ============================================================
echo   Schoepfer-Matrix - Task-Registrierung (Hintergrund-Modus)
echo ============================================================
echo.

REM Alte Tasks loeschen (ignoriert Fehler wenn nicht vorhanden)
schtasks /delete /tn "SchoepferMatrix-Backup"      /f >nul 2>&1
schtasks /delete /tn "SchoepferMatrix-Watchdog"    /f >nul 2>&1
schtasks /delete /tn "SchoepferMatrix-Eval"        /f >nul 2>&1
schtasks /delete /tn "SchoepferMatrix-Briefing"    /f >nul 2>&1
schtasks /delete /tn "SchoepferMatrix-MailPoll"    /f >nul 2>&1
schtasks /delete /tn "SchoepferMatrix-Retro"       /f >nul 2>&1
schtasks /delete /tn "SchoepferMatrix-TgCallback"  /f >nul 2>&1

echo [1/7] Backup-Task ...
schtasks /create /tn "SchoepferMatrix-Backup"      /tr "wscript.exe //B //Nologo \"%VBS%\" \"%ROOT%\backup.cmd\""           /sc daily  /st 02:30       /f >nul 2>&1
if errorlevel 1 (echo [FEHLER] Backup.) else (echo [ok] Backup: taeglich 02:30)

echo [2/7] Watchdog-Task ...
schtasks /create /tn "SchoepferMatrix-Watchdog"    /tr "wscript.exe //B //Nologo \"%VBS%\" \"%ROOT%\watchdog.cmd\""         /sc minute /mo 5           /f >nul 2>&1
if errorlevel 1 (echo [FEHLER] Watchdog.) else (echo [ok] Watchdog: alle 5 Minuten)

echo [3/7] Eval-Task ...
schtasks /create /tn "SchoepferMatrix-Eval"        /tr "wscript.exe //B //Nologo \"%VBS%\" \"%ROOT%\run_eval.cmd\""         /sc daily  /st 03:15       /f >nul 2>&1
if errorlevel 1 (echo [FEHLER] Eval.) else (echo [ok] Eval: taeglich 03:15)

echo [4/7] Briefing-Task ...
schtasks /create /tn "SchoepferMatrix-Briefing"    /tr "wscript.exe //B //Nologo \"%VBS%\" \"%ROOT%\briefing.cmd\""         /sc daily  /st 07:00       /f >nul 2>&1
if errorlevel 1 (echo [FEHLER] Briefing.) else (echo [ok] Briefing: taeglich 07:00)

echo [5/7] MailPoll-Task ...
schtasks /create /tn "SchoepferMatrix-MailPoll"    /tr "wscript.exe //B //Nologo \"%VBS%\" \"%ROOT%\mail_poll.cmd\""        /sc minute /mo 5           /f >nul 2>&1
if errorlevel 1 (echo [FEHLER] MailPoll.) else (echo [ok] MailPoll: alle 5 Minuten)

echo [6/6] Retro-Task ...
schtasks /create /tn "SchoepferMatrix-Retro"       /tr "wscript.exe //B //Nologo \"%VBS%\" \"%ROOT%\retro.cmd\""            /sc weekly /d SUN /st 20:00 /f >nul 2>&1
if errorlevel 1 (echo [FEHLER] Retro.) else (echo [ok] Retro: Sonntags 20:00)

REM StartWhenAvailable aktivieren: Backup/Eval/Briefing/Retro liegen in Zeiten, wo der
REM PC oft aus ist - ohne das Flag werden verpasste Starts NIE nachgeholt (0x800710E0).
echo [7/7] Verpasste-Starts-Nachholen aktivieren ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%MATRIX_ROOT%\tasks_fix.ps1"

REM HINWEIS: SchoepferMatrix-TgCallback (G1 Inline-Buttons) wurde ENTFERNT.
REM Grund: zweiter getUpdates-Poller auf demselben Bot-Token setzte
REM allowed_updates=["callback_query"] -> Telegram verwarf ALLE Textnachrichten.
REM Bestaetigungen laufen weiter per Text "GO <id>" ueber das Gateway.
REM (Loeschzeile oben in Zeile 33 raeumt evtl. noch vorhandene Alt-Tasks weg.)

REM Version-Marker schreiben (gateway.cmd prueft diesen statt Tasks einzeln)
echo v2-vbs>"%MARKER%"

echo.
echo ============================================================
echo Fertig. Tasks laufen ab jetzt unsichtbar im Hintergrund.
echo ============================================================
endlocal
