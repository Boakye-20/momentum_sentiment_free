# One-click launcher: starts backend + frontend (via restart_servers.ps1)
# and opens the app in the default browser once it responds.
#
# This is what the "Stock Picker AI" desktop shortcut runs.

$RepoRoot = Split-Path -Parent $PSScriptRoot

& "$PSScriptRoot\restart_servers.ps1"

Write-Host "Waiting for frontend on :3000..."
$deadline = (Get-Date).AddSeconds(60)
$up = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}

if ($up) {
    Start-Process "http://localhost:3000"
} else {
    Write-Host "Frontend didn't come up within 60s - check the backend/frontend windows for errors."
    Start-Sleep -Seconds 5
}
