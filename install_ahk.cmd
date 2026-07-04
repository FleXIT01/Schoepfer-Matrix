@echo off
REM Installiert AutoHotkey v2 und startet i1_hotkey.ahk (I1 - Globale Matrix-Hotkeys)
echo [I1] Installiere AutoHotkey v2 ...
winget install AutoHotkey.AutoHotkey --version 2.0.19 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [!] Installation fehlgeschlagen. Manuell: https://www.autohotkey.com/download/
    pause
    exit /b 1
)
echo [ok] AutoHotkey v2 installiert.
echo.
echo [I1] Starte Matrix-Hotkeys (n:\allinall\i1_hotkey.ahk) ...
start "" "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" "n:\allinall\i1_hotkey.ahk"
echo [ok] Hotkeys aktiv. Im System-Tray sichtbar.
echo.
echo  Win+Y  - Erklaeren
echo  Win+U  - Umformulieren
echo  Win+I  - Ins Deutsche uebersetzen
echo  Win+O  - Freie Frage (Eingabe-Popup)
pause
