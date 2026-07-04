; notaus.ahk — NOT-AUS Hotkey fuer die Schoepfer-Matrix (Phase A)
; Ctrl+Alt+N  =  NOT-AUS aktivieren  (freeze.flag schreiben)
; Ctrl+Alt+M  =  NOT-AUS aufheben    (freeze.flag loeschen)
;
; Starten:  notaus.ahk doppelklicken (AutoHotkey v2 benoetigt)
; Autostart: Verknuepfung in %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
;
#Requires AutoHotkey v2.0

FlagFile := "n:\allinall\openclaw-workspace\state\freeze.flag"

^!n:: {  ; Ctrl+Alt+N = NOT-AUS
    global FlagFile
    try FileAppend(FormatTime(, "yyyy-MM-dd HH:mm:ss") . ": NOT-AUS via Ctrl+Alt+N`n", FlagFile)
    MsgBox(
        "NOT-AUS AKTIV!`n`nAlle Agent-Aktionen eingefroren.`n`nCtrl+Alt+M zum Entsperren.",
        "Schoepfer-Matrix NOT-AUS",
        "Icon! T5"
    )
}

^!m:: {  ; Ctrl+Alt+M = Entsperren
    global FlagFile
    if FileExist(FlagFile) {
        FileDelete(FlagFile)
        MsgBox(
            "NOT-AUS aufgehoben.`nAgent-Aktionen wieder erlaubt.",
            "Schoepfer-Matrix",
            "Icon! T3"
        )
    } else {
        MsgBox(
            "Kein Freeze-Flag gefunden (war schon entsperrt).",
            "Schoepfer-Matrix",
            "T2"
        )
    }
}
