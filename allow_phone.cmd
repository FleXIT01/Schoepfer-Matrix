@echo off
REM ============================================================
REM  Handy-Zugriff freischalten: Windows-Firewall fuer das
REM  OpenClaw-Gateway (Port 18789) im PRIVATEN Netz oeffnen.
REM  EINMALIG als Administrator ausfuehren (Rechtsklick -> Als
REM  Administrator). Nur noetig fuer ClawHub-Handy-Pairing.
REM  WICHTIG: Diese Datei MUSS CRLF-Zeilenenden haben (Windows).
REM ============================================================
title OpenClaw - Handy-Zugriff freischalten
net session >nul 2>&1
if errorlevel 1 (
    echo [!] Bitte als ADMINISTRATOR ausfuehren (Rechtsklick - Als Administrator^).
    pause
    exit /b 1
)
echo [..] Firewall-Regel "OpenClaw Gateway 18789" anlegen (TCP 18789, Profil Privat^) ...
netsh advfirewall firewall delete rule name="OpenClaw Gateway 18789" >nul 2>&1
netsh advfirewall firewall add rule name="OpenClaw Gateway 18789" dir=in action=allow protocol=TCP localport=18789 profile=private
if errorlevel 1 (
    echo [FEHLER] Regel konnte nicht angelegt werden.
) else (
    echo [ok] Handy darf jetzt im selben WLAN auf das Gateway zugreifen.
    echo      Gateway-Adresse: http://10.0.0.38:18789
)
echo.
pause
