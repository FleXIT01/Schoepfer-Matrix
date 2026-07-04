# stop_all.ps1 — EIN zentraler, robuster Stopper fuer die Schoepfer-Matrix.
# Beendet ALLES, was gateway.cmd startet — port-basiert (zuverlaessig), nicht per
# Fenstertitel. Wird von stop.cmd UND vom gateway_loop.ps1-Cleanup (Strg+C) aufgerufen.
#
# Dienste/Ports:  Gateway 18789 | Ollama 11434 (+ alle ollama*-Prozesse)
#                 Reranker 8011 | ComfyUI 8188 | Webhook 7890
#                 Docker-Stacks: WeKnora (8080) + SearXNG (8888)  -> compose stop

$ErrorActionPreference = 'Continue'
# Portabel: Root = eigener Ordner (oder via MATRIX_ROOT vom Aufrufer vererbt).
$MatrixRoot = if ($env:MATRIX_ROOT) { $env:MATRIX_ROOT } else { $PSScriptRoot }

# Beendet den Prozess, der auf $port lauscht (samt sauberer Meldung).
function Stop-Port([int]$port, [string]$label) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 4 }
        foreach ($procId in $procIds) {
            try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host ("  [ok] {0} (Port {1}, PID {2}) beendet." -f $label, $port, $procId) }
            catch { Write-Host ("  [!] {0} (PID {1}) liess sich nicht beenden: {2}" -f $label, $procId, $_.Exception.Message) }
        }
    } else {
        Write-Host ("  [i] {0} (Port {1}) lief nicht." -f $label, $port)
    }
}

Write-Host '============================================================'
Write-Host '  STOPP - beende die komplette Schoepfer-Matrix ...'
Write-Host '============================================================'

# 0) STOPP-SIGNAL setzen: sagt dem gateway_loop-Supervisor "NICHT neu starten".
#    Ohne das wuerde der Supervisor den gekillten Gateway als Absturz werten und
#    nach 5s neu starten -> stop.cmd "macht nichts". gateway.cmd loescht das Flag
#    beim naechsten Start wieder.
$stopFlag = Join-Path $env:TEMP 'schoepfer_stop.flag'
try { Set-Content -Path $stopFlag -Value (Get-Date -Format o) -Force -ErrorAction Stop } catch {}

# Supervisor (gateway_loop.ps1) gezielt beenden, damit er den Stopp nicht bekaempft -
# aber NIE sich selbst oder den eigenen Eltern-Prozess killen (Strg+C-Cleanup-Fall,
# da ist der Supervisor unser Parent und beendet sich gleich selbst).
$self   = $PID
$parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$self" -ErrorAction SilentlyContinue).ParentProcessId
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -match 'gateway_loop\.ps1' -and $_.ProcessId -ne $self -and $_.ProcessId -ne $parent } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('  [ok] Gateway-Supervisor (PID {0}) beendet - kein Neustart.' -f $_.ProcessId) } catch {} }

# 1) Gateway (Node) — per Port und zur Sicherheit per Kommandozeile.
Stop-Port 18789 'Gateway'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match 'openclaw.*gateway run' } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }

# 2) Ollama — ALLE Varianten (serve, Tray 'ollama app', Modell-Runner 'ollama_llama_server').
$oll = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'ollama*' }
if ($oll) {
    $oll | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host ('  [ok] Ollama beendet ({0} Prozess(e), VRAM/Strom frei).' -f $oll.Count)
} else {
    Write-Host '  [i] Ollama lief nicht.'
}

# 3) Nebendienste per Port.
Stop-Port 8011 'Reranker'
Stop-Port 8188 'ComfyUI'
Stop-Port 7890 'Webhook'

# 4) Uebrige Fenster per Titel schliessen (Belt-and-Suspenders, samt Kindprozessen /T).
foreach ($t in @('Schoepfer-Matrix Reranker','Schoepfer-Matrix ComfyUI','Schoepfer-Matrix Webhook','Schoepfer-Matrix Ollama','Watchdog-Ollama')) {
    & taskkill /F /T /FI "WINDOWTITLE eq $t" *> $null
}

# 5) Docker-Stacks anhalten (best effort; nur wenn Docker laeuft). 'stop' statt 'down'
#    -> Container bleiben erhalten, Neustart spaeter schnell, aber CPU/RAM frei.
& docker info *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host '  [..] Docker-Stacks anhalten (WeKnora + SearXNG) ...'
    & docker compose --project-directory "$MatrixRoot\WeKnora-main" -f "$MatrixRoot\WeKnora-main\docker-compose.yml" --profile qdrant stop *> $null
    & docker compose --project-directory "$MatrixRoot\searxng" stop *> $null
    Write-Host '  [ok] Docker-Stacks angehalten (mit gateway.cmd wieder hoch).'
} else {
    Write-Host '  [i] Docker laeuft nicht - nichts anzuhalten.'
}

Write-Host '============================================================'
Write-Host '  FERTIG. Alles gestoppt. Der Watchdog startet NICHTS wieder,'
Write-Host '  solange das Gateway aus ist.'
Write-Host '============================================================'
