#Requires AutoHotkey v2.0
; ============================================================
;  Schoepfer-Matrix Hotkeys (I1)
;  Markierten Text in JEDER App an die Matrix schicken.
;
;  Win+Y  = Erklaeren    (was bedeutet das?)
;  Win+U  = Umformulieren (praeziser/klarer)
;  Win+I  = Ins Deutsche uebersetzen
;  Win+O  = Freie Frage  (Eingabe-Popup)
;
;  Voraussetzung: webhook_server laueft (gateway.cmd gestartet)
;  Token:  aus secrets.env oder Standard unten aendern
; ============================================================

ENDPOINT  := "http://127.0.0.1:7890/run"
TOKEN     := "schoepfer-matrix-webhook-2026"  ; muss mit secrets.env uebereinstimmen
TIMEOUT_S := 90  ; Sekunden bis Anfrage abgebrochen wird

; --- Win+Y: Erklaeren ---
#y:: {
    text := _GetSelection()
    if text = ""
        return
    _AskMatrix("Erklaere folgendes kurz und verstaendlich auf Deutsch: " text)
}

; --- Win+U: Umformulieren ---
#u:: {
    text := _GetSelection()
    if text = ""
        return
    _AskMatrix("Formuliere folgenden Text praeziser und klarer um. Nur den ueberarbeiteten Text, keine Erklaerung: " text)
}

; --- Win+I: Uebersetzen (ins Deutsche) ---
#i:: {
    text := _GetSelection()
    if text = ""
        return
    _AskMatrix("Uebersetze folgenden Text praezise ins Deutsche: " text)
}

; --- Win+O: Freie Frage (InputBox) ---
#o:: {
    text := _GetSelection()
    ib := InputBox("Frage an die Matrix:", "Schoepfer-Matrix", "w500 h120", text)
    if ib.Result = "Cancel" or ib.Value = ""
        return
    _AskMatrix(ib.Value)
}

; ============================================================
;  Hilfsfunktionen
; ============================================================

_GetSelection() {
    saved := A_Clipboard
    A_Clipboard := ""
    Send "^c"
    if !ClipWait(1.5)
        return ""
    sel := A_Clipboard
    A_Clipboard := saved
    return Trim(sel)
}

_AskMatrix(prompt) {
    global ENDPOINT, TOKEN, TIMEOUT_S

    ; Ladeindikator
    ToolTip "⏳ Matrix denkt ..."

    ; JSON-Payload bauen (einfaches Escaping)
    safe := StrReplace(prompt, "\", "\\")
    safe := StrReplace(safe, '"', '\"')
    safe := StrReplace(safe, "`r`n", "\n")
    safe := StrReplace(safe, "`n", "\n")
    json := '{"prompt":"' safe '","timeout":' TIMEOUT_S '}'

    ; HTTP-POST via WinHttp COM (kein externes Paket noetig)
    try {
        http := ComObject("WinHttp.WinHttpRequest.5.1")
        http.Open("POST", ENDPOINT, false)
        http.SetRequestHeader("Content-Type",  "application/json")
        http.SetRequestHeader("Authorization", "Bearer " TOKEN)
        http.SetTimeouts(5000, 5000, 0, TIMEOUT_S * 1000)
        http.Send(json)

        raw := http.ResponseText
        ; "result"-Feld aus JSON extrahieren (einfacher Regex)
        if RegExMatch(raw, '"result"\s*:\s*"((?:[^"\\]|\\.)*)?"', &m)
            answer := _JsonUnescape(m[1])
        else
            answer := "⚠ Keine Antwort: " SubStr(raw, 1, 200)

    } catch as e {
        ToolTip ""
        MsgBox "Matrix-Verbindung fehlgeschlagen:`n" e.Message "`n`nLaeuft gateway.cmd?", "Matrix-Hotkey", "Iconx"
        return
    }

    ToolTip ""

    ; Antwort als Tooltip und in Zwischenablage
    A_Clipboard := answer
    short := SubStr(answer, 1, 400)
    if StrLen(answer) > 400
        short .= "`n...`n[vollstaendig in Zwischenablage]"

    ; Tooltip 12 Sekunden anzeigen, dann automatisch ausblenden
    ToolTip short
    SetTimer () => ToolTip(), -12000
}

_JsonUnescape(s) {
    s := StrReplace(s, "\\n",  "`n")
    s := StrReplace(s, "\\r",  "")
    s := StrReplace(s, "\\t",  "`t")
    s := StrReplace(s, '\\"',  '"')
    s := StrReplace(s, "\\\\", "\")
    return s
}
