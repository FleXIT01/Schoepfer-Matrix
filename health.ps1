# health.ps1 — Gesamtzustand der Schoepfer-Matrix auf einen Blick (NEU 02.07.2026).
# Aufruf per status.cmd (Doppelklick) oder direkt. Nur LESEND, aendert nichts.

$ErrorActionPreference = 'SilentlyContinue'
# Portabel: Root + Konfig aus matrix.env (BACKUP_DEST), sonst Defaults.
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

function Dot([bool]$on) { if ($on) { '[AN ]' } else { '[aus]' } }

Write-Host '============================================================'
Write-Host ('  SCHOEPFER-MATRIX STATUS   ' + (Get-Date -Format 'dd.MM.yyyy HH:mm'))
Write-Host '============================================================'

# --- Dienste (Ports) ---
Write-Host ''
Write-Host '-- Dienste --'
$ports = @(
    @(18789,'Gateway (Telegram-Bot)'), @(11434,'Ollama'), @(8080,'WeKnora-RAG'),
    @(8888,'SearXNG'), @(8011,'Reranker'), @(8188,'ComfyUI'), @(7890,'Webhook'), @(5678,'n8n')
)
foreach ($p in $ports) {
    $up = $null -ne (Get-NetTCPConnection -LocalPort $p[0] -State Listen -ErrorAction SilentlyContinue)
    Write-Host ('  {0} {1,-22} Port {2}' -f (Dot $up), $p[1], $p[0])
}

# --- Ollama: geladene Modelle ---
$oll = $null
try { $oll = Invoke-RestMethod 'http://127.0.0.1:11434/api/ps' -TimeoutSec 3 } catch {}
if ($oll -and $oll.models) {
    Write-Host ''
    Write-Host '-- Ollama: geladene Modelle (VRAM) --'
    foreach ($m in $oll.models) {
        Write-Host ('  {0}  ({1:N1} GB)' -f $m.name, ($m.size_vram/1GB))
    }
}

# --- GPU ---
$gpu = & nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits 2>$null
if ($gpu) {
    $g = ($gpu -split ',').Trim()
    Write-Host ''
    Write-Host ('-- GPU --  VRAM {0}/{1} MB, Auslastung {2}%' -f $g[0], $g[1], $g[2])
}

# --- Scheduled Tasks: letzte Ergebnisse ---
Write-Host ''
Write-Host '-- Hintergrund-Tasks (letzter Lauf) --'
foreach ($n in 'SchoepferMatrix-Backup','SchoepferMatrix-Briefing','SchoepferMatrix-Eval','SchoepferMatrix-MailPoll','SchoepferMatrix-Retro','SchoepferMatrix-Watchdog') {
    $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue
    if ($i) {
        $res = if ($i.LastTaskResult -eq 0) { 'OK' }
               elseif ($i.LastTaskResult -eq 0x800710E0) { 'VERPASST (holt nach)' }
               elseif ($i.LastTaskResult -eq 267011) { 'noch nie gelaufen' }
               else { ('Fehler 0x{0:X}' -f $i.LastTaskResult) }
        Write-Host ('  {0,-28} {1:dd.MM. HH:mm}  {2}' -f ($n -replace 'SchoepferMatrix-',''), $i.LastRunTime, $res)
    }
}

# --- Backup-Alter ---
Write-Host ''
$bkRoot = if ($env:BACKUP_DEST) { $env:BACKUP_DEST } else { "$MatrixRoot\_backups" }
if (Test-Path $bkRoot) {
    $last = Get-ChildItem $bkRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if ($last) {
        $dt = [datetime]::ParseExact($last.Name, 'yyyy-MM-dd_HHmmss', $null)
        $age = (Get-Date) - $dt
        $flag = if ($age.TotalHours -lt 30) { 'OK' } else { 'ALT!' }
        Write-Host ('-- Backup --  {0} ({1:0}h alt) [{2}]' -f $last.Name, $age.TotalHours, $flag)
    } else { Write-Host '-- Backup --  KEINES vorhanden!' }
} else { Write-Host '-- Backup --  Laufwerk I: nicht erreichbar!' }

# --- Letzter Golden-Eval ---
$golden = "$MatrixRoot\eval\results\nightly_golden.log"
if (Test-Path $golden) {
    $t = Get-Content $golden -Raw
    $m = [regex]::Matches($t, 'ERGEBNIS:\s*(\d+)/(\d+)')
    if ($m.Count -gt 0) {
        $last = $m[$m.Count-1]
        Write-Host ('-- Golden-Eval --  letzter Lauf: {0}/{1} gruen' -f $last.Groups[1].Value, $last.Groups[2].Value)
    }
}

# --- Autostart / Stopp-Flag ---
Write-Host ''
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Schoepfer-Matrix Gateway.lnk'
Write-Host ('-- Boot-Autostart --  ' + $(if (Test-Path $lnk) { 'EIN (autostart.cmd off zum Abschalten)' } else { 'AUS (autostart.cmd on zum Einschalten)' }))

# --- Docker (nur wenn laeuft) ---
$running = & docker ps --format '{{.Names}}' 2>$null
if ($running) {
    Write-Host ''
    Write-Host ('-- Docker --  laufend: ' + ($running -join ', '))
}

Write-Host ''
Write-Host '============================================================'
Write-Host '  Start: gateway.cmd | Stopp: Strg+C oder stop.cmd'
Write-Host '============================================================'
