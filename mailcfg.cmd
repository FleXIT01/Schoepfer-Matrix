@echo off
REM ============================================================
REM  Schoepfer-Matrix - E-Mail-Versand einrichten / umstellen
REM  Interaktiv: Provider (Outlook/Gmail/Office365/Custom) +
REM  Absender + App-Passwort. Schreibt mail_account.json.
REM  Danach Gateway neu starten, damit es greift.
REM ============================================================
title Schoepfer-Matrix Mail-Konfiguration
C:\Python314\python.exe "n:\allinall\mcp-servers\mail_mcp\configure.py"
echo.
pause
