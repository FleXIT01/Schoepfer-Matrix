# tasks_fix.ps1 — setzt StartWhenAvailable=true auf den zeitgebundenen Tasks.
# GRUND: Backup(02:30)/Eval(03:15)/Briefing(07:00)/Retro(So 20:00) liegen in Zeiten,
# in denen der PC meist AUS ist. Ohne StartWhenAvailable werden verpasste Starts beim
# Hochfahren ABGELEHNT (0x800710E0) -> die Tasks liefen faktisch nie. Mit dem Flag
# holt Windows den Start nach, sobald der PC das naechste Mal an ist.
# schtasks /create kann das Flag nicht setzen -> XML-Roundtrip.
# HINWEIS: Die Tasks gehoeren 'Administratoren' -> dieses Skript braucht Elevation.

$names = 'SchoepferMatrix-Backup','SchoepferMatrix-Eval','SchoepferMatrix-Briefing','SchoepferMatrix-Retro'
$ok = 0
foreach ($n in $names) {
    $x = & schtasks /query /tn $n /xml 2>$null | Out-String
    if ($x -notmatch '<Task ') { Write-Host "  [!] $n nicht gefunden - uebersprungen."; continue }
    if ($x -match '<StartWhenAvailable>true</StartWhenAvailable>') {
        Write-Host "  [ok] $n hatte das Flag schon."; $ok++; continue
    }
    if ($x -match '<StartWhenAvailable>') {
        $x = $x -replace '<StartWhenAvailable>false</StartWhenAvailable>', '<StartWhenAvailable>true</StartWhenAvailable>'
    } else {
        $x = $x -replace '</Settings>', "  <StartWhenAvailable>true</StartWhenAvailable>`r`n  </Settings>"
    }
    $p = Join-Path $env:TEMP ("$n.xml")
    [IO.File]::WriteAllText($p, $x, [Text.Encoding]::Unicode)
    & schtasks /delete /tn $n /f | Out-Null
    & schtasks /create /tn $n /xml $p | Out-Null
    Remove-Item $p -Force -ErrorAction SilentlyContinue
    $chk = (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)
    if ($chk -and $chk.Settings.StartWhenAvailable) { Write-Host "  [ok] $n -> StartWhenAvailable=true"; $ok++ }
    else { Write-Host "  [!] $n konnte nicht umgestellt werden." }
}
Write-Host ""
Write-Host ("Ergebnis: {0}/{1} Tasks holen verpasste Starts jetzt nach." -f $ok, $names.Count)
Start-Sleep -Seconds 3
