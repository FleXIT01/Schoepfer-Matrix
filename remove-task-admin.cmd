@echo off
REM ============================================================
REM  Entfernt die versteckte Windows-Aufgabe "OpenClaw Gateway".
REM  Einmalig als Administrator ausfuehren (Rechtsklick ->
REM  "Als Administrator ausfuehren") - danach kann diese Aufgabe
REM  NIE mehr einen Telegram-Poll-Konflikt erzeugen.
REM ============================================================
echo Entferne versteckte Aufgabe "OpenClaw Gateway" ...
schtasks /delete /tn "OpenClaw Gateway" /f
echo.
echo Status oben: ERFOLGREICH = entfernt | "nicht gefunden" = war schon weg.
echo Diese Datei kann danach geloescht werden.
echo.
pause
