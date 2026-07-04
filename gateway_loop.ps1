# gateway_loop.ps1 — Gateway-Loop mit sauberem Strg+C-Stopp (V15).
# ZWECK: Strg+C beendet Gateway UND alles, was dazugehoert (Ollama, Reranker,
#        ComfyUI, Webhook, Docker-Stacks). Cleanup liegt zentral in stop_all.ps1.
#
# FRUEHERER BUG: Strg+C beendete nur 'node', der Loop hielt das fuer einen Absturz
# und startete das Gateway SOFORT NEU -> es sah aus, als wuerde Strg+C "nichts tun".
# FIX: Ein Strg+C-Handler setzt ein Stopp-Signal ($script:stopping) und unterdrueckt
# das harte PowerShell-Abbrechen ($e.Cancel = $true). Nach dem Beenden von node prueft
# der Loop das Signal und BRICHT AB (kein Neustart) -> finally raeumt alles auf.

$ErrorActionPreference = 'Continue'

# Portabel: Root = eigener Ordner (oder von gateway.cmd via MATRIX_ROOT vererbt);
# Secrets NIE im Skript - aus secrets.env laden, falls nicht schon in der Umgebung.
$MatrixRoot = if ($env:MATRIX_ROOT) { $env:MATRIX_ROOT } else { $PSScriptRoot }
foreach ($envFile in @("$MatrixRoot\matrix.env", "$MatrixRoot\secrets.env")) {
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*([^#][^=]*)=(.*)$') {
                $k = $Matches[1].Trim(); $v = $Matches[2].Trim()
                if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue)) { Set-Item "env:$k" $v }
            }
        }
    }
}
$token   = $env:TELEGRAM_BOT_TOKEN
$filter  = '["message","edited_message","channel_post","edited_channel_post","inline_query","chosen_inline_result","callback_query","shipping_query","pre_checkout_query","poll","poll_answer","my_chat_member","chat_member","chat_join_request","message_reaction"]'
$node    = "$MatrixRoot/openclaw-main/openclaw.mjs"
$stopAll = "$MatrixRoot\stop_all.ps1"
$stopFlag = Join-Path $env:TEMP 'schoepfer_stop.flag'   # extern (stop.cmd) gesetztes Stopp-Signal
$script:stopping   = $false   # wird vom Strg+C-Handler gesetzt -> Loop beendet sich
$script:killOllama = $true    # andere Instanz auf 18789 -> false -> nichts anfassen

# Altes Stopp-Signal aus einem frueheren Lauf entfernen (frischer Start).
Remove-Item $stopFlag -Force -ErrorAction SilentlyContinue

# True, wenn beendet werden soll: per Strg+C ODER per externem stop.cmd (Flag-Datei).
function Test-ShouldStop { return ($script:stopping -or (Test-Path $stopFlag)) }

# Strg+C-Handler: Signal setzen, hartes Abbrechen unterdruecken, Ollama sofort killen
# (reines .NET, weil Ollama in eigener Konsole laeuft und das Konsolen-Strg+C nicht
# selbst bekommt). Der Rest wird gleich im finally ueber stop_all.ps1 erledigt.
$null = [Console]::add_CancelKeyPress({
    param($s, $e)
    $e.Cancel = $true                  # NICHT hart abbrechen -> Loop+finally laufen weiter
    $script:stopping = $true
    try { [IO.File]::WriteAllText($stopFlag, (Get-Date).ToString('o')) } catch {}  # Signal auch als Datei
    try {
        [System.Diagnostics.Process]::GetProcesses() |
            Where-Object { $_.ProcessName -like 'ollama*' } |
            ForEach-Object { try { $_.Kill() } catch {} }
    } catch {}
    [Console]::WriteLine('')
    [Console]::WriteLine('       [Strg+C] Stopp-Signal gesetzt - fahre alles herunter ...')
})

Write-Host '============================================================'
Write-Host '  Gateway laeuft. BEENDEN mit Strg+C  ->  ALLES wird gestoppt.'
Write-Host '  (Gateway, Ollama, Reranker, ComfyUI, Webhook, Docker-Stacks)'
Write-Host '  Selbstheilend: bei Absturz automatischer Neustart.'
Write-Host '============================================================'

try {
    while (-not (Test-ShouldStop)) {
        # Telegram-Filter vor jedem (Neu)Start auf die volle Liste setzen.
        try {
            $u = "https://api.telegram.org/bot$token/getUpdates?timeout=0&offset=-1&allowed_updates=" + [uri]::EscapeDataString($filter)
            Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop | Out-Null
        } catch {}

        Write-Host ("[{0}] --- Gateway-Start ---" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
        & node $node gateway run
        $rc = $LASTEXITCODE
        Write-Host ("[!] Gateway-Exit Code={0} um {1}." -f $rc, (Get-Date -Format 'HH:mm:ss'))

        # Strg+C ODER stop.cmd? -> raus (KEIN Neustart).
        if (Test-ShouldStop) { break }

        Start-Sleep -Seconds 2
        if ($null -ne (Get-NetTCPConnection -LocalPort 18789 -State Listen -ErrorAction SilentlyContinue)) {
            Write-Host '[i] Andere Gateway-Instanz laeuft bereits (Port 18789) - diese beendet sich (Rest bleibt).'
            $script:killOllama = $false
            break
        }
        Write-Host '[..] Selbstheilung: Neustart in 5s. Zum BEENDEN jetzt Strg+C druecken (oder stop.cmd).'
        for ($i = 0; $i -lt 5 -and -not (Test-ShouldStop); $i++) { Start-Sleep -Seconds 1 }
    }
} finally {
    Write-Host ''
    if ($script:killOllama) {
        Write-Host '[cleanup] Fahre die komplette Schoepfer-Matrix herunter ...'
        & powershell -NoProfile -ExecutionPolicy Bypass -File $stopAll
    } else {
        Write-Host '[cleanup] Andere Instanz aktiv - es wird nichts gestoppt.'
    }
}
